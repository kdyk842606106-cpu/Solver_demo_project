@echo off
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"

echo ============================================
echo   Planner Adapter - Verified Local Start
echo ============================================
echo Project: %CD%
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [INFO] Isolated runtime not found. Running bootstrap first...
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\scripts\bootstrap_dev.ps1" -ProjectRoot "%CD%"
    if errorlevel 1 (
        echo [ERROR] Bootstrap failed.
        pause
        exit /b 1
    )
)

for /f %%G in ('git -C "%CD%" rev-parse HEAD 2^>nul') do set EXPECTED_COMMIT=%%G

echo [INFO] Replacing previous services on ports 8000 and 5173...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\scripts\install_verify.ps1" -ProjectRoot "%CD%" -StartMode process -ForceKillPortProcess -SkipDataChecks -ExpectedCommit "%EXPECTED_COMMIT%"
if errorlevel 1 (
    echo [ERROR] Backend verified restart failed.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\scripts\start_intranet_frontend.ps1" -ProjectRoot "%CD%" -ForceKillPortProcess
if errorlevel 1 (
    echo [ERROR] Frontend verified restart failed.
    pause
    exit /b 1
)

echo.
echo Planner adapter startup complete.
echo Commit:   %EXPECTED_COMMIT%
echo Backend:  http://127.0.0.1:8000
echo Frontend: http://127.0.0.1:5173
pause
