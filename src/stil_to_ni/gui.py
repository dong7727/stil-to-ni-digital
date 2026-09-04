"""Windows-friendly graphical interface for STIL to NI-Digital conversion."""

from __future__ import annotations

import os
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import __version__
from .compiler import compile_pattern, find_compiler
from .converter import ConversionError, ConversionResult, convert_file

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:  # File selection remains available without the optional package.
    DND_FILES = None
    TkinterDnD = None


BG = "#f4f7fb"
CARD = "#ffffff"
TEXT = "#182230"
MUTED = "#607086"
ACCENT = "#1769e0"
ACCENT_DARK = "#0f55ba"
SUCCESS = "#16794a"
BORDER = "#d7e0ec"


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


class ConverterApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.running = False
        self.last_output: Path | None = None

        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.expand_var = tk.BooleanVar(value=True)
        self.compile_var = tk.BooleanVar(value=self._compiler_available())
        self.status_var = tk.StringVar(value="请选择或拖入 STIL 文件")

        self.root.title(f"STIL to NI-Digital  {__version__}")
        self.root.geometry("900x700")
        self.root.minsize(760, 620)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._configure_style()
        self._build_ui()
        self.root.after(100, self._poll_events)

    @staticmethod
    def _compiler_available() -> bool:
        try:
            find_compiler()
        except FileNotFoundError:
            return False
        return True

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD)
        style.configure("Title.TLabel", background=BG, foreground=TEXT, font=("Segoe UI Semibold", 24))
        style.configure("Subtitle.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 10))
        style.configure("CardTitle.TLabel", background=CARD, foreground=TEXT, font=("Segoe UI Semibold", 11))
        style.configure("CardText.TLabel", background=CARD, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 9))
        style.configure("TCheckbutton", background=CARD, foreground=TEXT, font=("Segoe UI", 9))
        style.configure("Accent.TButton", font=("Segoe UI Semibold", 10), padding=(18, 10))
        style.configure("Secondary.TButton", font=("Segoe UI", 9), padding=(12, 7))
        style.configure("Horizontal.TProgressbar", troughcolor="#e7edf5", background=ACCENT)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=(28, 22, 28, 20))
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="STIL to NI-Digital", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            outer,
            text="将扫描型 STIL 转换为 NI .digipatsrc、.digitiming 和 .pinmap 文件",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(3, 18))

        input_card = ttk.Frame(outer, style="Card.TFrame", padding=18)
        input_card.pack(fill="x")
        ttk.Label(input_card, text="1  选择 STIL 文件", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(
            input_card,
            text="支持 .stil 和 .stil.gz；可拖放到下方区域，也可以点击“浏览”。",
            style="CardText.TLabel",
        ).pack(anchor="w", pady=(2, 10))

        row = ttk.Frame(input_card, style="Card.TFrame")
        row.pack(fill="x")
        self.input_entry = ttk.Entry(row, textvariable=self.input_var)
        self.input_entry.pack(side="left", fill="x", expand=True, ipady=6)
        self.input_button = ttk.Button(row, text="浏览…", command=self._browse_input, style="Secondary.TButton")
        self.input_button.pack(side="left", padx=(10, 0))

        drop_text = "把 STIL 文件拖到这里" if DND_FILES else "拖放组件未安装，请使用“浏览”选择文件"
        self.drop_zone = tk.Label(
            input_card,
            text=drop_text,
            bg="#f1f6fd",
            fg=ACCENT,
            font=("Segoe UI Semibold", 10),
            relief="solid",
            borderwidth=1,
            highlightthickness=0,
            height=3,
            cursor="hand2",
        )
        self.drop_zone.pack(fill="x", pady=(12, 0))
        self.drop_zone.bind("<Button-1>", lambda _event: self._browse_input())
        if DND_FILES and hasattr(self.drop_zone, "drop_target_register"):
            self.drop_zone.drop_target_register(DND_FILES)
            self.drop_zone.dnd_bind("<<Drop>>", self._on_drop)

        options_card = ttk.Frame(outer, style="Card.TFrame", padding=18)
        options_card.pack(fill="x", pady=(14, 0))
        ttk.Label(options_card, text="2  输出与转换选项", style="CardTitle.TLabel").pack(anchor="w")

        output_row = ttk.Frame(options_card, style="Card.TFrame")
        output_row.pack(fill="x", pady=(10, 8))
        self.output_entry = ttk.Entry(output_row, textvariable=self.output_var)
        self.output_entry.pack(side="left", fill="x", expand=True, ipady=6)
        self.output_button = ttk.Button(output_row, text="输出目录…", command=self._browse_output, style="Secondary.TButton")
        self.output_button.pack(side="left", padx=(10, 0))

        self.expand_check = ttk.Checkbutton(
            options_card,
            text="完全展开扫描周期（每个测试周期一行，文件可能很大）",
            variable=self.expand_var,
        )
        self.expand_check.pack(anchor="w", pady=(4, 2))
        self.compile_check = ttk.Checkbutton(
            options_card,
            text="调用 NI Digital Pattern Compiler，同时生成 .digipat",
            variable=self.compile_var,
        )
        self.compile_check.pack(anchor="w", pady=2)
        if not self._compiler_available():
            self.compile_var.set(False)
            self.compile_check.configure(state="disabled")
            ttk.Label(
                options_card,
                text="未检测到 NI 编译器；仍可生成 .digipatsrc、.digitiming 和 .pinmap。",
                style="CardText.TLabel",
            ).pack(anchor="w", pady=(2, 0))

        action_row = ttk.Frame(outer)
        action_row.pack(fill="x", pady=(16, 10))
        self.start_button = ttk.Button(action_row, text="开始转换", command=self._start, style="Accent.TButton")
        self.start_button.pack(side="left")
        self.open_button = ttk.Button(
            action_row,
            text="打开输出目录",
            command=self._open_output,
            style="Secondary.TButton",
            state="disabled",
        )
        self.open_button.pack(side="left", padx=(10, 0))
        ttk.Label(action_row, textvariable=self.status_var).pack(side="right")

        self.progress = ttk.Progressbar(outer, mode="indeterminate")
        self.progress.pack(fill="x")

        log_card = ttk.Frame(outer, style="Card.TFrame", padding=(14, 12))
        log_card.pack(fill="both", expand=True, pady=(12, 0))
        ttk.Label(log_card, text="转换日志", style="CardTitle.TLabel").pack(anchor="w", pady=(0, 7))
        log_frame = ttk.Frame(log_card, style="Card.TFrame")
        log_frame.pack(fill="both", expand=True)
        self.log = tk.Text(
            log_frame,
            height=10,
            wrap="word",
            bg="#0f1722",
            fg="#d9e5f5",
            insertbackground="white",
            selectbackground=ACCENT_DARK,
            relief="flat",
            padx=10,
            pady=9,
            font=("Cascadia Mono", 9),
            state="disabled",
        )
        scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def _browse_input(self) -> None:
        selected = filedialog.askopenfilename(
            title="选择 STIL 文件",
            filetypes=[("STIL files", "*.stil *.stil.gz"), ("All files", "*.*")],
        )
        if selected:
            self._set_input(Path(selected))

    def _browse_output(self) -> None:
        initial = self.output_var.get().strip() or str(Path.home())
        selected = filedialog.askdirectory(title="选择输出目录", initialdir=initial)
        if selected:
            self.output_var.set(selected)

    def _on_drop(self, event: object) -> None:
        data = getattr(event, "data", "")
        try:
            candidates = self.root.tk.splitlist(data)
        except tk.TclError:
            candidates = (data,)
        if candidates:
            self._set_input(Path(candidates[0]))

    def _set_input(self, source: Path) -> None:
        source = source.expanduser().resolve()
        if not _is_stil(source):
            messagebox.showerror("文件不支持", "请选择 .stil 或 .stil.gz 文件。", parent=self.root)
            return
        self.input_var.set(str(source))
        self.output_var.set(str(_suggest_output(source)))
        self.status_var.set("已选择文件，可以开始转换")
        self._append_log(f"输入文件：{source}")

    def _start(self) -> None:
        source = Path(self.input_var.get().strip()).expanduser()
        output_text = self.output_var.get().strip()
        if not _is_stil(source):
            messagebox.showerror("输入错误", "请选择存在的 .stil 或 .stil.gz 文件。", parent=self.root)
            return
        if not output_text:
            messagebox.showerror("输出错误", "请选择输出目录。", parent=self.root)
            return

        output = Path(output_text).expanduser()
        if output.exists() and not output.is_dir():
            messagebox.showerror("输出错误", "输出路径必须是文件夹。", parent=self.root)
            return
        try:
            output_has_files = output.is_dir() and next(output.iterdir(), None) is not None
        except OSError as exc:
            messagebox.showerror("输出错误", f"无法访问输出目录：{exc}", parent=self.root)
            return
        if output_has_files:
            proceed = messagebox.askyesno(
                "输出目录非空",
                "输出目录中已有文件，同名转换结果将被覆盖。是否继续？",
                parent=self.root,
            )
            if not proceed:
                return
        if self.compile_var.get():
            try:
                find_compiler()
            except FileNotFoundError as exc:
                messagebox.showerror("找不到 NI 编译器", str(exc), parent=self.root)
                return

        self.running = True
        self.last_output = None
        self._set_controls(False)
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self._append_log("开始转换，请勿关闭程序……")
        self._append_log(f"输入：{source.resolve()}")
        self._append_log(f"输出：{output.resolve()}")
        self._append_log(f"完全展开：{'是' if self.expand_var.get() else '否'}")
        self._append_log(f"编译 digipat：{'是' if self.compile_var.get() else '否'}")
        self.status_var.set("正在转换…")
        self.progress.start(12)

        thread = threading.Thread(
            target=self._worker,
            args=(source, output, self.expand_var.get(), self.compile_var.get()),
            daemon=True,
        )
        thread.start()

    def _worker(self, source: Path, output: Path, expand: bool, should_compile: bool) -> None:
        try:
            self.events.put(("log", "正在解析 STIL 并生成 NI 文件……"))
            result = convert_file(source, output, expand_scan=expand)
            self.events.put(("log", f"解析完成：{result.cycles:,} 个测试周期，{len(result.pins)} 个引脚"))
            for kind, path in result.files.items():
                self.events.put(("log", f"{kind}: {path}"))

            if should_compile:
                sources = [result.files["pattern_source"]]
                expanded = result.files.get("expanded_pattern_source")
                if expanded is not None:
                    sources.append(expanded)
                for pattern_source in sources:
                    self.events.put(("log", f"正在使用 NI 编译器处理：{pattern_source.name}"))
                    compiled = pattern_source.with_suffix(".digipat")
                    completed = compile_pattern(pattern_source, result.files["pinmap"], compiled)
                    detail = "\n".join(part.strip() for part in (completed.stdout, completed.stderr) if part.strip())
                    if detail:
                        self.events.put(("log", detail))
                    self.events.put(("log", f"compiled_pattern: {compiled}"))

            self.events.put(("success", (result, output.resolve())))
        except (ConversionError, FileNotFoundError, RuntimeError, OSError) as exc:
            self.events.put(("error", str(exc)))
        except Exception as exc:  # Keep the GUI alive and surface unexpected failures.
            self.events.put(("error", f"未预期错误：{type(exc).__name__}: {exc}"))

    def _poll_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "log":
                    self._append_log(str(payload))
                elif kind == "success":
                    result, output = payload
                    self._finish_success(result, output)
                elif kind == "error":
                    self._finish_error(str(payload))
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def _finish_success(self, result: ConversionResult, output: Path) -> None:
        self.running = False
        self.last_output = output
        self.progress.stop()
        self._set_controls(True)
        self.open_button.configure(state="normal")
        self.status_var.set("转换完成")
        self._append_log(f"完成：共 {result.cycles:,} 个测试周期。")
        messagebox.showinfo(
            "转换完成",
            f"已生成 NI 文件。\n\n测试周期：{result.cycles:,}\n输出目录：{output}",
            parent=self.root,
        )

    def _finish_error(self, detail: str) -> None:
        self.running = False
        self.progress.stop()
        self._set_controls(True)
        self.status_var.set("转换失败")
        self._append_log(f"错误：{detail}")
        messagebox.showerror("转换失败", detail, parent=self.root)

    def _set_controls(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for widget in (self.input_entry, self.input_button, self.output_entry, self.output_button, self.expand_check, self.start_button):
            widget.configure(state=state)
        if self._compiler_available():
            self.compile_check.configure(state=state)
        if not enabled:
            self.open_button.configure(state="disabled")

    def _append_log(self, line: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", line.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _open_output(self) -> None:
        if self.last_output and self.last_output.is_dir():
            os.startfile(self.last_output)  # type: ignore[attr-defined]

    def _on_close(self) -> None:
        if self.running:
            messagebox.showwarning("转换正在进行", "请等待转换完成后再关闭程序。", parent=self.root)
            return
        self.root.destroy()


def _enable_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass


def self_test() -> int:
    """Construct the complete hidden UI to verify packaged GUI resources."""
    root = TkinterDnD.Tk() if TkinterDnD else tk.Tk()
    root.withdraw()
    ConverterApp(root)
    root.update_idletasks()
    root.destroy()
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    _enable_dpi_awareness()
    root = TkinterDnD.Tk() if TkinterDnD else tk.Tk()
    app = ConverterApp(root)
    for argument in sys.argv[1:]:
        candidate = Path(argument)
        if _is_stil(candidate):
            app._set_input(candidate)
            break
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
