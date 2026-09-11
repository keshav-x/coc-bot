#!/usr/bin/env bash
# ==============================================================================
# Clash AutoLoot — macOS 1-Click Installer (Double-Clickable in Finder)
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "======================================================="
echo "   ⚡ Clash AutoLoot — macOS 1-Click Setup"
echo "======================================================="

# Check Python 3
if ! command -v python3 >/dev/null 2>&1; then
    echo "[!] Python 3 was not found on your Mac."
    echo "[*] Opening Python download page..."
    open "https://www.python.org/downloads/"
    read -p "Press [Enter] once Python is installed..."
fi

# Optional Homebrew setup for Tesseract OCR
if command -v brew >/dev/null 2>&1; then
    echo "[*] Homebrew detected. Ensuring Tesseract OCR is installed..."
    brew install tesseract || true
else
    echo "[*] Tip: Install Homebrew (https://brew.sh) and run 'brew install tesseract' for optimal OCR accuracy."
fi

# Create Virtual Environment
VENV_DIR="$SCRIPT_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "[*] Creating virtual environment at $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
fi

# Activate & Install requirements
source "$VENV_DIR/bin/activate"

echo "[*] Upgrading pip & wheel..."
pip install --upgrade pip wheel setuptools --quiet

echo "[*] Installing dependencies from requirements.txt..."
pip install -r requirements.txt

# Grant executable permissions
chmod +x "$SCRIPT_DIR/start_mac.command" 2>/dev/null || true
chmod +x "$SCRIPT_DIR/install_mac.command" 2>/dev/null || true

echo ""
echo "======================================================="
echo "   ✅ Installation Complete!"
echo "======================================================="
echo "You can launch Clash AutoLoot at any time by simply"
echo "double-clicking 'start_mac.command' in Finder!"
echo "======================================================="
echo ""

if [ "$1" != "--no-run" ]; then
    echo "[*] Starting Clash AutoLoot..."
    exec "$SCRIPT_DIR/start_mac.command"
fi
