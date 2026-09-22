@echo off
cd /d "%~dp0"
title PharaohScan and Explorer Launcher

echo ===================================================
echo PharaohScan and Explorer - Unified System Launcher
echo ===================================================
echo.

:: ── 1. Check Python Dependencies ──
echo [1/3] Checking python packages...

python -c "import flask" 2>nul
if %errorlevel% neq 0 (
    echo   Installing flask...
    pip install flask
)

python -c "import flask_socketio" 2>nul
if %errorlevel% neq 0 (
    echo   Installing flask-socketio...
    pip install flask-socketio
)

python -c "import flask_cors" 2>nul
if %errorlevel% neq 0 (
    echo   Installing flask-cors...
    pip install flask-cors
)

python -c "import pymongo" 2>nul
if %errorlevel% neq 0 (
    echo   Installing pymongo and dnspython...
    pip install pymongo dnspython
)

python -c "import ultralytics" 2>nul
if %errorlevel% neq 0 (
    echo   Installing ultralytics...
    pip install ultralytics
)

python -c "import cv2" 2>nul
if %errorlevel% neq 0 (
    echo   Installing opencv-python...
    pip install opencv-python
)

python -c "import numpy" 2>nul
if %errorlevel% neq 0 (
    echo   Installing numpy...
    pip install numpy
)

python -c "import PIL" 2>nul
if %errorlevel% neq 0 (
    echo   Installing pillow...
    pip install pillow
)

python -c "import google.generativeai" 2>nul
if %errorlevel% neq 0 (
    echo   Installing google-generativeai...
    pip install google-generativeai
)

python -c "import yaml" 2>nul
if %errorlevel% neq 0 (
    echo   Installing pyyaml...
    pip install pyyaml
)

echo [SUCCESS] All Python dependencies verified!
echo.

:: ── 2. Launch UI Browser ──
echo [2/3] Launching web browser view...
start "" http://localhost:5000

:: ── 3. Start Unified Server ──
echo [3/3] Starting PharaohScan integrated server on port 5000...
python app.py
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Server terminated unexpectedly.
    pause
    exit /b %errorlevel%
)

pause
