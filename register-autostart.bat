@echo off
REM ================================================
REM ChatGPT Plus 价格监控器 - 开机自启注册脚本
REM 位置：C:\Users\SsuJo_\Documents\GitHub\PriceAI-Monitor\
REM ================================================

chcp 65001 >nul
title 价格监控器 - 开机自启注册

echo.
echo 正在注册 ChatGPT Plus 价格监控器开机自启...
echo 当前路径: %cd%

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo 错误：未找到 Python 3.14，请先安装 Python。
    pause
    exit /b 1
)

set STARTUP_PATH=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
if not exist "%STARTUP_PATH%" (
    mkdir "%STARTUP_PATH%"
)

set BAT_PATH=%cd%\monitor.bat
set LINK=%STARTUP_PATH%\ChatGPTPlus_Price_Monitor.lnk
echo 正在创建开机启动链接...

powershell -Command ^
    "$ws = New-Object -ComObject WScript.Shell; " ^
    "$lnk = $ws.CreateShortcut('%LINK%'); " ^
    "$lnk.TargetPath = '%BAT_PATH%'; " ^
    "$lnk.WorkingDirectory = '%cd%'; " ^
    "$lnk.Description = 'ChatGPT Plus 价格监控器（无账号过滤版）'; " ^
    "$lnk.IconLocation = 'python.exe'; " ^
    "$lnk.Save(); " ^
    "Write-Host '✓ 开机自启已注册：%LINK%'"

echo.
echo 注册完成！
echo.
echo 启动方式：
echo   1. 手动：双击 monitor.bat（命令行窗口常驻显示日志）
echo   2. 开机：已注册到「启动文件夹」
echo.
pause
