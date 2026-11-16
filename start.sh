#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then python3 -m venv .venv; fi
.venv/bin/python -m pip install -c requirements-tested.txt .
exec .venv/bin/open-comfy-studio --data ./studio-data
