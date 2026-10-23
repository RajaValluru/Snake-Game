# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe for Mouse Snake -> standalone dist/MouseSnake.exe.

Build from the repo root with either:

    pip install pyinstaller
    python build_exe.py               # or:  pyinstaller --noconfirm MouseSnake.spec

Result: ONE self-contained file (Python + pygame bundled inside, no console
window). The machine that runs it does not need Python installed.

Optional knobs:
- MOUSE_SNAKE_CONSOLE=1  -> attach a console window (see startup tracebacks)
- icon.ico in the repo root + icon='icon.ico' below -> branded exe icon
"""

import os

# Attach a terminal so uncaught exceptions print instead of a modal dialog.
_console = os.environ.get("MOUSE_SNAKE_CONSOLE", "0") == "1"

a = Analysis(
    ['main.py'],          # entry point: pygame window/events/clock wiring
    pathex=[],
    binaries=[],
    datas=[],             # pygame's bundled data (fonts, SDL dlls) comes from PyInstaller's hook
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='MouseSnake',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,             # compress with UPX if it is on PATH; harmless otherwise
    upx_exclude=[],
    runtime_tmpdir=None,  # one-file mode: unpacks to a temp dir at startup
    console=_console,     # windowed game -> no console by default
    disable_windowed_traceback=not _console,  # error dialog only when there is no console
)
