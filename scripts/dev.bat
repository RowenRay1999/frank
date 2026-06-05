@echo off
REM Frank - Development Mode Launcher
REM Start Python inference service + Electron dev mode

cd /d "%~dp0\.."

echo ============================================
echo   Frank - Development Mode
echo ============================================
echo.

REM Check virtual environment
if not exist .venv\Scripts\python.exe (
    echo [ERROR] Virtual environment not found. Please run scripts\setup.bat first.
    pause
    exit /b 1
)

REM Check node_modules
if not exist node_modules\ (
    echo [ERROR] node_modules not found. Please run scripts\setup.bat first.
    pause
    exit /b 1
)

REM Create logs directory
if not exist logs\ mkdir logs

echo Starting Electron app...
echo (Python inference service will be auto-managed by Electron)
echo.

call npm run dev

pause
