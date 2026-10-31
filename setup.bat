@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_CMD=py -3.11"
%PYTHON_CMD% -c "import sys; assert sys.version_info[:3] == (3, 11, 9)" >nul 2>nul
if errorlevel 1 (
    set "PYTHON_CMD=python"
    python -c "import sys; assert sys.version_info[:3] == (3, 11, 9)" >nul 2>nul
    if errorlevel 1 (
        echo Error: Python 3.11.9 is required.
        echo Install Python 3.11.9 and make it available through py or python.
        pause
        exit /b 1
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 goto :error
)

".venv\Scripts\python.exe" -c "import sys; assert sys.version_info[:3] == (3, 11, 9)"
if errorlevel 1 (
    echo Existing .venv must use Python 3.11.9. Rename it and run setup again.
    goto :error
)
echo Installing pinned dependencies...
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
