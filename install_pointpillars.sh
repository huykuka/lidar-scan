#!/bin/bash
# install_pointpillars.sh -- Automated installer for zhulf0804/PointPillars
# Installs PointPillars as a Python package in a dedicated Python 3.8+ venv.
# Usage: bash install_pointpillars.sh [install_dir]

set -e

PP_REPO=https://github.com/zhulf0804/PointPillars.git
VENVDIR=pointpillars-venv
if [ -n "$1" ]; then
  VENVDIR="$1"
fi

PYTHON_BIN=$(command -v python3.8 || command -v python3.9 || command -v python3)

if ! "$PYTHON_BIN" --version | grep -q '3.8\|3.9'; then
  echo "[ERROR] PointPillars requires Python 3.8 or 3.9. Please install Python 3.8/3.9 and re-run this script." >&2
  exit 1
fi

if [ ! -d "$VENVDIR" ]; then
  echo "[INFO] Creating Python venv at $VENVDIR..."
  "$PYTHON_BIN" -m venv "$VENVDIR"
fi
source "$VENVDIR/bin/activate"

if [ ! -d "PointPillars" ]; then
  echo "[INFO] Cloning PointPillars repository..."
  git clone "$PP_REPO"
fi
cd PointPillars

pip install --upgrade pip
pip install -r requirements.txt
python setup.py build_ext --inplace
pip install .

echo "[SUCCESS] PointPillars installed in venv: $VENVDIR"
echo "To activate: source $VENVDIR/bin/activate"