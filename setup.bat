@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_CMD=py -3.11"
%PYTHON_CMD% -c "import sys; assert sys.version_info[:2] == (3, 11)" >nul 2>nul
if errorlevel 1 (
    set "PYTHON_CMD=python"
    python -c "import sys; assert sys.version_info[:2] == (3, 11)" >nul 2>nul
    if errorlevel 1 (
        echo Error: Python 3.11 is required.
        echo Install Python 3.11 and make it available through py or python.
        pause
        exit /b 1
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 goto :error
)

echo Installing dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :error
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo.
echo Setup completed. Start the application with run.bat.
pause
exit /b 0

:error
echo.
echo Setup failed. Review the messages above.
pause
exit /b 1
