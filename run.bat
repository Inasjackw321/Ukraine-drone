@echo off
cd /d "%~dp0"
title Ukraine Drone Map
mode con cols=70 lines=35
color 0B

echo.
echo  =====================================================
echo   UKRAINE DRONE MAP
echo  =====================================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Python is not installed or not on PATH.
    echo.
    echo  Download from: https://www.python.org/downloads/
    echo  IMPORTANT: tick "Add Python to PATH" when installing.
    echo.
    pause
    exit /b 1
)

python --version
echo.

:: Install / update dependencies automatically
echo  Checking dependencies...
pip install -r requirements.txt --quiet --no-warn-script-location
echo  Dependencies OK.
echo.

:: Run the app
echo  Starting app...
echo  =====================================================
echo.
python app.py %*

:: Always pause so the window stays open and errors are readable
echo.
echo  =====================================================
echo   App has closed.  Check above for any error messages.
echo  =====================================================
pause
