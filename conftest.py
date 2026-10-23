"""Pytest bootstrap: make the repository root importable so that `snake_game`
resolves no matter which directory pytest is launched from."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
