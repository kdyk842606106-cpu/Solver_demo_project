@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy\scripts\start_planner_worker.ps1" -ProjectRoot "%CD%"
