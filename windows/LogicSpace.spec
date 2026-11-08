# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

ROOT = Path(SPECPATH).parent
ICON = ROOT / "build" / "windows" / "logicspace.ico"
EXAMPLE_DATA = [
    (str(path), str(path.parent.relative_to(ROOT)))
    for path in (ROOT / "examples").rglob("*")
    if path.is_file() and path.suffix.lower() in {".json", ".asm", ".bin", ".hex", ".v", ".sv", ".md"}
]

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / "resources"), "resources"),
        (str(ROOT / "README.md"), "."),
    ] + EXAMPLE_DATA,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="LogicSpace",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon=str(ICON),
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False,
    upx=False,
    name="LogicSpace",
)
