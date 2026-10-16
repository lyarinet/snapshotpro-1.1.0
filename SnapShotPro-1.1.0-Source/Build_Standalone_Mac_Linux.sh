#!/usr/bin/env bash
set -eu
cd "$(dirname "$0")"
python3 -m venv .venv-build
CC="${CC:-gcc}" .venv-build/bin/python -m pip install -r requirements-build.txt
.venv-build/bin/python build_all.py "$@"
