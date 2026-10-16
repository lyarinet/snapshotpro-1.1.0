#!/usr/bin/env python3
"""Explicit source launcher. Runtime startup never installs packages."""
import importlib.util
import os
from pathlib import Path
import sys

if __name__ == '__main__':
    if importlib.util.find_spec('PyQt6') is None:
        print('Run Run_Setup.bat (Windows) or Setup_Auto_Install_Mac_Linux.sh first.')
        raise SystemExit(1)
    script = Path(__file__).resolve().with_name('snapshot_pro.py')
    os.execv(sys.executable, [sys.executable, str(script), *sys.argv[1:]])
