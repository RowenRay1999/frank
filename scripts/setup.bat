@echo off
REM Frank (弗兰克) — 开发环境一键安装脚本
REM 创建 Python 虚拟环境 + 安装依赖 + npm install

echo ============================================
echo  Frank (弗兰克) — 开发环境安装
echo ============================================
echo.

cd /d "%~dp0\.."

REM 检查 Python
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.11+
    pause
    exit /b 1
)

echo [1/3] 创建 Python 虚拟环境...
if exist .venv\ (
    echo   虚拟环境已存在，跳过创建
) else (
    python -m venv .venv
    echo   虚拟环境创建完成
)

echo [2/3] 安装 Python 依赖...
call .venv\Scripts\python.exe -m pip install --upgrade pip -q
call .venv\Scripts\python.exe -m pip install -r src\python\requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo [警告] 部分依赖安装失败，请检查网络连接后重试
)

echo [3/3] 安装 Node.js 依赖...
where npm >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [错误] 未找到 npm，请先安装 Node.js 20+
    pause
    exit /b 1
)
call npm install
if %ERRORLEVEL% NEQ 0 (
    echo [警告] npm install 失败，请检查网络连接后重试
)

echo.
echo ============================================
echo  安装完成！运行 scripts\dev.bat 启动开发模式
echo ============================================
pause
