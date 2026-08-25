param(
    [string]$ProjectRoot,
    [string]$PythonExe,
    [int]$BackendPort = 8000,
    [ValidateSet('process', 'service', 'none')]
    [string]$StartMode = 'process',
    [string]$ServiceName = 'SolverBackend',
    [string]$ExpectedCommit,
    [switch]$SkipMigrations,
    [switch]$SkipDataChecks,
    [switch]$ForceKillPortProcess
)

$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'

function Write-Section([string]$Title) {
    Write-Host ""
    Write-Host ("[VERIFY-INSTALL] {0}" -f $Title)
}

function Find-ProjectRoot {
    $dir = (Resolve-Path -LiteralPath $PSScriptRoot).ProviderPath
    while (-not [string]::IsNullOrWhiteSpace($dir)) {
        $hasBackend = Test-Path -LiteralPath (Join-Path -Path $dir -ChildPath 'requirements.txt')
        $hasApp = Test-Path -LiteralPath (Join-Path -Path $dir -ChildPath 'app')
        $hasAlembic = Test-Path -LiteralPath (Join-Path -Path $dir -ChildPath 'alembic.ini')
        if ($hasBackend -and $hasApp -and $hasAlembic) {
            return $dir.TrimEnd('\')
        }

        $parent = Split-Path -Parent $dir
        if ([string]::IsNullOrWhiteSpace($parent) -or $parent -eq $dir) {
            break
        }
        $dir = $parent
    }

    throw "Unable to locate project root from script path: $PSScriptRoot"
}

function Invoke-Native([string]$FilePath, [string[]]$Arguments) {
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $FilePath @Arguments
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    if ($exitCode -ne 0) {
        throw ("Command failed with exit code {0}: {1} {2}" -f $exitCode, $FilePath, ($Arguments -join ' '))
    }
}

function Invoke-ReadinessCheck([string]$Python, [string[]]$Arguments, [string]$LogDir) {
    if (-not (Test-Path -LiteralPath $LogDir)) {
        New-Item -ItemType Directory -Path $LogDir | Out-Null
    }
    $timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $logPath = Join-Path -Path $LogDir -ChildPath ("deploy_readiness_{0}.json" -f $timestamp)
    $allArgs = @()
    $allArgs += $Arguments
    $allArgs += '--json'

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = & $Python @allArgs 2>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    $text = ($output | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine
    Set-Content -LiteralPath $logPath -Value $text -Encoding UTF8
    if (-not [string]::IsNullOrWhiteSpace($text)) {
        Write-Host $text
    }

    if ($exitCode -ne 0) {
        throw ("Deployment readiness check failed with exit code {0}. Full JSON/log: {1}" -f $exitCode, $logPath)
    }
}

function Import-ProjectEnv([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }

    Get-Content -LiteralPath $Path | ForEach-Object {
        $line = $_.Trim()
        if ([string]::IsNullOrWhiteSpace($line) -or $line.StartsWith('#')) {
            return
        }

        $separatorIndex = $line.IndexOf('=')
        if ($separatorIndex -le 0) {
            return
        }

        $name = $line.Substring(0, $separatorIndex).Trim()
        $value = $line.Substring($separatorIndex + 1).Trim()
        if (
            ($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))
        ) {
            $value = $value.Substring(1, $value.Length - 2)
        }

        Set-Item -Path ("Env:{0}" -f $name) -Value $value
    }
}

function Get-ListeningProcessIds([int]$Port) {
    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return @($connections | Select-Object -ExpandProperty OwningProcess -Unique)
}

function Get-ProcessCommandLine([int]$ProcessId) {
    $process = Get-CimInstance Win32_Process -Filter ("ProcessId = {0}" -f $ProcessId) -ErrorAction SilentlyContinue
    if ($null -eq $process) {
        return $null
    }
    return $process.CommandLine
}

function Get-ChildProcessIds([int]$ParentProcessId) {
    $children = @(Get-CimInstance Win32_Process -Filter ("ParentProcessId = {0}" -f $ParentProcessId) -ErrorAction SilentlyContinue)
    $ids = @()
    foreach ($child in $children) {
        $ids += [int]$child.ProcessId
        $ids += Get-ChildProcessIds -ParentProcessId ([int]$child.ProcessId)
    }
    return $ids
}

function Test-ProjectProcess([int]$ProcessId, [string]$Root) {
    $commandLine = Get-ProcessCommandLine $ProcessId
    if ([string]::IsNullOrWhiteSpace($commandLine)) {
        return $false
    }
    $normalizedCommand = $commandLine.ToLowerInvariant()
    $normalizedRoot = $Root.ToLowerInvariant()
    return $normalizedCommand.Contains($normalizedRoot)
}

function Stop-ProcessAndWait([int]$ProcessId, [string]$Reason) {
    $processIds = @()
    $processIds += Get-ChildProcessIds -ParentProcessId $ProcessId
    $processIds += $ProcessId
    $processIds = @($processIds | Select-Object -Unique)

    foreach ($pidToStop in $processIds) {
        $process = Get-Process -Id $pidToStop -ErrorAction SilentlyContinue
        if ($null -eq $process) {
            continue
        }
        Write-Host ("Stopping PID {0}: {1}" -f $pidToStop, $Reason)
        Stop-Process -Id $pidToStop -Force
    }

    for ($attempt = 1; $attempt -le 20; $attempt++) {
        Start-Sleep -Milliseconds 500
        $alive = @($processIds | Where-Object { $null -ne (Get-Process -Id $_ -ErrorAction SilentlyContinue) })
        if ($alive.Count -eq 0) {
            return
        }
    }
    throw ("Process tree did not exit after stop: PID {0}" -f $ProcessId)
}

function Stop-Backend {
    param(
        [string]$Root,
        [string]$PidFile,
        [string]$Service,
        [int]$Port
    )

    $svc = Get-Service -Name $Service -ErrorAction SilentlyContinue
    if ($null -ne $svc -and $svc.Status -ne 'Stopped') {
        Write-Host ("Stopping service {0}" -f $Service)
        Stop-Service -Name $Service -Force
        $svc.WaitForStatus('Stopped', [TimeSpan]::FromSeconds(30))
    }

    if (Test-Path -LiteralPath $PidFile) {
        $pidText = (Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
        if ($pidText -match '^\d+$') {
            $pidValue = [int]$pidText
            if (Test-ProjectProcess $pidValue $Root) {
                Stop-ProcessAndWait $pidValue 'previous verifier backend pid file'
            } elseif ($null -ne (Get-Process -Id $pidValue -ErrorAction SilentlyContinue)) {
                Write-Warning ("Ignoring stale backend PID file owned by another process: PID {0}" -f $pidValue)
            }
        }
        Remove-Item -LiteralPath $PidFile -Force
    }

    for ($attempt = 1; $attempt -le 20; $attempt++) {
        $remaining = Get-ListeningProcessIds $Port
        if ($remaining.Count -eq 0) {
            Write-Host ("Port {0} is free" -f $Port)
            return
        }

        foreach ($portPid in $remaining) {
            if (Test-ProjectProcess $portPid $Root) {
                Stop-ProcessAndWait $portPid ("project process still listening on port {0}" -f $Port)
                continue
            }
            if ($ForceKillPortProcess) {
                Stop-ProcessAndWait $portPid ("ForceKillPortProcess for port {0}" -f $Port)
                continue
            }
            $commandLine = Get-ProcessCommandLine $portPid
            throw (
                "Port {0} is still owned by PID {1}, but it does not look like this project. " +
                "Stop it manually or rerun with -ForceKillPortProcess. CommandLine={2}"
            ) -f $Port, $portPid, $commandLine
        }

        Start-Sleep -Milliseconds 500
    }
    throw ("Port {0} is still occupied after backend stop" -f $Port)
}

function Start-Backend {
    param(
        [string]$Root,
        [string]$Python,
        [string]$PidFile,
        [string]$Service,
        [int]$Port,
        [string]$Mode
    )

    if ($Mode -eq 'none') {
        Write-Host 'StartMode=none; backend start skipped'
        return
    }

    if ($Mode -eq 'service') {
        $svc = Get-Service -Name $Service -ErrorAction SilentlyContinue
        if ($null -eq $svc) {
            throw ("Service not found: {0}" -f $Service)
        }
        Write-Host ("Starting service {0}" -f $Service)
        Start-Service -Name $Service
        return
    }

    $deployDir = Split-Path -Parent $PidFile
    $logDir = Join-Path -Path $deployDir -ChildPath 'logs'
    if (-not (Test-Path -LiteralPath $logDir)) {
        New-Item -ItemType Directory -Path $logDir | Out-Null
    }
    $timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $outLog = Join-Path -Path $logDir -ChildPath ("backend_{0}.out.log" -f $timestamp)
    $errLog = Join-Path -Path $logDir -ChildPath ("backend_{0}.err.log" -f $timestamp)
    $args = @('-m', 'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', [string]$Port)
    $process = Start-Process `
        -FilePath $Python `
        -ArgumentList $args `
        -WorkingDirectory $Root `
        -WindowStyle Hidden `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog `
        -PassThru
    Set-Content -LiteralPath $PidFile -Value ([string]$process.Id) -Encoding ASCII
    Write-Host ("Started backend PID {0}" -f $process.Id)
    Write-Host ("stdout: {0}" -f $outLog)
    Write-Host ("stderr: {0}" -f $errLog)
}

function Wait-SystemReady([int]$Port, [bool]$IncludeDataChecks, [string]$Commit) {
    $include = if ($IncludeDataChecks) { 'true' } else { 'false' }
    $url = "http://127.0.0.1:$Port/api/v1/system/status?include_data_checks=$include"
    for ($attempt = 1; $attempt -le 40; $attempt++) {
        Start-Sleep -Seconds 2
        try {
            $status = Invoke-RestMethod -Uri $url -TimeoutSec 5
            if ($status.status -eq 'ready') {
                if (-not [string]::IsNullOrWhiteSpace($Commit)) {
                    $runningCommit = [string]$status.release.app_commit
                    if ($runningCommit -ne $Commit) {
                        throw ("Running commit mismatch. expected={0}, actual={1}" -f $Commit, $runningCommit)
                    }
                }
                Write-Host ("System status ready: {0}" -f $url)
                return
            }
            Write-Host ("System status is {0}; waiting... attempt {1}/40" -f $status.status, $attempt)
        } catch {
            Write-Host ("Waiting for system status... attempt {0}/40: {1}" -f $attempt, $_.Exception.Message)
        }
    }
    throw ("Backend did not report ready status at {0}" -f $url)
}

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = Find-ProjectRoot
} else {
    $ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).ProviderPath.TrimEnd('\')
}

if ([string]::IsNullOrWhiteSpace($PythonExe)) {
    $PythonExe = Join-Path -Path $ProjectRoot -ChildPath '.venv\Scripts\python.exe'
}

$envFile = Join-Path -Path $ProjectRoot -ChildPath '.env'
$deployDir = Join-Path -Path $ProjectRoot -ChildPath '.deploy'
$pidFile = Join-Path -Path $deployDir -ChildPath 'solver-backend.pid'
$localPgData = Join-Path -Path $ProjectRoot -ChildPath '.postgres-data'
$legacySiblingPgData = "{0}.postgres-data" -f $ProjectRoot.TrimEnd('\')
$localPgLogDir = Join-Path -Path $ProjectRoot -ChildPath '.postgres-logs'
$localPgLog = Join-Path -Path $localPgLogDir -ChildPath 'postgres.log'
$postgresBin = Join-Path -Path ${env:ProgramFiles} -ChildPath 'PostgreSQL\15\bin'
$pgCtl = Join-Path -Path $postgresBin -ChildPath 'pg_ctl.exe'

function Resolve-ConfiguredPath([string]$PathValue) {
    if ([string]::IsNullOrWhiteSpace($PathValue)) {
        return $null
    }
    $expanded = [Environment]::ExpandEnvironmentVariables($PathValue.Trim())
    if ([System.IO.Path]::IsPathRooted($expanded)) {
        return $expanded
    }
    return (Join-Path -Path $ProjectRoot -ChildPath $expanded)
}

function Ensure-WorkspacePostgres {
    $dbHost = [Environment]::GetEnvironmentVariable('DB_HOST', 'Process')
    $dbPort = [Environment]::GetEnvironmentVariable('DB_PORT', 'Process')
    $configuredPgData = Resolve-ConfiguredPath ([Environment]::GetEnvironmentVariable('POSTGRES_DATA_DIR', 'Process'))
    $configuredPgBin = Resolve-ConfiguredPath ([Environment]::GetEnvironmentVariable('POSTGRES_BIN_DIR', 'Process'))
    if ([string]::IsNullOrWhiteSpace($dbPort)) {
        $dbPort = '5432'
    }
    $usesLocalHost = [string]::IsNullOrWhiteSpace($dbHost) -or @('localhost', '127.0.0.1', '::1') -contains $dbHost
    if (-not $usesLocalHost) {
        return
    }
    $pgData = $null
    $pgDataCandidates = @()
    if (-not [string]::IsNullOrWhiteSpace($configuredPgData)) {
        $pgDataCandidates += $configuredPgData
    }
    $pgDataCandidates += @($localPgData, $legacySiblingPgData)
    foreach ($candidate in $pgDataCandidates) {
        if (Test-Path -LiteralPath $candidate -PathType Container) {
            $pgData = $candidate
            break
        }
    }
    if ([string]::IsNullOrWhiteSpace($pgData)) {
        if (-not [string]::IsNullOrWhiteSpace($configuredPgData)) {
            throw ("POSTGRES_DATA_DIR is configured but not found: {0}" -f $configuredPgData)
        }
        Write-Host ("No workspace PostgreSQL data directory found. Checked: {0}. Assuming an external local PostgreSQL service owns DB_PORT={1}" -f ($pgDataCandidates -join '; '), $dbPort)
        return
    }
    $effectivePgCtl = $pgCtl
    if (-not [string]::IsNullOrWhiteSpace($configuredPgBin)) {
        $effectivePgCtl = Join-Path -Path $configuredPgBin -ChildPath 'pg_ctl.exe'
    }
    if (-not (Test-Path -LiteralPath $effectivePgCtl -PathType Leaf)) {
        throw "Workspace PostgreSQL data exists, but pg_ctl was not found at $effectivePgCtl. Set POSTGRES_BIN_DIR in .env if PostgreSQL is installed elsewhere."
    }
    if (-not (Test-Path -LiteralPath $localPgLogDir)) {
        New-Item -ItemType Directory -Path $localPgLogDir | Out-Null
    }

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $effectivePgCtl -D $pgData status > $null 2>&1
        $statusExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($statusExitCode -eq 0) {
        Write-Host 'Workspace PostgreSQL is already running'
        return
    }

    Write-Host ("Starting workspace PostgreSQL from {0} on DB_PORT={1}" -f $pgData, $dbPort)
    Invoke-Native $effectivePgCtl @('-D', $pgData, '-l', $localPgLog, '-o', ("-p {0}" -f $dbPort), 'start')
}

Set-Location -LiteralPath $ProjectRoot
if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    throw ("Python executable not found: {0}" -f $PythonExe)
}
if (-not (Test-Path -LiteralPath $deployDir)) {
    New-Item -ItemType Directory -Path $deployDir | Out-Null
}

Write-Host '============================================'
Write-Host '  Verifier Machine Install/Restart'
Write-Host '============================================'
Write-Host ("ProjectRoot: {0}" -f $ProjectRoot)
Write-Host ("PythonExe:   {0}" -f $PythonExe)
Write-Host ("BackendPort: {0}" -f $BackendPort)
Write-Host ("StartMode:   {0}" -f $StartMode)

Write-Section 'Loading environment'
Import-ProjectEnv $envFile
if (-not [string]::IsNullOrWhiteSpace($ExpectedCommit)) {
    # Start-Process inherits the current process environment. Publishing the
    # expected commit here lets the running API prove which checkout it serves.
    $env:APP_COMMIT = $ExpectedCommit
}
Write-Host ("DB_HOST={0}" -f $env:DB_HOST)
Write-Host ("DB_PORT={0}" -f $env:DB_PORT)
Write-Host ("DB_NAME={0}" -f $env:DB_NAME)

Write-Section 'Stopping previous backend'
Stop-Backend -Root $ProjectRoot -PidFile $pidFile -Service $ServiceName -Port $BackendPort

Write-Section 'Checking database connectivity'
Ensure-WorkspacePostgres
Invoke-Native $PythonExe @('scripts/test_db_connection.py')

if (-not $SkipMigrations) {
    Write-Section 'Running migrations'
    Invoke-Native $PythonExe @('-m', 'alembic', 'upgrade', 'head')

    Write-Section 'Checking narrow schema compatibility'
    Invoke-Native $PythonExe @('scripts/ensure_schema_compat.py')
} else {
    Write-Section 'Skipping migrations'
}

Write-Section 'Checking deployment readiness before start'
$readinessArgs = @('scripts/check_deploy_readiness.py')
if (-not $SkipDataChecks) {
    $readinessArgs += '--strict-data'
}
Invoke-ReadinessCheck -Python $PythonExe -Arguments $readinessArgs -LogDir (Join-Path -Path $deployDir -ChildPath 'logs')

Write-Section 'Starting backend'
Start-Backend -Root $ProjectRoot -Python $PythonExe -PidFile $pidFile -Service $ServiceName -Port $BackendPort -Mode $StartMode

if ($StartMode -ne 'none') {
    Write-Section 'Checking running system status'
    Wait-SystemReady -Port $BackendPort -IncludeDataChecks:(-not $SkipDataChecks) -Commit $ExpectedCommit
}

Write-Section 'Install/restart complete'
Write-Host ("Backend: http://127.0.0.1:{0}" -f $BackendPort)
Write-Host ("Status:  http://127.0.0.1:{0}/api/v1/system/status?include_data_checks=true" -f $BackendPort)
