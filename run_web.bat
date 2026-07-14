@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

REM EDAPGui launch script (uses .venv, Python 3.11)

if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment not found, creating .venv...

    py -3.11 --version >nul 2>&1
    if %errorlevel% == 0 (
        py -3.11 -m venv .venv
    ) else (
        echo Python 3.11 not found via py launcher.
        echo Please install Python 3.11 from https://www.python.org/downloads/ and try again.
        pause
        exit /b 1
    )

    if not exist ".venv\Scripts\python.exe" (
        echo Error: Failed to create virtual environment.
        pause
        exit /b 1
    )

    echo Installing requirements, this may take a while...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt

    if %errorlevel% neq 0 (
        echo Error: Failed to install requirements.
        pause
        exit /b 1
    )

    echo Setup complete!
)

echo Starting edap_headless...
".venv\Scripts\python.exe" edap_headless.py --host 0.0.0.0 --port 8090 --log-level info

pause
