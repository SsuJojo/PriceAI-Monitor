@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [提示] 监控入口已整合至 start_monitor.bat，正在启动...
call "%~dp0start_monitor.bat"

