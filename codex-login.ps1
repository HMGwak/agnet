$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectCodexHome = Join-Path $scriptDir ".codex"
$globalCodexHome = Join-Path $HOME ".codex"
$projectAuth = Join-Path $projectCodexHome "auth.json"
$globalAuth = Join-Path $globalCodexHome "auth.json"

New-Item -ItemType Directory -Force -Path $projectCodexHome | Out-Null

if (-not (Test-Path $projectAuth) -and (Test-Path $globalAuth) -and ($projectCodexHome -ne $globalCodexHome)) {
    Copy-Item -Path $globalAuth -Destination $projectAuth
}

$env:CODEX_HOME = $projectCodexHome

Write-Host "Using project Codex home: $env:CODEX_HOME"
& codex login
