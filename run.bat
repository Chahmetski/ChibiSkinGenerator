@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Virtual environment not found. Run setup.bat first.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -c "import sys; assert sys.version_info[:3] == (3, 11, 9)" >nul 2>nul
if errorlevel 1 (
    echo Python 3.11.9 is required. Recreate .venv with setup.bat.
    pause
    exit /b 1
)

set "PYTHONPATH=%~dp0src"
".venv\Scripts\python.exe" -m chibi_skin_generator
if errorlevel 1 (
    echo.
    echo Application finished with an error.
    pause
)
