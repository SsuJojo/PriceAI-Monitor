@echo off
setlocal
cd /d "%~dp0"

set "PYTHON=python"

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found in PATH.
    echo Install Python or add it to PATH and try again.
    pause
    exit /b 1
)

if not exist "%~dp0config.json" (
    echo config.json was not found. Creating it from config.example.json...
    copy /Y "%~dp0config.example.json" "%~dp0config.json" >nul
    if errorlevel 1 (
        echo [ERROR] Failed to create config.json.
        pause
        exit /b 1
    )
)

for /f "delims=" %%I in ('"%PYTHON%" -c "import sys; print(sys.executable)"') do set "PYTHON_EXE=%%I"
for %%I in ("%PYTHON_EXE%") do set "PYTHONW=%%~dpIpythonw.exe"

if exist "%PYTHONW%" (
    start "" "%PYTHONW%" "%~dp0settings_gui.py"
    exit /b 0
)

"%PYTHON%" "%~dp0settings_gui.py"
exit /b %ERRORLEVEL%
