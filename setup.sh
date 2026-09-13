#!/usr/bin/env bash

set -e

SCRIPT_DIR="$(
    cd "$(dirname "${BASH_SOURCE[0]}")"
    pwd
)"

cd "$SCRIPT_DIR"

echo "============================================================"
echo "                  NETOPS LAB SETUP"
echo "============================================================"
echo

if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: python3 is required."
    exit 1
fi

echo "[1/3] Creating Python virtual environment..."

if [[ ! -d ".venv-wsl" ]]; then
    python3 -m venv .venv-wsl
else
    echo "Virtual environment already exists."
fi

echo
echo "[2/3] Installing Python dependencies..."

.venv-wsl/bin/python \
    -m pip install \
    --upgrade pip

.venv-wsl/bin/python \
    -m pip install \
    -r requirements.txt

echo
echo "[3/3] Setup complete."
echo
echo "Next:"
echo
echo "    ./start_netops.sh"
echo
