param([string]$ProjectRoot, [string]$PythonExe)
$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($ProjectRoot)) { $ProjectRoot = Join-Path $PSScriptRoot '..\..' }
$ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).ProviderPath
if ([string]::IsNullOrWhiteSpace($PythonExe)) { $PythonExe = Join-Path $ProjectRoot '.venv\Scripts\python.exe' }
$PythonExe = (Resolve-Path -LiteralPath $PythonExe).ProviderPath
$logDir = Join-Path $ProjectRoot '.deploy\logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$pidFile = Join-Path $ProjectRoot '.deploy\planner-worker.pid'
if (Test-Path -LiteralPath $pidFile) {
    $previousId = [int](Get-Content -LiteralPath $pidFile -Raw).Trim()
    $previous = Get-CimInstance Win32_Process -Filter "ProcessId = $previousId" -ErrorAction SilentlyContinue
    if ($previous -and $previous.CommandLine -like '*-m app.planner_worker*' -and $previous.ExecutablePath -eq $PythonExe) {
        Write-Host "Planner worker already running: $previousId"
        return
    }
}
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$workerProcess = Start-Process -FilePath $PythonExe -ArgumentList @('-m','app.planner_worker') -WorkingDirectory $ProjectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDir "worker-$stamp.out.log") -RedirectStandardError (Join-Path $logDir "worker-$stamp.err.log")
Set-Content -LiteralPath $pidFile -Value $workerProcess.Id
Write-Host "Planner worker started: $($workerProcess.Id)"
