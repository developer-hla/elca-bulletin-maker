# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Bulletin Maker.

Build with:
    PLAYWRIGHT_BROWSERS_PATH=0 playwright install chromium --only-shell
    pyinstaller bulletin_maker.spec
"""

from __future__ import annotations

import platform

from PyInstaller.utils.hooks import collect_data_files

# Read version from version.py (single source of truth)
VERSION = "0.0.0"
with open("src/bulletin_maker/version.py") as _f:
    for _line in _f:
        if _line.startswith("__version__"):
            VERSION = _line.split('"')[1]
            break

block_cipher = None

# Playwright data (browser driver + bundled headless shell)
# Install with --only-shell to avoid the full Chrome .app bundle whose nested
# .framework breaks PyInstaller codesigning (PyInstaller #7969).
playwright_datas = collect_data_files("playwright")

a = Analysis(
    ["src/bulletin_maker/ui/app.py"],
    pathex=["src"],
    binaries=[],
    datas=[
        # UI templates (HTML/CSS/JS for pywebview)
        ("src/bulletin_maker/ui/templates", "bulletin_maker/ui/templates"),
        # Jinja2 HTML templates for PDF rendering
        ("src/bulletin_maker/renderer/templates/html", "bulletin_maker/renderer/templates/html"),
        # Notation image assets
        ("src/bulletin_maker/renderer/assets", "bulletin_maker/renderer/assets"),
    ] + playwright_datas,
    hiddenimports=[
        "bulletin_maker",
        "bulletin_maker.ui.api",
        "bulletin_maker.sns.client",
        "bulletin_maker.renderer",
        "bulletin_maker.renderer.html_renderer",
        "bulletin_maker.renderer.filters",
        "bulletin_maker.renderer.pdf_engine",
        "bulletin_maker.renderer.image_manager",
        "bulletin_maker.renderer.season",
        "bulletin_maker.renderer.static_text",
        "bulletin_maker.renderer.text_utils",
        "bulletin_maker.renderer.prayers_parser",
        "bulletin_maker.updater",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Bulletin Maker",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Bulletin Maker",
)

# macOS: wrap into .app bundle
if platform.system() == "Darwin":
    app = BUNDLE(
        coll,
        name="Bulletin Maker.app",
        icon=None,
        bundle_identifier="com.ascensionjackson.bulletinmaker",
        info_plist={
            "NSHighResolutionCapable": True,
            "CFBundleShortVersionString": VERSION,
        },
    )
