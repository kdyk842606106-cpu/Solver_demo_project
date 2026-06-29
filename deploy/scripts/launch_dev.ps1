param(
    [ValidateSet('docker', 'local', 'intranet')]
    [string]$Mode = 'local',
    [string]$ProjectRoot
)

$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'

function Write-Section([string]$Title) {
    Write-Host ""
    Write-Host ("[LAUNCH] {0}" -f $Title)
}

function Assert-Path([string]$Path, [string]$Message) {
    if (-not (Test-Path -LiteralPath $Path)) {
        throw $Message
    }
}

function Find-ProjectRoot {
    $dir = (Resolve-Path -LiteralPath $PSScriptRoot).ProviderPath
    while (-not [string]::IsNullOrWhiteSpace($dir)) {
        $hasBackend = Test-Path -LiteralPath (Join-Path -Path $dir -ChildPath 'requirements.txt')
        $hasFrontend = Test-Path -LiteralPath (Join-Path -Path $dir -ChildPath 'frontend')
        $hasApp = Test-Path -LiteralPath (Join-Path -Path $dir -ChildPath 'app')
        if ($hasBackend -and $hasFrontend -and $hasApp) {
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

function Test-PythonModule([string]$PythonExe, [string]$ModuleName) {
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $PythonExe -c "import $ModuleName" > $null 2>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    return $exitCode -eq 0
}

function Get-EnvFileValue([string]$Path, [string]$Name) {
    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }
    $line = Get-Content -LiteralPath $Path | Where-Object { $_ -match ("^{0}=" -f [regex]::Escape($Name)) } | Select-Object -First 1
    if ([string]::IsNullOrWhiteSpace($line)) {
        return $null
    }
    return $line.Substring($Name.Length + 1).Trim()
}

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = Find-ProjectRoot
} else {
    $ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).ProviderPath.TrimEnd('\')
}

$venvRoot = Join-Path -Path $ProjectRoot -ChildPath '.venv'
$venvScripts = Join-Path -Path $venvRoot -ChildPath 'Scripts'
$venvPython = Join-Path -Path $venvScripts -ChildPath 'python.exe'
$envFile = Join-Path -Path $ProjectRoot -ChildPath '.env'
$frontendRoot = Join-Path -Path $ProjectRoot -ChildPath 'frontend'
$npmrcFile = Join-Path -Path $frontendRoot -ChildPath '.npmrc'
$npmCommand = if (Get-Command 'npm.cmd' -ErrorAction SilentlyContinue) { 'npm.cmd' } else { 'npm' }
$localPgData = Join-Path -Path $ProjectRoot -ChildPath '.postgres-data'
$localPgLogDir = Join-Path -Path $ProjectRoot -ChildPath '.postgres-logs'
$localPgLog = Join-Path -Path $localPgLogDir -ChildPath 'postgres.log'
$postgresBin = Join-Path -Path ${env:ProgramFiles} -ChildPath 'PostgreSQL\15\bin'
$pgCtl = Join-Path -Path $postgresBin -ChildPath 'pg_ctl.exe'
$projectRootName = Split-Path -Leaf $ProjectRoot
$projectParentName = Split-Path -Leaf (Split-Path -Parent $ProjectRoot)

function Ensure-WorkspacePostgres {
    $dbPort = Get-EnvFileValue $envFile 'DB_PORT'
    if ($dbPort -ne '55432' -or -not (Test-Path -LiteralPath $localPgData)) {
        return
    }
    if (-not (Test-Path -LiteralPath $pgCtl -PathType Leaf)) {
        throw "Workspace PostgreSQL data exists, but pg_ctl was not found at $pgCtl"
    }
    if (-not (Test-Path -LiteralPath $localPgLogDir)) {
        New-Item -ItemType Directory -Path $localPgLogDir | Out-Null
    }

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $pgCtl -D $localPgData status > $null 2>&1
        $statusExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($statusExitCode -eq 0) {
        Write-Host 'Workspace PostgreSQL is already running'
        return
    }

    Write-Host 'Starting workspace PostgreSQL on DB_PORT=55432'
    Invoke-Native $pgCtl @('-D', $localPgData, '-l', $localPgLog, '-o', '-p 55432', 'start')
}

Set-Location -LiteralPath $ProjectRoot

Write-Host "============================================"
Write-Host ("  Dev Environment Launch ({0})" -f $Mode)
Write-Host "============================================"
Write-Host "PSScriptRoot: $PSScriptRoot"
Write-Host "ProjectRoot:  $ProjectRoot"
Write-Host "VenvPython:   $venvPython"
if ($projectRootName -eq $projectParentName) {
    Write-Host "[WARN] Project appears to be nested in a duplicate folder: $ProjectRoot"
    Write-Host "[WARN] Prefer extracting the package contents directly into the target Solver_demo_project folder."
}

Assert-Path $venvPython "Virtual environment not found at $venvPython. Run deploy/scripts/bootstrap_dev.ps1 first."
Assert-Path $envFile '.env not found. Run deploy/scripts/bootstrap_dev.ps1 first.'
Assert-Path $npmrcFile 'frontend/.npmrc not found. Configure the company npm mirror first.'
Write-Host "Using venv python: $venvPython"

Write-Section 'Checking backend Python dependencies'
if (-not (Test-PythonModule $venvPython 'openpyxl')) {
    Write-Host 'Missing Python dependency openpyxl; installing requirements.txt'
    Invoke-Native $venvPython @('-m', 'pip', 'install', '-r', 'requirements.txt')
} else {
    Write-Host 'Backend Python dependencies look ready'
}

if ($Mode -eq 'docker') {
    Write-Section 'Checking Docker'
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & docker info > $null 2>&1
        $dockerInfoExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    if ($dockerInfoExitCode -ne 0) {
        throw 'Docker is not running. Please start Docker Desktop.'
    }

    Write-Section 'Starting PostgreSQL'
    Invoke-Native 'docker-compose' @('up', '-d', 'postgres')

    Write-Section 'Waiting for PostgreSQL'
    $retries = 30
    while ($retries -gt 0) {
        Start-Sleep -Seconds 2
        $previousErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            & docker exec solver_postgres pg_isready -U solver -d solver_db > $null 2>&1
            $pgReadyExitCode = $LASTEXITCODE
        } finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
        if ($pgReadyExitCode -eq 0) {
            break
        }
        $retries--
    }
    if ($retries -le 0) {
        throw 'Database startup timeout.'
    }
} else {
    Write-Section 'Checking database connectivity'
    Ensure-WorkspacePostgres
    Invoke-Native $venvPython @('scripts/test_db_connection.py')
}

Write-Section 'Running migrations'
Invoke-Native $venvPython @('-m', 'alembic', 'upgrade', 'head')

Write-Section 'Checking schema compatibility'
Invoke-Native $venvPython @('scripts/ensure_schema_compat.py')

Write-Section 'Loading seed data'
Invoke-Native $venvPython @('scripts/load_seed_data.py', '--file', 'seeds/001_initial_data.sql', '--skip-conflicts')
Invoke-Native $venvPython @('scripts/load_seed_data.py', '--file', 'seeds/002_expanded_data.sql', '--skip-conflicts')
Invoke-Native $venvPython @('scripts/load_seed_data.py', '--file', 'seeds/003_v0.2_seed_data.sql', '--skip-conflicts')
Invoke-Native $venvPython @('scripts/load_seed_data.py', '--file', 'seeds/008_aircraft_final_assembly_10000_seed.sql', '--skip-conflicts')

Write-Section 'Starting backend'
$escapedProjectRoot = $ProjectRoot.Replace("'", "''")
$escapedVenvPython = $venvPython.Replace("'", "''")
$backendCommand = "Set-Location -LiteralPath '$escapedProjectRoot'; & '$escapedVenvPython' -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"
Start-Process -FilePath 'powershell' -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', $backendCommand -WindowStyle Hidden | Out-Null

Write-Section 'Waiting for backend health'
$backendHealthUrl = 'http://127.0.0.1:8000/health'
$backendReady = $false
for ($attempt = 1; $attempt -le 40; $attempt++) {
    Start-Sleep -Seconds 2
    try {
        $response = Invoke-WebRequest -Uri $backendHealthUrl -UseBasicParsing -TimeoutSec 3
        if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
            $backendReady = $true
            Write-Host ("Backend health check passed: {0}" -f $backendHealthUrl)
            break
        }
    } catch {
        Write-Host ("Waiting for backend on 127.0.0.1:8000... attempt {0}/40" -f $attempt)
    }
}
if (-not $backendReady) {
    throw "Backend did not become healthy at $backendHealthUrl. Check the backend PowerShell window for the uvicorn error."
}

Write-Section 'Starting frontend'
$escapedFrontendRoot = $frontendRoot.Replace("'", "''")
$frontendCommand = "Set-Location -LiteralPath '$escapedFrontendRoot'; & '$npmCommand' run dev -- --host 0.0.0.0"
Start-Process -FilePath 'powershell' -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', $frontendCommand -WindowStyle Hidden | Out-Null

Write-Section 'Launch complete'
Write-Host 'Backend:  http://localhost:8000/docs'
Write-Host 'Frontend: http://localhost:5173'
