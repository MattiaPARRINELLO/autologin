# -*- mode: python ; coding: utf-8 -*-
"""Bundle PyInstaller de CheckMate."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

PROJECT = Path(SPECPATH).parent
SRC = PROJECT / "src"

playwright_datas, playwright_binaries, playwright_hidden = collect_all("playwright")

hiddenimports = playwright_hidden + [
    "keyring",
    "keyring.backends.Windows",
    "keyring.backends.SecretService",
    "keyring.backends.macOS",
    "tomli_w",
    "tkinter",
    "tkinter.messagebox",
]

a = Analysis(
    [str(PROJECT / "packaging" / "entrypoint.py")],
    pathex=[str(SRC)],
    binaries=playwright_binaries,
    datas=playwright_datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="CheckMate",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(PROJECT / "assets" / "checkmate.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="CheckMate",
)
