@echo off
title Clash AutoLoot - 1-Click Launcher
cd /d "%~dp0"

echo =======================================================
echo    ⚡ Clash AutoLoot - Windows 1-Click Launcher
echo =======================================================

if exist "dist\ClashAutoLoot\ClashAutoLoot.exe" (
    echo [*] Starting compiled Clash AutoLoot...
    start "" "dist\ClashAutoLoot\ClashAutoLoot.exe"
    exit /b
)

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
