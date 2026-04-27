param(
    [string]$ProjectRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
)

$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'

function Write-Section([string]$Title) {
    Write-Host ""
    Write-Host ("[BOOTSTRAP] {0}" -f $Title)
}

function Assert-Command([string]$Name, [string]$Hint) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name not found. $Hint"
    }
}

Set-Location $ProjectRoot

Write-Host "============================================"
Write-Host "  Intranet Dev Environment Bootstrap"
Write-Host "============================================"

Assert-Command 'python' 'Install Python 3.11+ and ensure it is on PATH.'
Assert-Command 'npm' 'Install Node.js and ensure npm is on PATH.'

Write-Section 'Preparing .env'
if (-not (Test-Path '.env')) {
    Copy-Item '.env.example' '.env'
    Write-Host 'Created .env from .env.example'
} else {
    Write-Host '.env already exists'
}

Write-Section 'Checking PostgreSQL connectivity'
& python 'scripts/test_db_connection.py'

Write-Section 'Creating virtual environment'
if (-not (Test-Path '.venv\Scripts\python.exe')) {
    & python -m venv '.venv'
    Write-Host '.venv created'
} else {
    Write-Host '.venv already exists'
}

$venvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'

Write-Section 'Upgrading pip'
& $venvPython -m pip install --upgrade pip

Write-Section 'Installing backend dependencies'
& $venvPython -m pip install -r 'requirements.txt'

Write-Section 'Checking npm registry'
$registryFile = Join-Path $ProjectRoot 'frontend\.npmrc'
if (-not (Test-Path $registryFile)) {
    throw 'frontend/.npmrc not found. Create it from the repository template and point NPM_REGISTRY to the company mirror.'
}
$registryLine = Get-Content $registryFile | Where-Object { $_ -match '^registry=' } | Select-Object -First 1
if ([string]::IsNullOrWhiteSpace($registryLine)) {
    throw 'frontend/.npmrc does not define registry=. Please configure the company npm mirror.'
}
Write-Host $registryLine

Write-Section 'Installing frontend dependencies'
Set-Location (Join-Path $ProjectRoot 'frontend')
& npm install
Set-Location $ProjectRoot

Write-Section 'Bootstrap complete'
Write-Host 'Environment is ready. Use start.intranet.bat for daily launch.'
