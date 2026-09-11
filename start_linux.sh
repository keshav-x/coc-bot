#!/usr/bin/env bash
# ==============================================================================
# ApexClash Pro — Linux & Raspberry Pi 1-Click Launcher
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="$SCRIPT_DIR/.venv"

# If not installed yet, run 1-click installer first
if [ ! -d "$VENV_DIR" ] || [ ! -f "$VENV_DIR/bin/activate" ]; then
    echo "[*] First time launch detected. Running 1-click installer..."
    bash "$SCRIPT_DIR/install_linux.sh" --no-run
fi

# Activate virtual environment
source "$VENV_DIR/bin/activate"

# Launch Application
exec python3 "$SCRIPT_DIR/main.py" "$@"
