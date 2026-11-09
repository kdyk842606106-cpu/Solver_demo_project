@echo off
setlocal
cd /d "%~dp0"
"runtime\python\python.exe" "deploy\scripts\deploy_runtime.py" stop %*
exit /b %ERRORLEVEL%
