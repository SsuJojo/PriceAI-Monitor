@echo off
REM ================================================
REM ChatGPT Plus 价格监控器 - 手动启动脚本
REM 位置：C:\Users\SsuJo_\Documents\GitHub\PriceAI-Monitor\
REM ================================================

chcp 65001 >nul
title ChatGPT Plus 价格监控器

echo.
echo 正在启动监控器...
cd /d "%~dp0"
python -X utf8 monitor.py
pause
