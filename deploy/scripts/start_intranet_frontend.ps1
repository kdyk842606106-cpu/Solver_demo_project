param(
    [string]$ProjectRoot,
    [int]$FrontendPort = 5173
)

$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'

function Write-Section([string]$Title) {
    Write-Host ""
    Write-Host ("[INTRANET-FRONTEND] {0}" -f $Title)
}

function Find-ProjectRoot {
    $dir = (Resolve-Path -LiteralPath $PSScriptRoot).ProviderPath
    while (-not [string]::IsNullOrWhiteSpace($dir)) {
        $hasFrontend = Test-Path -LiteralPath (Join-Path -Path $dir -ChildPath 'frontend')
        $hasBackend = Test-Path -LiteralPath (Join-Path -Path $dir -ChildPath 'app')
        if ($hasFrontend -and $hasBackend) {
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

function Test-FrontendProcess([int]$ProcessId, [string]$Root) {
    $commandLine = Get-ProcessCommandLine $ProcessId
    if ([string]::IsNullOrWhiteSpace($commandLine)) {
        return $false
    }

    $normalizedCommand = $commandLine.ToLowerInvariant()
    $normalizedRoot = $Root.ToLowerInvariant()
    return $normalizedCommand.Contains($normalizedRoot)
}

function Stop-FrontendPort([string]$Root, [int]$Port) {
    $portPids = Get-ListeningProcessIds $Port
    foreach ($portPid in $portPids) {
        if (-not (Test-FrontendProcess $portPid $Root)) {
            $commandLine = Get-ProcessCommandLine $portPid
            throw (
                "Port {0} is owned by PID {1}, but it does not look like this frontend. " +
                "Stop it manually. CommandLine={2}"
            ) -f $Port, $portPid, $commandLine
        }

        Write-Host ("Stopping frontend PID {0} on port {1}" -f $portPid, $Port)
        Stop-Process -Id $portPid -Force
    }

    for ($attempt = 1; $attempt -le 20; $attempt++) {
        $remaining = Get-ListeningProcessIds $Port
        if ($remaining.Count -eq 0) {
            Write-Host ("Frontend port {0} is free" -f $Port)
            return
        }
        Start-Sleep -Milliseconds 500
    }
    throw ("Frontend port {0} is still occupied" -f $Port)
}

function Wait-Frontend([int]$Port) {
    $url = "http://127.0.0.1:$Port"
    for ($attempt = 1; $attempt -le 40; $attempt++) {
        Start-Sleep -Seconds 2
        try {
            $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                Write-Host ("Frontend ready: {0}" -f $url)
                return
            }
        } catch {
            Write-Host ("Waiting for frontend on port {0}... attempt {1}/40" -f $Port, $attempt)
        }
    }
    throw ("Frontend did not become ready at {0}" -f $url)
}

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = Find-ProjectRoot
} else {
    $ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).ProviderPath.TrimEnd('\')
}

$frontendRoot = Join-Path -Path $ProjectRoot -ChildPath 'frontend'
$npmrcFile = Join-Path -Path $frontendRoot -ChildPath '.npmrc'
$npmCommand = if (Get-Command 'npm.cmd' -ErrorAction SilentlyContinue) { 'npm.cmd' } else { 'npm' }
$deployDir = Join-Path -Path $ProjectRoot -ChildPath '.deploy'
$logDir = Join-Path -Path $deployDir -ChildPath 'logs'

if (-not (Test-Path -LiteralPath $frontendRoot -PathType Container)) {
    throw ("Frontend directory not found: {0}" -f $frontendRoot)
}
if (-not (Test-Path -LiteralPath $npmrcFile -PathType Leaf)) {
    throw 'frontend/.npmrc not found. Configure the company npm mirror first.'
}
if (-not (Test-Path -LiteralPath $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}

Write-Host '============================================'
Write-Host '  Intranet Frontend Restart'
Write-Host '============================================'
Write-Host ("ProjectRoot:  {0}" -f $ProjectRoot)
Write-Host ("FrontendPort: {0}" -f $FrontendPort)

Write-Section 'Stopping previous frontend'
Stop-FrontendPort -Root $ProjectRoot -Port $FrontendPort

Write-Section 'Starting frontend'
$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$outLog = Join-Path -Path $logDir -ChildPath ("frontend_{0}.out.log" -f $timestamp)
$errLog = Join-Path -Path $logDir -ChildPath ("frontend_{0}.err.log" -f $timestamp)
$process = Start-Process `
    -FilePath $npmCommand `
    -ArgumentList @('run', 'dev', '--', '--host', '0.0.0.0') `
    -WorkingDirectory $frontendRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $outLog `
    -RedirectStandardError $errLog `
    -PassThru

Set-Content -LiteralPath (Join-Path -Path $deployDir -ChildPath 'solver-frontend.pid') -Value ([string]$process.Id) -Encoding ASCII
Write-Host ("Started frontend PID {0}" -f $process.Id)
Write-Host ("stdout: {0}" -f $outLog)
Write-Host ("stderr: {0}" -f $errLog)

Write-Section 'Waiting for frontend'
Wait-Frontend -Port $FrontendPort

Write-Section 'Frontend restart complete'
Write-Host ("Frontend: http://127.0.0.1:{0}" -f $FrontendPort)
