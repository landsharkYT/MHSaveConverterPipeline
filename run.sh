#!/usr/bin/env bash
# Launcher for the MH Save Converter Pipeline (Linux/macOS).
# Ensures a local .venv with the Python deps, then runs the app.
# Rust / save3ds are built from the app's [4] Install Dependencies menu.
set -euo pipefail

# Always work from the repo root (this script's directory).
cd "$(dirname "$0")"

VENV=".venv"
LOCK="$VENV/.requirements.lock"
CONVERTER="MHXXGUSaveConvert/MHGU-MHXX-Save-Converter-Script/modules/converter_api.py"

# 1. Pick a Python interpreter.
if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "Error: Python 3 not found. Install Python 3.8+ and try again." >&2
  exit 1
fi

# 2. Initialize submodules if the converter is missing (only in a git checkout).
if [ ! -e "$CONVERTER" ] && [ -e ".git" ] && command -v git >/dev/null 2>&1; then
  echo "Initializing git submodules..."
  git submodule update --init
fi

# 3. Create the virtual environment if needed.
if [ ! -x "$VENV/bin/python" ]; then
  echo "Creating virtual environment in $VENV ..."
  "$PY" -m venv "$VENV"
fi
VPY="$VENV/bin/python"

# 4. (Re)install requirements when they change (stamp compare).
if [ ! -f "$LOCK" ] || ! cmp -s requirements.txt "$LOCK"; then
  echo "Installing Python dependencies ..."
  "$VPY" -m pip install --upgrade pip >/dev/null 2>&1 || true
  "$VPY" -m pip install -r requirements.txt
  cp requirements.txt "$LOCK"
fi

# 5. Launch the app (forward any extra arguments).
exec "$VPY" -m mhpipeline "$@"
