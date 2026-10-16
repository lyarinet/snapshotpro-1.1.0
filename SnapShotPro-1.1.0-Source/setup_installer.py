#!/usr/bin/env python3
"""Explicit source setup; install into the project virtual environment."""
from pathlib import Path
import os
import subprocess
import sys
import venv

if __name__ == '__main__':
    root = Path(__file__).resolve().parent
    environment = root / '.venv'
    venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(root / 'requirements.txt')], check=True)
    subprocess.run([str(python), str(root / 'snapshot_pro.py')], check=True)
