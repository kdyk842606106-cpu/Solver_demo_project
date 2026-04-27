@echo off
set PYTHONIOENCODING=utf-8

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\scripts\launch_dev.ps1" -Mode docker
if errorlevel 1 (
    echo [ERROR] Docker launch failed.
    pause
    exit /b 1
)

pause
