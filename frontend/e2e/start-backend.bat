@echo off
setlocal
set PYTHONIOENCODING=utf-8

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "PROJECT_ROOT=%%~fI"
cd /d "%PROJECT_ROOT%"

set "PROJECT_ROOT_URL=%PROJECT_ROOT:\=/%"
set "DATABASE_URL=sqlite+aiosqlite:///%PROJECT_ROOT_URL%/frontend/e2e/test.db"
set "DATABASE_URL_SYNC=sqlite:///%PROJECT_ROOT_URL%/frontend/e2e/test.db"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Missing .venv\Scripts\python.exe. Run deploy\scripts\bootstrap_dev.ps1 first.
    exit /b 1
)

".venv\Scripts\python.exe" "frontend\e2e\seed.py"
if errorlevel 1 exit /b 1

".venv\Scripts\python.exe" -m uvicorn app.main:app --port 8000 --host 0.0.0.0
