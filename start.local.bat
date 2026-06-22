@echo off
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\scripts\launch_dev.ps1" -Mode local -ProjectRoot "%CD%"
if errorlevel 1 (
    echo [ERROR] Local launch failed.
    pause
    exit /b 1
)

pause
