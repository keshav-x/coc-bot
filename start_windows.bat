@echo off
title ApexClash Pro - 1-Click Launcher
cd /d "%~dp0"

echo =======================================================
echo    ⚡ ApexClash Pro - Windows 1-Click Launcher
echo =======================================================


if not exist ".venv\Scripts\activate.bat" (
    echo [*] First time setup detected. Creating virtual environment...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    python -m pip install --upgrade pip wheel setuptools
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)

echo [*] Starting Clash AutoLoot...
python main.py %*
