"""Windows desktop interface for STIL to NI-Digital conversion."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QCloseEvent, QDesktopServices, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFileDialog,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .compiler import compile_pattern, find_compiler
from .converter import ConversionError, ConversionResult, StilInspection, convert_file, inspect_file


def _suggest_output(source: Path) -> Path:
    name = source.name
    lower = name.lower()
    if lower.endswith(".stil.gz"):
        name = name[:-8]
    elif lower.endswith(".stil"):
        name = name[:-5]
    return source.parent / f"{name}_NI_Output"


def _is_stil(path: Path) -> bool:
    name = path.name.lower()
    return path.is_file() and (name.endswith(".stil") or name.endswith(".stil.gz"))


class DropArea(QFrame):
    file_dropped = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setObjectName("dropArea")
        self.setMinimumHeight(72)
        layout = QVBoxLayout(self)
        label = QLabel("把 STIL 文件拖到这里")
        label.setObjectName("dropText")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

    @staticmethod
    def _first_stil(event: QDragEnterEvent | QDropEvent) -> Path | None:
        mime = event.mimeData()
        if not mime.hasUrls():
            return None
        for url in mime.urls():
            candidate = Path(url.toLocalFile())
            if _is_stil(candidate):
                return candidate
        return None

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._first_stil(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        candidate = self._first_stil(event)
        if candidate:
            event.acceptProposedAction()
            self.file_dropped.emit(str(candidate))


class InspectionWorker(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, source: Path) -> None:
        super().__init__()
        self.source = source

    @Slot()
    def run(self) -> None:
        try:
            self.succeeded.emit(inspect_file(self.source))
        except (ConversionError, FileNotFoundError, OSError) as exc:
            self.failed.emit(str(exc))
        except Exception as exc:
            self.failed.emit(f"未预期错误：{type(exc).__name__}: {exc}")
        finally:
            self.finished.emit()


class ConversionWorker(QObject):
    log = Signal(str)
    succeeded = Signal(object, str)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        source: Path,
        output: Path,
        expand: bool,
        should_compile: bool,
        selected_pins: tuple[str, ...],
    ) -> None:
        super().__init__()
        self.source = source
        self.output = output
        self.expand = expand
        self.should_compile = should_compile
        self.selected_pins = selected_pins

    @Slot()
    def run(self) -> None:
        try:
            self.log.emit("正在解析 STIL 并生成 NI 文件……")
            result = convert_file(
                self.source,
                self.output,
                expand_scan=self.expand,
                selected_pins=self.selected_pins,
            )
            self.log.emit(f"解析完成：{result.cycles:,} 个测试周期，{len(result.pins)} 个引脚")
            for kind, path in result.files.items():
                self.log.emit(f"{kind}: {path}")

            if self.should_compile:
                sources = [result.files["pattern_source"]]
                expanded = result.files.get("expanded_pattern_source")
                if expanded is not None:
                    sources.append(expanded)
                for pattern_source in sources:
                    self.log.emit(f"正在使用 NI 编译器处理：{pattern_source.name}")
                    compiled = pattern_source.with_suffix(".digipat")
                    completed = compile_pattern(pattern_source, result.files["pinmap"], compiled)
                    detail = "\n".join(
                        part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
                    )
                    if detail:
                        self.log.emit(detail)
                    self.log.emit(f"compiled_pattern: {compiled}")

            self.succeeded.emit(result, str(self.output.resolve()))
        except (ConversionError, FileNotFoundError, RuntimeError, OSError) as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # Keep the UI alive and surface unexpected failures.
            self.failed.emit(f"未预期错误：{type(exc).__name__}: {exc}")
        finally:
            self.finished.emit()


class ConverterWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.running = False
        self.last_output: Path | None = None
        self.thread: QThread | None = None
        self.worker: QObject | None = None
        self.inspection: StilInspection | None = None
        self.inspection_source: Path | None = None
        self.compiler_available = self._compiler_available()

        self.setWindowTitle(f"STIL to NI-Digital  {__version__}")
        self.resize(960, 860)
        self.setMinimumSize(820, 720)
        self._build_ui()
        self._apply_style()

    @staticmethod
    def _compiler_available() -> bool:
        try:
            find_compiler()
        except FileNotFoundError:
            return False
        return True

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(30, 24, 30, 24)
        outer.setSpacing(14)

        title = QLabel("STIL to NI-Digital")
        title.setObjectName("title")
        subtitle = QLabel("将扫描型 STIL 转换为 NI .digipatsrc、.digitiming 和 .pinmap 文件")
        subtitle.setObjectName("subtitle")
        outer.addWidget(title)
        outer.addWidget(subtitle)

        input_card = self._card()
        input_layout = QVBoxLayout(input_card)
        input_layout.setContentsMargins(18, 16, 18, 18)
        input_layout.setSpacing(10)
        input_layout.addWidget(self._card_title("1  选择 STIL 文件"))
        input_layout.addWidget(self._hint("支持 .stil 和 .stil.gz；可拖放到下方区域，也可以点击“浏览”。"))
        input_row = QHBoxLayout()
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("请选择 STIL 文件")
        self.input_button = QPushButton("浏览…")
        self.input_button.clicked.connect(self._browse_input)
        self.inspect_button = QPushButton("解析引脚")
        self.inspect_button.clicked.connect(self._start_inspection)
        input_row.addWidget(self.input_edit, 1)
        input_row.addWidget(self.input_button)
        input_row.addWidget(self.inspect_button)
        input_layout.addLayout(input_row)
        self.drop_area = DropArea()
        self.drop_area.file_dropped.connect(lambda path: self._set_input(Path(path)))
        input_layout.addWidget(self.drop_area)
        outer.addWidget(input_card)

        pins_card = self._card()
        pins_layout = QVBoxLayout(pins_card)
        pins_layout.setContentsMargins(18, 16, 18, 18)
        pins_layout.setSpacing(9)
        pins_layout.addWidget(self._card_title("2  解析结果与引脚选择"))
        pins_layout.addWidget(
            self._hint("选择文件后会自动解析。可取消普通引脚；ScanIn、ScanOut 和扫描时钟为必选。")
        )
        pins_action_row = QHBoxLayout()
        self.pin_summary = QLabel("尚未解析 STIL 文件")
        self.pin_summary.setObjectName("hint")
        self.select_all_button = QPushButton("全选")
        self.select_all_button.clicked.connect(self._select_all_pins)
        self.select_all_button.setEnabled(False)
        self.required_only_button = QPushButton("仅保留必选")
        self.required_only_button.clicked.connect(self._select_required_pins)
        self.required_only_button.setEnabled(False)
        pins_action_row.addWidget(self.pin_summary, 1)
        pins_action_row.addWidget(self.select_all_button)
        pins_action_row.addWidget(self.required_only_button)
        pins_layout.addLayout(pins_action_row)
        self.pin_table = QTableWidget(0, 4)
        self.pin_table.setHorizontalHeaderLabels(("转换", "引脚", "方向", "角色"))
        self.pin_table.setAlternatingRowColors(True)
        self.pin_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.pin_table.setMinimumHeight(190)
        self.pin_table.setEnabled(False)
        header = self.pin_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.pin_table.itemChanged.connect(self._update_pin_summary)
        pins_layout.addWidget(self.pin_table)
        outer.addWidget(pins_card)

        options_card = self._card()
        options_layout = QVBoxLayout(options_card)
        options_layout.setContentsMargins(18, 16, 18, 18)
        options_layout.setSpacing(9)
        options_layout.addWidget(self._card_title("3  输出与转换选项"))
        output_row = QHBoxLayout()
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("请选择输出目录")
        self.output_button = QPushButton("输出目录…")
        self.output_button.clicked.connect(self._browse_output)
        output_row.addWidget(self.output_edit, 1)
        output_row.addWidget(self.output_button)
        options_layout.addLayout(output_row)
        self.expand_check = QCheckBox("完全展开扫描周期（每个测试周期一行，文件可能很大）")
        self.expand_check.setChecked(True)
        self.compile_check = QCheckBox("调用 NI Digital Pattern Compiler，同时生成 .digipat")
        self.compile_check.setChecked(self.compiler_available)
        self.compile_check.setEnabled(self.compiler_available)
        options_layout.addWidget(self.expand_check)
        options_layout.addWidget(self.compile_check)
        if not self.compiler_available:
            options_layout.addWidget(
                self._hint("未检测到 NI 编译器；仍可生成 .digipatsrc、.digitiming 和 .pinmap。")
            )
        outer.addWidget(options_card)

        action_row = QHBoxLayout()
        self.start_button = QPushButton("开始转换")
        self.start_button.setObjectName("primaryButton")
        self.start_button.clicked.connect(self._start)
        self.start_button.setEnabled(False)
        self.open_button = QPushButton("打开输出目录")
        self.open_button.clicked.connect(self._open_output)
        self.open_button.setEnabled(False)
        self.status_label = QLabel("请选择或拖入 STIL 文件")
        self.status_label.setObjectName("status")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        action_row.addWidget(self.start_button)
        action_row.addWidget(self.open_button)
        action_row.addStretch(1)
        action_row.addWidget(self.status_label)
        outer.addLayout(action_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.hide()
        outer.addWidget(self.progress)

        log_card = self._card()
        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(16, 14, 16, 16)
        log_layout.addWidget(self._card_title("转换日志"))
        self.log = QPlainTextEdit()
        self.log.setObjectName("log")
        self.log.setReadOnly(True)
        self.log.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.log.setMinimumHeight(110)
        log_layout.addWidget(self.log)
        outer.addWidget(log_card, 1)

    @staticmethod
    def _card() -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        return card

    @staticmethod
    def _card_title(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("cardTitle")
        return label

    @staticmethod
    def _hint(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("hint")
        label.setWordWrap(True)
        return label

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #f4f7fb; color: #182230; font-family: "Segoe UI"; font-size: 14px; }
            QLabel#title { font-size: 30px; font-weight: 700; }
            QLabel#subtitle, QLabel#hint, QLabel#status { color: #607086; }
            QLabel#cardTitle { font-size: 16px; font-weight: 600; }
            QFrame#card { background: #ffffff; border: 1px solid #d7e0ec; border-radius: 10px; }
            QFrame#dropArea { background: #f1f6fd; border: 2px dashed #75a8ed; border-radius: 8px; }
            QFrame#dropArea:hover { background: #e8f2ff; border-color: #1769e0; }
            QLabel#dropText { background: transparent; color: #1769e0; font-weight: 600; border: none; }
            QLineEdit { background: #ffffff; border: 1px solid #bdc9d8; border-radius: 6px; padding: 9px 10px; }
            QLineEdit:focus { border: 2px solid #1769e0; padding: 8px 9px; }
            QPushButton { background: #ffffff; border: 1px solid #b9c6d6; border-radius: 6px; padding: 9px 16px; }
            QPushButton:hover { background: #eef4fc; border-color: #7d9fc8; }
            QPushButton:disabled { color: #9aa7b6; background: #edf1f5; border-color: #d9e0e8; }
            QPushButton#primaryButton { background: #1769e0; color: #ffffff; border: none; font-weight: 600; padding: 11px 22px; }
            QPushButton#primaryButton:hover { background: #0f55ba; }
            QCheckBox { background: transparent; spacing: 8px; padding: 2px; }
            QProgressBar { border: none; background: #e2e9f2; height: 7px; border-radius: 3px; }
            QProgressBar::chunk { background: #1769e0; border-radius: 3px; }
            QPlainTextEdit#log { background: #0f1722; color: #d9e5f5; border: none; border-radius: 7px; padding: 8px; font-family: "Cascadia Mono", Consolas; font-size: 13px; }
            """
        )

    @Slot()
    def _browse_input(self) -> None:
        selected, _filter = QFileDialog.getOpenFileName(
            self,
            "选择 STIL 文件",
            "",
            "STIL files (*.stil *.stil.gz);;All files (*.*)",
        )
        if selected:
            self._set_input(Path(selected))

    @Slot()
    def _browse_output(self) -> None:
        initial = self.output_edit.text().strip() or str(Path.home())
        selected = QFileDialog.getExistingDirectory(self, "选择输出目录", initial)
        if selected:
            self.output_edit.setText(selected)

    def _set_input(self, source: Path) -> None:
        source = source.expanduser().resolve()
        if not _is_stil(source):
            QMessageBox.critical(self, "文件不支持", "请选择 .stil 或 .stil.gz 文件。")
            return
        self.input_edit.setText(str(source))
        self.output_edit.setText(str(_suggest_output(source)))
        self._clear_inspection()
        self.status_label.setText("已选择文件，正在解析…")
        self._append_log(f"输入文件：{source}")
        self._start_inspection()

    def _clear_inspection(self) -> None:
        self.inspection = None
        self.inspection_source = None
        self.pin_table.setRowCount(0)
        self.pin_table.setEnabled(False)
        self.pin_summary.setText("尚未解析 STIL 文件")
        self.start_button.setEnabled(False)
        self.select_all_button.setEnabled(False)
        self.required_only_button.setEnabled(False)

    @Slot()
    def _start_inspection(self) -> None:
        if self.running:
            return
        source = Path(self.input_edit.text().strip()).expanduser()
        if not _is_stil(source):
            QMessageBox.critical(self, "输入错误", "请选择存在的 .stil 或 .stil.gz 文件。")
            return
        self._clear_inspection()
        self.running = True
        self._set_controls(False)
        self.status_label.setText("正在解析 STIL…")
        self.progress.show()
        self._append_log("正在解析引脚、Timing 和 ScanChain……")

        self.thread = QThread(self)
        self.worker = InspectionWorker(source.resolve())
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)  # type: ignore[attr-defined]
        self.worker.succeeded.connect(self._finish_inspection)  # type: ignore[attr-defined]
        self.worker.failed.connect(self._finish_inspection_error)  # type: ignore[attr-defined]
        self.worker.finished.connect(self.thread.quit)  # type: ignore[attr-defined]
        self.worker.finished.connect(self.worker.deleteLater)  # type: ignore[attr-defined]
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    @Slot(object)
    def _finish_inspection(self, inspection: StilInspection) -> None:
        self.running = False
        self.inspection = inspection
        self.inspection_source = inspection.source
        self.progress.hide()
        self._populate_pins(inspection)
        self._set_controls(True)
        self.status_label.setText("解析完成，可以选择引脚并转换")
        self._append_log(
            f"解析完成：{len(inspection.pins)} 个引脚，{len(inspection.scan_chains)} 条 ScanChain"
        )
        for chain in inspection.scan_chains:
            self._append_log(
                f"ScanChain {chain.name}: {chain.scan_in} → {chain.scan_out}, "
                f"长度 {chain.length:,}"
            )

    @Slot(str)
    def _finish_inspection_error(self, detail: str) -> None:
        self.running = False
        self.progress.hide()
        self._set_controls(True)
        self.status_label.setText("解析失败")
        self._append_log(f"解析错误：{detail}")
        QMessageBox.critical(self, "解析失败", detail)

    def _populate_pins(self, inspection: StilInspection) -> None:
        self.pin_table.blockSignals(True)
        self.pin_table.setRowCount(len(inspection.pins))
        for row, pin in enumerate(inspection.pins):
            include = QTableWidgetItem()
            include.setCheckState(Qt.CheckState.Checked)
            flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            if not pin.required:
                flags |= Qt.ItemFlag.ItemIsUserCheckable
            include.setFlags(flags)
            include.setData(Qt.ItemDataRole.UserRole, pin.name)
            self.pin_table.setItem(row, 0, include)
            name_item = QTableWidgetItem(pin.name)
            name_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.pin_table.setItem(row, 1, name_item)
            direction_item = QTableWidgetItem(pin.direction)
            direction_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.pin_table.setItem(row, 2, direction_item)
            role = "、".join(pin.roles) if pin.roles else "普通引脚（可选）"
            if pin.required:
                role = f"必选；{role}"
            role_item = QTableWidgetItem(role)
            role_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.pin_table.setItem(row, 3, role_item)
        self.pin_table.blockSignals(False)
        self.pin_table.setEnabled(True)
        self.select_all_button.setEnabled(True)
        self.required_only_button.setEnabled(True)
        self._update_pin_summary()

    @Slot()
    def _select_all_pins(self) -> None:
        self.pin_table.blockSignals(True)
        for row in range(self.pin_table.rowCount()):
            self.pin_table.item(row, 0).setCheckState(Qt.CheckState.Checked)
        self.pin_table.blockSignals(False)
        self._update_pin_summary()

    @Slot()
    def _select_required_pins(self) -> None:
        if self.inspection is None:
            return
        required = {pin.name for pin in self.inspection.pins if pin.required}
        self.pin_table.blockSignals(True)
        for row in range(self.pin_table.rowCount()):
            item = self.pin_table.item(row, 0)
            pin = str(item.data(Qt.ItemDataRole.UserRole))
            item.setCheckState(
                Qt.CheckState.Checked if pin in required else Qt.CheckState.Unchecked
            )
        self.pin_table.blockSignals(False)
        self._update_pin_summary()

    @Slot()
    def _update_pin_summary(self) -> None:
        selected = len(self._selected_pins())
        total = self.pin_table.rowCount()
        required = (
            sum(pin.required for pin in self.inspection.pins) if self.inspection is not None else 0
        )
        self.pin_summary.setText(f"已选择 {selected}/{total} 个引脚，其中 {required} 个必选")

    def _selected_pins(self) -> tuple[str, ...]:
        selected: list[str] = []
        for row in range(self.pin_table.rowCount()):
            item = self.pin_table.item(row, 0)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(str(item.data(Qt.ItemDataRole.UserRole)))
        return tuple(selected)

    @Slot()
    def _start(self) -> None:
        source = Path(self.input_edit.text().strip()).expanduser()
        output_text = self.output_edit.text().strip()
        if not _is_stil(source):
            QMessageBox.critical(self, "输入错误", "请选择存在的 .stil 或 .stil.gz 文件。")
            return
        resolved_source = source.resolve()
        if self.inspection is None or self.inspection_source != resolved_source:
            QMessageBox.critical(self, "尚未解析", "请先点击“解析引脚”，再选择引脚并转换。")
            return
        if not output_text:
            QMessageBox.critical(self, "输出错误", "请选择输出目录。")
            return

        output = Path(output_text).expanduser()
        if output.exists() and not output.is_dir():
            QMessageBox.critical(self, "输出错误", "输出路径必须是文件夹。")
            return
        try:
            output_has_files = output.is_dir() and next(output.iterdir(), None) is not None
        except OSError as exc:
            QMessageBox.critical(self, "输出错误", f"无法访问输出目录：{exc}")
            return
        if output_has_files:
            answer = QMessageBox.question(
                self,
                "输出目录非空",
                "输出目录中已有文件，同名转换结果将被覆盖。是否继续？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        if self.compile_check.isChecked():
            try:
                find_compiler()
            except FileNotFoundError as exc:
                QMessageBox.critical(self, "找不到 NI 编译器", str(exc))
                return

        self.running = True
        self.last_output = None
        self._set_controls(False)
        self.log.clear()
        self._append_log("开始转换，请勿关闭程序……")
        self._append_log(f"输入：{source.resolve()}")
        self._append_log(f"输出：{output.resolve()}")
        self._append_log(f"完全展开：{'是' if self.expand_check.isChecked() else '否'}")
        self._append_log(f"编译 digipat：{'是' if self.compile_check.isChecked() else '否'}")
        selected_pins = self._selected_pins()
        self._append_log(f"转换引脚：{len(selected_pins)}/{len(self.inspection.pins)}")
        self.status_label.setText("正在转换…")
        self.progress.show()

        self.thread = QThread(self)
        self.worker = ConversionWorker(
            source,
            output,
            self.expand_check.isChecked(),
            self.compile_check.isChecked(),
            selected_pins,
        )
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.log.connect(self._append_log)
        self.worker.succeeded.connect(self._finish_success)
        self.worker.failed.connect(self._finish_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    @Slot(object, str)
    def _finish_success(self, result: ConversionResult, output_text: str) -> None:
        self.running = False
        self.last_output = Path(output_text)
        self.progress.hide()
        self._set_controls(True)
        self.open_button.setEnabled(True)
        self.status_label.setText("转换完成")
        self._append_log(f"完成：共 {result.cycles:,} 个测试周期。")
        QMessageBox.information(
            self,
            "转换完成",
            f"已生成 NI 文件。\n\n测试周期：{result.cycles:,}\n输出目录：{output_text}",
        )

    @Slot(str)
    def _finish_error(self, detail: str) -> None:
        self.running = False
        self.progress.hide()
        self._set_controls(True)
        self.status_label.setText("转换失败")
        self._append_log(f"错误：{detail}")
        QMessageBox.critical(self, "转换失败", detail)

    def _set_controls(self, enabled: bool) -> None:
        for widget in (
            self.input_edit,
            self.input_button,
            self.inspect_button,
            self.output_edit,
            self.output_button,
            self.expand_check,
            self.drop_area,
        ):
            widget.setEnabled(enabled)
        self.start_button.setEnabled(enabled and self.inspection is not None)
        self.pin_table.setEnabled(enabled and self.inspection is not None)
        self.select_all_button.setEnabled(enabled and self.inspection is not None)
        self.required_only_button.setEnabled(enabled and self.inspection is not None)
        self.compile_check.setEnabled(enabled and self.compiler_available)
        if not enabled:
            self.open_button.setEnabled(False)

    @Slot(str)
    def _append_log(self, line: str) -> None:
        self.log.appendPlainText(line.rstrip())
        scroll = self.log.verticalScrollBar()
        scroll.setValue(scroll.maximum())

    @Slot()
    def _open_output(self) -> None:
        if self.last_output and self.last_output.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_output)))

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.running:
            QMessageBox.warning(self, "任务正在进行", "请等待解析或转换完成后再关闭程序。")
            event.ignore()
            return
        event.accept()


def self_test() -> int:
    """Construct the complete hidden UI to verify packaged GUI resources."""
    app = QApplication.instance() or QApplication(["stil-to-ni-self-test"])
    window = ConverterWindow()
    window.show()
    QTimer.singleShot(100, app.quit)
    return app.exec()


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    app = QApplication(sys.argv)
    app.setApplicationName("STIL to NI-Digital")
    app.setApplicationVersion(__version__)
    window = ConverterWindow()
    for argument in sys.argv[1:]:
        candidate = Path(argument)
        if _is_stil(candidate):
            window._set_input(candidate)
            break
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
