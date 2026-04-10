#!/usr/bin/env python3
"""
Standalone credential setup tool for PyRAT API and frontend session access.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC_DIR = Path(__file__).resolve().parent / "src"
if _SRC_DIR.exists():
    sys.path.insert(0, str(_SRC_DIR))

from metazebrobot.utils.pyrat_credentials_cli import main


if __name__ == "__main__":
    raise SystemExit(main())
