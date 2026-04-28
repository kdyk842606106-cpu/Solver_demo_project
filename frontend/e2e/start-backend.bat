@echo off
cd /d E:\Solver_demo_project
set DATABASE_URL=sqlite+aiosqlite:///E:/Solver_demo_project/frontend/e2e/test.db
.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000 --host 0.0.0.0
