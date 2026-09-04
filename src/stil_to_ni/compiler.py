"""Optional integration with the proprietary NI Digital Pattern Compiler."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


COMMON_COMPILER_PATHS = (
    Path(r"C:\Program Files\National Instruments\Digital Pattern Compiler\DigitalPatternCompiler.exe"),
    Path(r"C:\Program Files (x86)\National Instruments\Digital Pattern Compiler\DigitalPatternCompiler.exe"),
)


def find_compiler(explicit: Path | None = None) -> Path:
    if explicit is not None:
        path = explicit.expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"NI Digital Pattern Compiler not found: {path}")
        return path

    command = shutil.which("DigitalPatternCompiler.exe") or shutil.which("DigitalPatternCompiler")
    if command:
        return Path(command).resolve()
    for candidate in COMMON_COMPILER_PATHS:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "NI Digital Pattern Compiler was not found. Install NI Digital Pattern Editor/Compiler "
        "or pass --compiler PATH."
    )


def compile_pattern(
    source: Path,
    pinmap: Path,
    output: Path,
    compiler: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    executable = find_compiler(compiler)
    result = subprocess.run(
        [str(executable), "-pinmap", str(pinmap), "-o", str(output), str(source)],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
        raise RuntimeError(f"NI compiler failed with exit code {result.returncode}:\n{detail}")
    return result
