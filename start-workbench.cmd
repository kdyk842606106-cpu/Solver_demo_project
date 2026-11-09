@echo off
setlocal EnableExtensions DisableDelayedExpansion
chcp 65001 >nul
set "wait_on_exit=1"
if defined PLANNER_FROM_DEPLOY (
  rem Keep command-line callers unattended. Pause when Explorer opened cmd.exe.
  powershell.exe -NoProfile -NonInteractive -Command "$p=Get-CimInstance Win32_Process -Filter ('ProcessId='+$PID) -ErrorAction Stop; $c=Get-Process -Id (Get-CimInstance Win32_Process -Filter ('ProcessId='+$p.ParentProcessId) -ErrorAction Stop).ParentProcessId -ErrorAction Stop; if($c.ProcessName -eq 'explorer'){exit 0}; exit 1" >nul 2>&1
  if errorlevel 1 set "wait_on_exit="
)
if defined PLANNER_NO_PAUSE set "wait_on_exit="
set "rc=1"
set "startup_log=%~dp0deploy-startup-%RANDOM%-%RANDOM%.log"
pushd "%~dp0"
if errorlevel 1 goto :bad_directory
>"%startup_log%" echo [START] Solver Workbench
if errorlevel 1 (
  set "startup_log=%TEMP%\planner-startup-%RANDOM%-%RANDOM%.log"
)
>"%startup_log%" echo [START] Solver Workbench
if errorlevel 1 goto :bad_log
echo 启动日志 / Startup log: "%startup_log%"
if not exist "runtime\python\python.exe" goto :incomplete
if not exist "deploy\scripts\deploy_runtime.py" goto :incomplete
if not exist "MANIFEST.json" goto :incomplete
echo 正在检查部署并启动服务，请稍候。详细进度写入上面的日志。
set "PYTHONHOME="
set "PYTHONPATH="
set "PYTHONNOUSERSITE=1"
set "PYTHONIOENCODING=utf-8"
"runtime\python\python.exe" -X utf8 -u "deploy\scripts\deploy_runtime.py" up %* >>"%startup_log%" 2>&1
set "rc=%ERRORLEVEL%"
>>"%startup_log%" echo [EXIT] %rc%
goto :show

:incomplete
>>"%startup_log%" echo 安装文件不完整。请下载 Windows 离线 ZIP，完整解压后，把此启动器放在含 deploy.bat 和 runtime 文件夹的目录中再运行。
goto :show

:bad_log
echo 无法写入启动日志。请将完整安装包解压到可写的本地目录。
goto :done

:bad_directory
echo 无法进入启动器目录。请先完整解压安装包。
goto :finish

:show
type "%startup_log%"
if "%rc%"=="0" echo 部署成功。请在浏览器打开上方 url 对应的本机地址。
if not "%rc%"=="0" echo 部署失败。请查看上方报错。日志保存在 "%startup_log%"。
:done
popd
:finish
if defined wait_on_exit pause
exit /b %rc%
