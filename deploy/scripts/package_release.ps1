param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$')]
    [string]$Version,
    [string]$ProjectRoot,
    [string]$OutputDirectory,
    [string]$PythonExe,
    [switch]$SkipVerification
)

$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'

function Write-Section([string]$Title) {
    Write-Host ""
    Write-Host ("[RELEASE] {0}" -f $Title)
}

function Write-Utf8NoBom([string]$Path, [string]$Content) {
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $encoding)
}

function Invoke-Native([string]$FilePath, [string[]]$Arguments, [string]$WorkingDirectory) {
    Push-Location -LiteralPath $WorkingDirectory
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $FilePath @Arguments
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
        Pop-Location
    }
    if ($exitCode -ne 0) {
        throw ("Command failed with exit code {0}: {1} {2}" -f $exitCode, $FilePath, ($Arguments -join ' '))
    }
}

function Get-NativeOutput([string]$FilePath, [string[]]$Arguments, [string]$WorkingDirectory) {
    Push-Location -LiteralPath $WorkingDirectory
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = & $FilePath @Arguments
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
        Pop-Location
    }
    if ($exitCode -ne 0) {
        throw ("Command failed with exit code {0}: {1} {2}" -f $exitCode, $FilePath, ($Arguments -join ' '))
    }
    return (($output | ForEach-Object { $_.ToString() }) -join "`n").Trim()
}

function Copy-ReleaseDirectory([string]$RelativePath, [string]$DestinationRoot) {
    $source = Join-Path -Path $ProjectRoot -ChildPath $RelativePath
    if (-not (Test-Path -LiteralPath $source -PathType Container)) {
        throw "Required release directory not found: $RelativePath"
    }
    $destination = Join-Path -Path $DestinationRoot -ChildPath $RelativePath
    $parent = Split-Path -Parent $destination
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination -Recurse
}

function Copy-ReleaseFile([string]$RelativePath, [string]$DestinationRoot) {
    $source = Join-Path -Path $ProjectRoot -ChildPath $RelativePath
    if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
        throw "Required release file not found: $RelativePath"
    }
    $destination = Join-Path -Path $DestinationRoot -ChildPath $RelativePath
    $parent = Split-Path -Parent $destination
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination
}

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..\..')).ProviderPath
} else {
    $ProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).ProviderPath
}
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path -Path $ProjectRoot -ChildPath 'release'
} elseif (-not [System.IO.Path]::IsPathRooted($OutputDirectory)) {
    $OutputDirectory = Join-Path -Path $ProjectRoot -ChildPath $OutputDirectory
}
$OutputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)
if ([string]::IsNullOrWhiteSpace($PythonExe)) {
    $PythonExe = Join-Path -Path $ProjectRoot -ChildPath '.venv\Scripts\python.exe'
}
if (-not (Test-Path -LiteralPath $PythonExe -PathType Leaf)) {
    throw "Python executable not found: $PythonExe"
}

$npmCommand = if (Get-Command 'npm.cmd' -ErrorAction SilentlyContinue) { 'npm.cmd' } else { 'npm' }
$tagName = "v$Version"
$commit = Get-NativeOutput 'git' @('rev-parse', 'HEAD') $ProjectRoot
$shortCommit = Get-NativeOutput 'git' @('rev-parse', '--short=12', 'HEAD') $ProjectRoot
$worktreeStatus = Get-NativeOutput 'git' @('status', '--porcelain') $ProjectRoot
if (-not [string]::IsNullOrWhiteSpace($worktreeStatus)) {
    throw "Release packaging requires a clean Git worktree. Commit or remove local changes first."
}
$existingTag = Get-NativeOutput 'git' @('tag', '--list', $tagName) $ProjectRoot
if (-not [string]::IsNullOrWhiteSpace($existingTag)) {
    throw "Release tag already exists: $tagName"
}

Write-Host ("ProjectRoot: {0}" -f $ProjectRoot)
Write-Host ("Version:     {0}" -f $Version)
Write-Host ("Commit:      {0}" -f $commit)
Write-Host ("Output:      {0}" -f $OutputDirectory)

if (-not $SkipVerification) {
    Write-Section 'Source checks'
    Invoke-Native 'git' @('diff', '--check', 'HEAD^', 'HEAD') $ProjectRoot
    Invoke-Native $PythonExe @('scripts/check_terminology.py') $ProjectRoot

    Write-Section 'Backend tests'
    Invoke-Native $PythonExe @('-m', 'pytest', '-q') $ProjectRoot

    Write-Section 'Deployment readiness'
    Invoke-Native $PythonExe @('scripts/check_deploy_readiness.py', '--strict-data') $ProjectRoot

    Write-Section 'Frontend Chromium regression'
    Invoke-Native $npmCommand @('run', 'test:e2e', '--', '--project=chromium', '--workers=1') (Join-Path $ProjectRoot 'frontend')
}

Write-Section 'Frontend production build'
$previousBuildVersion = [Environment]::GetEnvironmentVariable('VITE_APP_VERSION', 'Process')
try {
    $env:VITE_APP_VERSION = $Version
    Invoke-Native $npmCommand @('run', 'build') (Join-Path $ProjectRoot 'frontend')
} finally {
    if ($null -eq $previousBuildVersion) {
        Remove-Item Env:VITE_APP_VERSION -ErrorAction SilentlyContinue
    } else {
        $env:VITE_APP_VERSION = $previousBuildVersion
    }
}

$postBuildStatus = Get-NativeOutput 'git' @('status', '--porcelain') $ProjectRoot
if (-not [string]::IsNullOrWhiteSpace($postBuildStatus)) {
    throw "The production build changed tracked files. Commit the generated frontend/dist output, then rerun packaging."
}

Write-Section 'Building clean artifact'
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
$artifactBase = "Solver_demo_project-$tagName-win-x64"
$stagingParent = Join-Path -Path $OutputDirectory -ChildPath '.staging'
$stagingRoot = Join-Path -Path $stagingParent -ChildPath $artifactBase
if (Test-Path -LiteralPath $stagingParent) {
    Remove-Item -LiteralPath $stagingParent -Recurse -Force
}
New-Item -ItemType Directory -Path $stagingRoot -Force | Out-Null

@('app', 'migrations', 'deploy', 'scripts', 'seeds', 'frontend\dist') | ForEach-Object {
    Copy-ReleaseDirectory $_ $stagingRoot
}
@('.env.example', 'alembic.ini', 'requirements.txt', 'README.md') | ForEach-Object {
    Copy-ReleaseFile $_ $stagingRoot
}

$releaseTimestamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
$releaseId = "$tagName+$releaseTimestamp"
$releaseLevel = if ($Version -match '(?i)(^|[.-])beta([.-]|$)') {
    'beta release'
} elseif ($Version -match '(?i)(^|[.-])rc([.-]|$)') {
    'release candidate'
} elseif ($Version.Contains('-')) {
    'pre-release'
} else {
    'stable release'
}
$versionPayload = [ordered]@{
    app_version = $Version
    app_commit = $commit
    release_id = $releaseId
}
$versionJson = $versionPayload | ConvertTo-Json
Write-Utf8NoBom -Path (Join-Path $stagingRoot 'VERSION.json') -Content $versionJson

$releaseNotes = @"
# Solver Demo Project $tagName

- Release level: $releaseLevel
- Target: Windows verifier machine, existing PostgreSQL upgrade
- Source commit: $commit
- Release ID: $releaseId
- Migration head: 013_plan_adjustment

## Install

1. Back up the existing PostgreSQL database with pg_dump -Fc.
2. Extract this package into a new version directory.
3. Copy the verifier machine's existing .env into the new directory.
4. Run deploy/scripts/install_verify.ps1 -ExpectedCommit $commit.
5. Verify /health and /api/v1/system/status?include_data_checks=true.

## Known non-blocking warnings

- The Vite production build reports the existing large-chunk warning.
- A Network Editor geometry assertion can be timing-sensitive under high-worker stress; focused single-worker reruns pass.

The package intentionally excludes .env, databases, PostgreSQL data, virtual environments, logs, caches, PID files, development dependencies, and historical release archives.
"@
$notesName = "RELEASE_NOTES-$tagName.md"
$releaseNotes | Set-Content -LiteralPath (Join-Path $stagingRoot $notesName) -Encoding UTF8
$releaseNotes | Set-Content -LiteralPath (Join-Path $OutputDirectory $notesName) -Encoding UTF8

$manifestLines = Get-ChildItem -LiteralPath $stagingRoot -File -Recurse |
    Sort-Object FullName |
    ForEach-Object {
        $relative = $_.FullName.Substring($stagingRoot.Length + 1).Replace('\', '/')
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()
        "$hash  $relative"
    }
$manifestLines | Set-Content -LiteralPath (Join-Path $stagingRoot 'MANIFEST.sha256') -Encoding ASCII

$zipPath = Join-Path -Path $OutputDirectory -ChildPath "$artifactBase.zip"
if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
Compress-Archive -LiteralPath $stagingRoot -DestinationPath $zipPath -CompressionLevel Optimal
$zipHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $zipPath).Hash.ToLowerInvariant()
$checksumPath = "$zipPath.sha256"
"$zipHash  $([System.IO.Path]::GetFileName($zipPath))" | Set-Content -LiteralPath $checksumPath -Encoding ASCII
Remove-Item -LiteralPath $stagingParent -Recurse -Force

Write-Section 'Release artifact complete'
Write-Host ("ZIP:      {0}" -f $zipPath)
Write-Host ("SHA-256:  {0}" -f $checksumPath)
Write-Host ("Notes:    {0}" -f (Join-Path $OutputDirectory $notesName))
Write-Host ("Next: create annotated tag with git tag -a {0} {1} -m 'Solver Demo Project {0}'" -f $tagName, $commit)
