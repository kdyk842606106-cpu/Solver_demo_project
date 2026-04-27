param(
    [ValidateSet('docker', 'local', 'intranet')]
    [string]$Mode = 'local',
    [string]$ProjectRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
)

$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'

function Write-Section([string]$Title) {
    Write-Host ""
    Write-Host ("[LAUNCH] {0}" -f $Title)
}

function Assert-Path([string]$Path, [string]$Message) {
    if (-not (Test-Path $Path)) {
        throw $Message
    }
}

Set-Location $ProjectRoot

Write-Host "============================================"
Write-Host ("  Dev Environment Launch ({0})" -f $Mode)
Write-Host "============================================"

Assert-Path '.venv\Scripts\python.exe' 'Virtual environment not found. Run deploy/scripts/bootstrap_dev.ps1 first.'
Assert-Path '.env' '.env not found. Run deploy/scripts/bootstrap_dev.ps1 first.'
Assert-Path 'frontend\.npmrc' 'frontend/.npmrc not found. Configure the company npm mirror first.'

$venvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'

if ($Mode -eq 'docker') {
    Write-Section 'Checking Docker'
    docker info > $null 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw 'Docker is not running. Please start Docker Desktop.'
    }

    Write-Section 'Starting PostgreSQL'
    docker-compose up -d postgres
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to start PostgreSQL via docker-compose.'
    }

    Write-Section 'Waiting for PostgreSQL'
    $retries = 30
    while ($retries -gt 0) {
        Start-Sleep -Seconds 2
        docker exec solver_postgres pg_isready -U solver -d solver_db > $null 2>&1
        if ($LASTEXITCODE -eq 0) {
            break
        }
        $retries--
    }
    if ($retries -le 0) {
        throw 'Database startup timeout.'
    }
} else {
    Write-Section 'Checking database connectivity'
    & $venvPython 'scripts/test_db_connection.py'
}

Write-Section 'Running migrations'
& $venvPython -m alembic upgrade head

Write-Section 'Loading seed data'
& $venvPython 'scripts/load_seed_data.py' --file 'seeds/001_initial_data.sql'
& $venvPython 'scripts/load_seed_data.py' --file 'seeds/002_expanded_data.sql'
& $venvPython 'scripts/load_seed_data.py' --file 'seeds/003_v0.2_seed_data.sql'

Write-Section 'Starting backend'
$backendCommand = "Set-Location '$ProjectRoot'; & '.venv\Scripts\python.exe' -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
Start-Process -FilePath 'powershell' -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-NoExit', '-Command', $backendCommand | Out-Null

Write-Section 'Starting frontend'
$frontendRoot = Join-Path $ProjectRoot 'frontend'
$frontendCommand = "Set-Location '$frontendRoot'; npm run dev -- --host 0.0.0.0"
Start-Process -FilePath 'powershell' -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-NoExit', '-Command', $frontendCommand | Out-Null

Write-Section 'Launch complete'
Write-Host 'Backend:  http://localhost:8000/docs'
Write-Host 'Frontend: http://localhost:5173'
