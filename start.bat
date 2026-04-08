@echo off
set PYTHONIOENCODING=utf-8

echo ============================================
echo   Process Scheduling System - Quick Start
echo ============================================
echo.

echo [1/7] Checking Docker...
docker info >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker is not running. Please start Docker Desktop.
    pause
    exit /b 1
)
echo [OK] Docker is running

echo.
echo [2/7] Starting PostgreSQL...
docker-compose up -d postgres 2>nul
if errorlevel 1 (
    echo [ERROR] Failed to start PostgreSQL
    pause
    exit /b 1
)

echo.
echo [3/7] Waiting for database to be ready...
set /a retries=30
:wait_loop
timeout /t 2 /nobreak >nul
docker exec solver_postgres pg_isready -U solver -d solver_db >nul 2>&1
if not errorlevel 1 goto db_ready
set /a retries-=1
if %retries% gtr 0 goto wait_loop

echo [ERROR] Database startup timeout
pause
exit /b 1

:db_ready
echo [OK] Database is ready

echo.
echo [4/7] Testing database connection...
.venv\Scripts\python.exe scripts/test_db_connection.py
if errorlevel 1 (
    echo [ERROR] Database connection failed
    pause
    exit /b 1
)

echo.
echo [5/7] Running database migrations...
.venv\Scripts\alembic upgrade head
if errorlevel 1 (
    echo [ERROR] Database migration failed
    pause
    exit /b 1
)

echo.
echo [6/8] Loading initial seed data...
.venv\Scripts\python.exe scripts/load_seed_data.py --file seeds/001_initial_data.sql
if errorlevel 1 (
    echo [WARN] Initial seed data load failed (may already exist)
)

echo.
echo [7/8] Loading expanded seed data...
.venv\Scripts\python.exe scripts/load_seed_data.py --file seeds/002_expanded_data.sql
if errorlevel 1 (
    echo [WARN] Expanded seed data load failed (may already exist)
)

echo.
echo [8/8] Starting backend server...
start "Backend Server" cmd /k "set PYTHONIOENCODING=utf-8 && .venv\Scripts\activate.bat && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"

echo.
echo ============================================
echo   Startup Complete!
echo ============================================
echo.
echo   Backend API:  http://localhost:8000/docs
echo   Frontend UI:  frontend/index.html
echo.
echo   Press any key to open the frontend...
pause >nul

start "" "%~dp0frontend\index.html"

echo.
echo Services are running in background.
echo To stop: docker-compose down
echo.
pause
