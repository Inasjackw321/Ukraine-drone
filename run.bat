@echo off
cd /d "%~dp0"
title Ukraine Drone Map
mode con cols=70 lines=40
color 0B

echo.
echo  =====================================================
echo   UKRAINE DRONE MAP
echo  =====================================================
echo.

:: Find Python - try py launcher first, then python, then python3
set PYTHON=
py --version >nul 2>&1
if not errorlevel 1 ( set PYTHON=py & goto :found_python )
python --version >nul 2>&1
if not errorlevel 1 ( set PYTHON=python & goto :found_python )
python3 --version >nul 2>&1
if not errorlevel 1 ( set PYTHON=python3 & goto :found_python )

echo  [ERROR] Python is not installed or not on PATH.
echo  Download from: https://www.python.org/downloads/
echo  IMPORTANT: tick "Add Python to PATH" when installing.
echo.
pause & exit /b 1

:found_python
%PYTHON% --version
echo.

:: Auto-update if this is a git repo
git --version >nul 2>&1
if not errorlevel 1 (
    if exist ".git\" (
        echo  Checking for updates...
        git pull origin main
        echo.
    )
)

:: Install / update dependencies automatically
echo  Checking dependencies...
%PYTHON% -m pip install -r requirements.txt --quiet --no-warn-script-location
echo  Dependencies OK.
echo.

:: Run the app
echo  Starting app...
echo  =====================================================
echo.
%PYTHON% app.py %*

echo.
echo  =====================================================
echo   App has closed.  Check above for any error messages.
echo  =====================================================
pause
