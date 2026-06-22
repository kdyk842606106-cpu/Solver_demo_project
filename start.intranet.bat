@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

echo ============================================
echo   Integration Planning Solver - Intranet Dev
echo ============================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [INFO] Virtual environment not found. Running bootstrap first...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\scripts\bootstrap_dev.ps1" -ProjectRoot "%CD%"
    if errorlevel 1 (
        echo [ERROR] Bootstrap failed.
        pause
        exit /b 1
    )
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\scripts\launch_dev.ps1" -Mode intranet -ProjectRoot "%CD%"
if errorlevel 1 (
    echo [ERROR] Launch failed.
    pause
    exit /b 1
)

echo.
echo Startup requested. Backend and frontend should be launching.
pause
