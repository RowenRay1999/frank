@echo off
REM Frank (弗兰克) — 开发模式启动脚本
REM 启动 Python 推理服务 + Electron 开发模式

cd /d "%~dp0\.."

echo ============================================
echo  Frank (弗兰克) — 开发模式
echo ============================================
echo.

REM 检查虚拟环境
if not exist .venv\Scripts\python.exe (
    echo [错误] 未找到虚拟环境，请先运行 scripts\setup.bat
    pause
    exit /b 1
)

REM 检查 node_modules
if not exist node_modules\ (
    echo [错误] 未找到 node_modules，请先运行 scripts\setup.bat
    pause
    exit /b 1
)

REM 创建日志目录
if not exist logs\ mkdir logs

echo 启动 Electron 应用...
echo (Python 推理服务将由 Electron 自动管理)
echo.

call npm run dev

pause
