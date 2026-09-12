#!/usr/bin/env bash
# ==============================================================================
# Clash AutoLoot — Linux & Raspberry Pi 1-Click Installer
# Supports: Ubuntu, Debian, Raspberry Pi OS (ARM64 / aarch64 / armv7l), Fedora, Arch
# ==============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "======================================================="
echo "   ⚡ ApexClash Pro — 1-Click Linux & Raspberry Pi Setup"
echo "======================================================="

# Detect System & Architecture
ARCH="$(uname -m)"
OS_NAME="Linux"
IS_RPI=false

if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS_NAME="$NAME"
fi

if [ -f /proc/device-tree/model ] && grep -qi "Raspberry Pi" /proc/device-tree/model 2>/dev/null; then
    IS_RPI=true
elif [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "armv7l" ]; then
    IS_RPI=true
fi

echo "[*] Detected OS: $OS_NAME ($ARCH)"
if [ "$IS_RPI" = true ]; then
    echo "[*] Device detected: Raspberry Pi / ARM architecture ($ARCH)"
fi

# Function: Install system libraries via package manager
install_system_deps() {
    echo "[*] Checking and installing required system dependencies..."
    SUDO_CMD=""
    if [ "$EUID" -ne 0 ]; then
        if command -v sudo >/dev/null 2>&1; then
            SUDO_CMD="sudo"
        else
            echo "[!] Note: sudo not available. Please ensure system packages are installed."
        fi
    fi

    if command -v apt-get >/dev/null 2>&1; then
        echo "[*] Detected Debian / Ubuntu / Raspberry Pi OS (apt)..."
        if [ -n "$SUDO_CMD" ] || [ "$EUID" -eq 0 ]; then
            $SUDO_CMD apt-get update -y || true
            $SUDO_CMD apt-get install -y \
                python3 \
                python3-pip \
                python3-venv \
                python3-dev \
                libgl1 \
                libglib2.0-0 \
                libxkbcommon-x11-0 \
                libegl1 \
                libxcb-cursor0 \
                tesseract-ocr \
                libtesseract-dev || true

            # On Raspberry Pi OS, also install system PySide6 if available
            if [ "$IS_RPI" = true ]; then
                $SUDO_CMD apt-get install -y python3-pyside6 python3-opencv || true
            fi
        fi
    elif command -v dnf5 >/dev/null 2>&1; then
        echo "[*] Detected Fedora / RHEL (dnf5)..."
        $SUDO_CMD dnf5 install -y \
            python3 \
            python3-pip \
            python3-devel \
            mesa-libGL \
            glib2 \
            libxkbcommon-x11 \
            xcb-util-cursor \
            tesseract \
            tesseract-devel || true
    elif command -v dnf >/dev/null 2>&1; then
        echo "[*] Detected Fedora / RHEL (dnf)..."
        $SUDO_CMD dnf install -y \
            python3 \
            python3-pip \
            python3-devel \
            mesa-libGL \
            glib2 \
            libxkbcommon-x11 \
            xcb-util-cursor \
            tesseract \
            tesseract-devel || true
    elif command -v pacman >/dev/null 2>&1; then
        echo "[*] Detected Arch Linux (pacman)..."
        $SUDO_CMD pacman -Sy --noconfirm python python-pip mesa glib2 libxkbcommon xcb-util-cursor tesseract || true
    else
        echo "[!] Warning: Unknown package manager. Please ensure Python 3, Qt dependencies (libxkbcommon, xcb-util-cursor), and Tesseract are installed."
    fi
}

# Ask or install system dependencies
if [ "$1" != "--skip-sys" ]; then
    install_system_deps
fi

# Ensure Python 3 is present
if ! command -v python3 >/dev/null 2>&1; then
    echo "[!] Error: python3 is not installed. Please install Python 3.9+ and re-run."
    exit 1
fi

PY_VER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
echo "[*] Found Python $PY_VER"

# Create Virtual Environment
VENV_DIR="$SCRIPT_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "[*] Creating virtual environment at $VENV_DIR..."
    # If on Raspberry Pi, allow system site packages in case PySide6 or OpenCV was installed via apt
    if [ "$IS_RPI" = true ]; then
        python3 -m venv --system-site-packages "$VENV_DIR" || python3 -m venv "$VENV_DIR"
    else
        python3 -m venv "$VENV_DIR"
    fi
fi

# Activate Virtual Environment
source "$VENV_DIR/bin/activate"

echo "[*] Upgrading pip & wheel..."
pip install --upgrade pip wheel setuptools --quiet

# Install Python requirements
echo "[*] Installing Python dependencies from requirements.txt..."
if ! pip install -r requirements.txt; then
    if [ "$IS_RPI" = true ]; then
        echo "[!] Note: Standard pip install encountered an issue on ARM. Retrying with compatible flags..."
        pip install --upgrade pip
        pip install -r requirements.txt --extra-index-url https://www.piwheels.org/simple || true
    else
        echo "[!] Error installing requirements. Please check above logs."
        exit 1
    fi
fi

# Ensure executable permissions on launcher scripts
chmod +x "$SCRIPT_DIR/start_linux.sh" 2>/dev/null || true
chmod +x "$SCRIPT_DIR/install_linux.sh" 2>/dev/null || true

# Create Desktop Shortcut (.desktop entry)
create_desktop_shortcut() {
    ICON_PATH="$SCRIPT_DIR/assets/apex_clash_logo.png"
    if [ ! -f "$ICON_PATH" ]; then
        ICON_PATH=""
    fi

    DESKTOP_ENTRY="[Desktop Entry]
Name=ApexClash Pro
Comment=Autonomous Combat & Farming Suite for Clash of Clans
Exec=\"$SCRIPT_DIR/start_linux.sh\"
Icon=$ICON_PATH
Terminal=false
Type=Application
Categories=Game;Utility;
StartupNotify=true"

    # Application Menu entry
    APPS_DIR="$HOME/.local/share/applications"
    mkdir -p "$APPS_DIR"
    echo "$DESKTOP_ENTRY" > "$APPS_DIR/ApexClashPro.desktop"
    chmod +x "$APPS_DIR/ApexClashPro.desktop"
    echo "[*] Installed application launcher to: $APPS_DIR/ApexClashPro.desktop"

    # Desktop shortcut (if ~/Desktop exists)
    if [ -d "$HOME/Desktop" ]; then
        echo "$DESKTOP_ENTRY" > "$HOME/Desktop/ApexClashPro.desktop"
        chmod +x "$HOME/Desktop/ApexClashPro.desktop"
        # On modern GNOME / Ubuntu / Pi OS, allow launching
        if command -v gio >/dev/null 2>&1; then
            gio set "$HOME/Desktop/ApexClashPro.desktop" metadata::trusted true 2>/dev/null || true
        fi
        echo "[*] Created Desktop icon at: $HOME/Desktop/ApexClashPro.desktop"
    fi
}

create_desktop_shortcut

echo ""
echo "======================================================="
echo "   ✅ Installation Complete!"
echo "======================================================="
echo "You can now run ApexClash Pro at any time by:"
echo "  1. Double-clicking the 'ApexClash Pro' Desktop icon"
echo "  2. Running: ./start_linux.sh"
echo "======================================================="
echo ""

# If user executed directly and wants to run now
if [ -t 0 ] && [ "$1" != "--no-run" ]; then
    read -p "Would you like to start ApexClash Pro now? [Y/n] " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
        exec "$SCRIPT_DIR/start_linux.sh"
    fi
fi
