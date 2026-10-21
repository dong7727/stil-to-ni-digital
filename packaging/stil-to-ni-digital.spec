# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path


python_abi_dll = Path(sys.base_prefix) / "python3.dll"

analysis = Analysis(
    ["windows_entry.py"],
    # Always package this checkout, even if the build venv has an older wheel.
    pathex=[str(Path(SPECPATH).parent / "src")],
    binaries=[(str(python_abi_dll), ".")],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="STIL-to-NI-Digital",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
