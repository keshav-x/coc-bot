#!/usr/bin/env bash
# ==============================================================================
# Clash AutoLoot — macOS 1-Click Launcher (Double-Clickable in Finder)
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR="$SCRIPT_DIR/.venv"

echo "======================================================="
echo "   ⚡ Clash AutoLoot — macOS Launcher"
echo "======================================================="

# If virtual environment is missing, run installer automatically
if [ ! -d "$VENV_DIR" ] || [ ! -f "$VENV_DIR/bin/activate" ]; then
    echo "[*] First run detected. Initializing 1-click setup..."
    bash "$SCRIPT_DIR/install_mac.command" --no-run
fi

# Activate virtual environment
source "$VENV_DIR/bin/activate"

# Launch Application
exec python3 "$SCRIPT_DIR/main.py" "$@"
