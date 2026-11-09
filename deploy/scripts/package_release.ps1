param(
    [Parameter(Mandatory=$true)][string]$Version,
    [string]$ProjectRoot,
    [string]$PlannerRoot,
    [string]$PostgresRoot,
    [Parameter(Mandatory=$true)][string]$OutputDirectory,
    [string]$PythonExe,
    [switch]$AllowDirty
)
$ErrorActionPreference='Stop'
if ([string]::IsNullOrWhiteSpace($ProjectRoot)) { $ProjectRoot=(Resolve-Path (Join-Path $PSScriptRoot '..\..')).ProviderPath }
if ([string]::IsNullOrWhiteSpace($PlannerRoot)) { $PlannerRoot=Join-Path (Split-Path $ProjectRoot -Parent) 'planner' }
if ([string]::IsNullOrWhiteSpace($PythonExe)) { $PythonExe=Join-Path $ProjectRoot '.venv\Scripts\python.exe' }
$arguments=@((Join-Path $PSScriptRoot 'build_deployment.py'),'--project-root',$ProjectRoot,'--planner-root',$PlannerRoot,'--version',$Version,'--output',$OutputDirectory)
if ($PostgresRoot) { $arguments+=@('--postgres-root',$PostgresRoot) }
if ($AllowDirty) { $arguments+='--allow-dirty' }
& $PythonExe @arguments
if ($LASTEXITCODE -ne 0) { throw 'Deployment packaging failed; source files and existing installations were retained.' }
