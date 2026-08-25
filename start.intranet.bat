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

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\scripts\install_verify.ps1" -ProjectRoot "%CD%" -StartMode process -ForceKillPortProcess -SkipDataChecks
if errorlevel 1 (
    echo [ERROR] Verified backend restart failed.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\scripts\start_intranet_frontend.ps1" -ProjectRoot "%CD%" -ForceKillPortProcess
if errorlevel 1 (
    echo [ERROR] Frontend restart failed.
    pause
    exit /b 1
)

echo.
echo Verified startup complete.
echo Backend:  http://127.0.0.1:8000
echo Frontend: http://127.0.0.1:5173
pause
