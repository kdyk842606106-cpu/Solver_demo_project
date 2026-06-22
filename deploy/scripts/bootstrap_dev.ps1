param(
    [string]$ProjectRoot,
    [switch]$DiagnosticsOnly
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

function Resolve-PythonCommand {
    $probeScript = 'import sys; print(sys.executable); print(sys.version_info[0], sys.version_info[1], sys.version_info[2], sep=chr(46)); print(sys.platform); raise SystemExit(0 if sys.version_info >= (3, 11) and sys.platform == chr(119)+chr(105)+chr(110)+chr(51)+chr(50) else 2)'
    $candidates = @(
        [PSCustomObject]@{ Exe = 'py'; Args = [string[]]@('-3.12') },
        [PSCustomObject]@{ Exe = 'py'; Args = [string[]]@('-3.11') },
        [PSCustomObject]@{ Exe = 'py'; Args = [string[]]@('-3') },
        [PSCustomObject]@{ Exe = 'python'; Args = [string[]]@() }
    )
    $attempts = New-Object System.Collections.Generic.List[string]

    foreach ($candidate in $candidates) {
        $command = Get-Command $candidate.Exe -ErrorAction SilentlyContinue
        if (-not $command) {
            $attempts.Add(("{0}: command not found" -f $candidate.Exe)) | Out-Null
            continue
        }

        $probeArgs = @()
        $probeArgs += $candidate.Args
        $probeArgs += @('-c', $probeScript)
        $previousErrorActionPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            try {
                $output = & $candidate.Exe @probeArgs 2>&1
                $exitCode = $LASTEXITCODE
            } catch {
                $output = @($_.Exception.Message)
                $exitCode = -1
            }
        } finally {
            $ErrorActionPreference = $previousErrorActionPreference
        }
        $lines = @($output | ForEach-Object { $_.ToString() })

        if ($exitCode -eq 0 -and $lines.Count -ge 3) {
            return [PSCustomObject]@{
                Exe = $candidate.Exe
                Args = [string[]]$candidate.Args
                Source = $command.Source
                Executable = $lines[0]
                Version = $lines[1]
                Platform = $lines[2]
            }
        }

        $attempts.Add(("{0} {1}: exit {2}; {3}" -f $candidate.Exe, ($candidate.Args -join ' '), $exitCode, ($lines -join ' | '))) | Out-Null
    }

    throw ("No usable Windows Python 3.11+ was found. Attempts: {0}" -f ($attempts -join ' ; '))
}

function Invoke-PythonCommand([object]$PythonCommand, [string[]]$Arguments) {
    $allArgs = @()
    $allArgs += $PythonCommand.Args
    $allArgs += $Arguments
    Invoke-Native $PythonCommand.Exe $allArgs
}

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = Find-ProjectRoot
} else {
    $ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).ProviderPath.TrimEnd('\')
}

$venvRoot = Join-Path -Path $ProjectRoot -ChildPath '.venv'
$venvScripts = Join-Path -Path $venvRoot -ChildPath 'Scripts'
$venvPython = Join-Path -Path $venvScripts -ChildPath 'python.exe'
$frontendRoot = Join-Path -Path $ProjectRoot -ChildPath 'frontend'
$registryFile = Join-Path -Path $frontendRoot -ChildPath '.npmrc'
$projectRootName = Split-Path -Leaf $ProjectRoot
$projectParentName = Split-Path -Leaf (Split-Path -Parent $ProjectRoot)

Set-Location -LiteralPath $ProjectRoot

Write-Host "============================================"
Write-Host "  Intranet Dev Environment Bootstrap"
Write-Host "============================================"

$pythonCommand = Resolve-PythonCommand
Assert-Command 'npm' 'Install Node.js and ensure npm is on PATH.'

Write-Section 'Diagnostics'
Write-Host "PSScriptRoot: $PSScriptRoot"
Write-Host "ProjectRoot:  $ProjectRoot"
Write-Host "VenvRoot:     $venvRoot"
Write-Host "VenvPython:   $venvPython"
Write-Host ("Python cmd:   {0} {1}" -f $pythonCommand.Exe, ($pythonCommand.Args -join ' '))
Write-Host "Python source:$($pythonCommand.Source)"
Write-Host "Python exe:   $($pythonCommand.Executable)"
Write-Host "Python ver:   $($pythonCommand.Version)"
Write-Host "Python plat:  $($pythonCommand.Platform)"

if ($projectRootName -eq $projectParentName) {
    Write-Host "[WARN] Project appears to be nested in a duplicate folder: $ProjectRoot"
    Write-Host "[WARN] Prefer extracting the package contents directly into the target Solver_demo_project folder."
}

if ($DiagnosticsOnly) {
    Write-Host "Diagnostics only; no changes were made."
    exit 0
}

Write-Section 'Preparing .env'
if (-not (Test-Path -LiteralPath (Join-Path -Path $ProjectRoot -ChildPath '.env'))) {
    Copy-Item -LiteralPath (Join-Path -Path $ProjectRoot -ChildPath '.env.example') -Destination (Join-Path -Path $ProjectRoot -ChildPath '.env')
    Write-Host 'Created .env from .env.example'
} else {
    Write-Host '.env already exists'
}

Write-Section 'Creating virtual environment'
if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    Invoke-PythonCommand $pythonCommand @('-m', 'venv', $venvRoot)
    Write-Host '.venv create command completed'
} else {
    Write-Host '.venv already exists'
}

if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    $posixPython = Join-Path -Path (Join-Path -Path $venvRoot -ChildPath 'bin') -ChildPath 'python'
    if (Test-Path -LiteralPath $posixPython) {
        throw "A POSIX-style virtual environment was created at $venvRoot. Run this script with a Windows Python 3.11+ interpreter."
    }
    throw "Virtual environment python was not created at: $venvPython. If $venvRoot exists from a failed run, delete it and rerun start.intranet.bat."
}
Write-Host "Using venv python: $venvPython"

Write-Section 'Upgrading pip'
Invoke-Native $venvPython @('-m', 'pip', 'install', '--upgrade', 'pip')

Write-Section 'Installing backend dependencies'
Invoke-Native $venvPython @('-m', 'pip', 'install', '-r', 'requirements.txt')

Write-Section 'Checking PostgreSQL connectivity'
Invoke-Native $venvPython @('scripts/test_db_connection.py')

Write-Section 'Checking npm registry'
if (-not (Test-Path -LiteralPath $registryFile)) {
    throw 'frontend/.npmrc not found. Create it from the repository template and point NPM_REGISTRY to the company mirror.'
}
$registryLine = Get-Content -LiteralPath $registryFile | Where-Object { $_ -match '^registry=' } | Select-Object -First 1
if ([string]::IsNullOrWhiteSpace($registryLine)) {
    throw 'frontend/.npmrc does not define registry=. Please configure the company npm mirror.'
}
Write-Host $registryLine

Write-Section 'Installing frontend dependencies'
Set-Location -LiteralPath $frontendRoot
Invoke-Native 'npm' @('install')
Set-Location -LiteralPath $ProjectRoot

Write-Section 'Bootstrap complete'
Write-Host 'Environment is ready. Use start.intranet.bat for daily launch.'
