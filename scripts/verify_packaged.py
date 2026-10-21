"""Check that a PyInstaller executable contains this checkout's Python code."""

from pathlib import Path
from types import CodeType

from PyInstaller.archive.readers import CArchiveReader


def normalize(code: CodeType) -> CodeType:
    return code.replace(
        co_filename="<checkout>",
        co_consts=tuple(normalize(value) if isinstance(value, CodeType) else value
                        for value in code.co_consts),
    )


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    executable = root / "packaging/dist/STIL-to-NI-Digital.exe"
    archive = CArchiveReader(str(executable)).open_embedded_archive("PYZ.pyz")
    required = {
        "stil_to_ni", "stil_to_ni.gui", "stil_to_ni.converter",
        "stil_to_ni.compiler", "stil_to_ni.profiles", "stil_to_ni.progress",
    }
    missing = required - archive.toc.keys()
    if missing:
        raise RuntimeError(f"Packaged executable is missing modules: {sorted(missing)}")
    checked = []
    for name in sorted(archive.toc):
        if name != "stil_to_ni" and not name.startswith("stil_to_ni."):
            continue
        relative = name.replace(".", "/")
        source = root / "src" / (relative + ("/__init__.py" if name == "stil_to_ni" else ".py"))
        expected = compile(source.read_text(encoding="utf-8"), str(source), "exec", optimize=1)
        if normalize(archive.extract(name)) != normalize(expected):
            raise RuntimeError(f"Packaged module differs from checkout: {name}")
        checked.append(name)
    print(f"Verified packaged source: {', '.join(checked)}")


if __name__ == "__main__":
    main()
