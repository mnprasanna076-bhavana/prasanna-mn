@echo off
echo ========================================================
echo         Starting PocketSmart AI Budget Planner
echo ========================================================

REM Navigate to project root directory
cd /d "%~dp0"

REM Check for virtual environment
IF NOT EXIST "venv\Scripts\activate.bat" (
    echo Creating virtual environment...
    python -m venv venv
)

echo Activating virtual environment...
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
)

echo Checking and installing dependencies...
venv\Scripts\pip.exe install -r requirements.txt

echo.
echo Starting FastAPI Web Server...
echo Access the application in your browser once the server starts.
echo.
venv\Scripts\python.exe app.py
pause
