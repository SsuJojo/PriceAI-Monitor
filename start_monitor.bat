@echo off
setlocal
cd /d "%~dp0"

if not exist "%~dp0config.json" (
    if exist "%~dp0config.example.json" (
        copy "%~dp0config.example.json" "%~dp0config.json" >nul
    )
)

rem 1. Prefer local uv virtual environment
if exist "%~dp0.venv\Scripts\python.exe" (
    powershell -NoProfile -Command "Start-Process -FilePath '%~dp0.venv\Scripts\python.exe' -ArgumentList '\"%~dp0settings_gui.py\"' -WindowStyle Hidden"
    exit /b 0
)

rem 2. Try uv run if uv is available
where uv >nul 2>nul
if %ERRORLEVEL% equ 0 (
    powershell -NoProfile -Command "Start-Process -FilePath 'uv' -ArgumentList 'run python \"%~dp0settings_gui.py\"' -WindowStyle Hidden"
    exit /b 0
)

rem 3. Fallback: find python via PATH
where python >nul 2>nul
if %ERRORLEVEL% equ 0 (
    powershell -NoProfile -Command "Start-Process -FilePath 'python' -ArgumentList '\"%~dp0settings_gui.py\"' -WindowStyle Hidden"
    exit /b 0
)

echo [ERROR] 未找到可用的 Python 或 uv 运行环境。
echo 请先安装 uv 或 Python 并添加到 PATH。
pause
exit /b 1
