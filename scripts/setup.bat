@echo off
REM Frank - One-Click Dev Environment Setup
REM Create Python venv + install dependencies + npm install

echo ============================================
echo   Frank - Environment Setup
echo ============================================
echo.

cd /d "%~dp0\.."

REM Check Python
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python not found. Please install Python 3.11+ first.
    pause
    exit /b 1
)

echo [1/3] Creating Python virtual environment...
if exist .venv\ (
    echo   Virtual environment already exists, skipping.
) else (
    python -m venv .venv
    echo   Virtual environment created.
)

echo [2/3] Installing Python dependencies...
call .venv\Scripts\python.exe -m pip install --upgrade pip -q
call .venv\Scripts\python.exe -m pip install -r src\python\requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo [WARNING] Some Python dependencies failed to install. Check network and retry.
)

echo [3/3] Installing Node.js dependencies...
where npm >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] npm not found. Please install Node.js 20+ first.
    pause
    exit /b 1
)
call npm install
if %ERRORLEVEL% NEQ 0 (
    echo [WARNING] npm install failed. Check network and retry.
)

echo.
echo ============================================
echo   Setup complete! Run scripts\dev.bat to start.
echo ============================================
pause
