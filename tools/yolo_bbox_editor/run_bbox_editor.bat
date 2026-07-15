@echo off
REM YOLO BBox Editor launcher — uses project .venv
set ROOT=%~dp0..\..

REM Resolve ROOT to absolute path (handles spaces, Cyrillic)
for %%i in ("%ROOT%") do set "ROOT=%%~fi"

REM Activate .venv if it exists
if exist "%ROOT%\.venv\Scripts\python.exe" (
    set "PYTHON=%ROOT%\.venv\Scripts\python.exe"
) else if exist "%ROOT%\venv\Scripts\python.exe" (
    set "PYTHON=%ROOT%\venv\Scripts\python.exe"
) else (
    echo ERROR: No virtual environment found at %ROOT%
    echo Run start_ed_ap.bat first to create it.
    pause
    exit /b 1
)

echo Using: %PYTHON%
"%PYTHON%" "%~dp0main.py"
pause
