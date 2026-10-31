@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run setup.bat first.
    exit /b 1
)
".venv\Scripts\python.exe" -c "import sys; assert sys.version_info[:3] == (3, 11, 9)"
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" tools\build_windows.py
exit /b %errorlevel%
