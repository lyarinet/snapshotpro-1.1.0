#!/usr/bin/env bash
set -eu
cd "$(dirname "$0")"
python3 -m venv .venv
CC="${CC:-gcc}" .venv/bin/python -m pip install -r requirements.txt
exec .venv/bin/python snapshot_pro.py "$@"
