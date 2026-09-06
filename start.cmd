@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Python environment missing. See README.md for setup instructions.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" scripts\check_environment.py
if errorlevel 1 (
    echo Environment check failed. See the error above and README.md.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" scripts\launch_app.py
if errorlevel 1 (
    echo Startup failed. Please copy the error above.
    pause
    exit /b 1
)
