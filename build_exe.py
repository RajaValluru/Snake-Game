"""Build the standalone Mouse Snake executable (.exe) with PyInstaller.

Usage (from anywhere; paths are resolved relative to this file):

    pip install pyinstaller        # one-time, on the machine doing the build
    python build_exe.py            # -> dist/MouseSnake.exe  (single self-contained file)

The exe is a single file: copy it onto any Windows machine and double-click —
Python does not need to be installed there. Command-line flags still work:

    MouseSnake.exe --seed N        # reproducible apple spawns

Debug tip: set MOUSE_SNAKE_CONSOLE=1 in the environment before building to get
a console window attached (startup errors become visible).
"""

from __future__ import annotations

import pathlib
import subprocess
import sys


def main() -> int:
    root = pathlib.Path(__file__).resolve().parent
    spec = root / "MouseSnake.spec"
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(spec)]
    print("Building MouseSnake.exe ...")
    print("$ " + " ".join(cmd))
    rc = subprocess.call(cmd, cwd=root)
    if rc == 0:
        exe = root / "dist" / "MouseSnake.exe"
        print(f"\nDone. Run it with:  {exe}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
