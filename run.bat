@echo off
cd /d "%~dp0"
title Ukraine Drone Map

python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  ERROR: Python not found.
    echo  Download it from https://www.python.org/downloads/
    echo  Make sure to tick "Add Python to PATH" during install.
    echo.
    pause
    exit /b 1
)

python app.py %*
if errorlevel 1 (
    echo.
    echo  The app exited with an error. See above for details.
    pause
)
