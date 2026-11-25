# -*- mode: python ; coding: utf-8 -*-
"""Bundle PyInstaller de CheckMate."""

from pathlib import Path

import sys

from PyInstaller.utils.hooks import collect_all

PROJECT = Path(SPECPATH).parent
SRC = PROJECT / "src"

playwright_datas, playwright_binaries, playwright_hidden = collect_all("playwright")
webview_datas, webview_binaries, webview_hidden = collect_all("webview")
curl_datas, curl_binaries, curl_hidden = collect_all("curl_cffi")

hiddenimports = playwright_hidden + webview_hidden + curl_hidden + [
    "keyring",
    "keyring.backends.Windows",
    "keyring.backends.SecretService",
    "keyring.backends.macOS",
    "tomli_w",
    "tkinter",
    "tkinter.messagebox",
    "pystray",
    "PIL.Image",
    "PIL.ImageDraw",
]

if sys.platform.startswith("win"):
    hiddenimports.append("pystray._win32")
    hiddenimports.extend(
        [
            "webview.platforms.edgechromium",
            "webview.platforms.winforms",
            "clr",
        ]
    )
elif sys.platform == "darwin":
    hiddenimports.append("pystray._darwin")
    hiddenimports.append("webview.platforms.cocoa")
else:
    hiddenimports.append("pystray._xorg")
    hiddenimports.append("webview.platforms.gtk")

a = Analysis(
    [str(PROJECT / "packaging" / "entrypoint.py")],
    pathex=[str(SRC)],
    binaries=playwright_binaries + webview_binaries + curl_binaries,
    datas=playwright_datas + webview_datas + curl_datas,
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
