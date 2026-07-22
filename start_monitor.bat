@echo off
setlocal
cd /d "%~dp0"

if not exist "%~dp0config.json" (
    echo [ERROR] config.json was not found.
    echo Please create it first or run the monitor once to generate default settings.
    pause
    exit /b 1
)

rem Prefer default-py312 shared environment, launch hidden via PowerShell
set "DEFAULT_PY=E:\DevTools\Python\envs\default-py312\Scripts\python.exe"
if exist "%DEFAULT_PY%" (
    powershell -NoProfile -Command "Start-Process -FilePath '%DEFAULT_PY%' -ArgumentList '\"%~dp0settings_gui.py\"' -WindowStyle Hidden"
    exit /b 0
)

rem Fallback: find python via PATH
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found in PATH.
    echo Install Python or add it to PATH and try again.
    pause
    exit /b 1
)

powershell -NoProfile -Command "Start-Process -FilePath 'python' -ArgumentList '\"%~dp0settings_gui.py\"' -WindowStyle Hidden"
exit /b %ERRORLEVEL%
