$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoDir = Split-Path -Parent $scriptDir
$sidecarDir = Join-Path $repoDir "runtime\codex\sidecar"
$codexHome = Join-Path $repoDir "runtime\codex\home"
$configFile = Join-Path $codexHome "config.toml"
$appData = Join-Path $codexHome "AppData\Roaming"
$localAppData = Join-Path $codexHome "AppData\Local"

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm is not installed or not on PATH."
}

Push-Location $sidecarDir
if (-not (Test-Path "node_modules")) {
    & npm install
}
Pop-Location

New-Item -ItemType Directory -Force -Path $codexHome | Out-Null
New-Item -ItemType Directory -Force -Path $appData | Out-Null
New-Item -ItemType Directory -Force -Path $localAppData | Out-Null
Set-Content -Path $configFile -Value "cli_auth_credentials_store = `"file`"`nforced_login_method = `"chatgpt`"`n"

$codexCmd = Join-Path $sidecarDir "node_modules\.bin\codex.cmd"
if (-not (Test-Path $codexCmd)) {
    throw "Local Codex runtime not found: $codexCmd"
}

$previous = @{
    HOME = $env:HOME
    USERPROFILE = $env:USERPROFILE
    APPDATA = $env:APPDATA
    LOCALAPPDATA = $env:LOCALAPPDATA
    CODEX_HOME = $env:CODEX_HOME
    OPENAI_API_KEY = $env:OPENAI_API_KEY
    CODEX_API_KEY = $env:CODEX_API_KEY
    OPENAI_BASE_URL = $env:OPENAI_BASE_URL
}

try {
    $env:HOME = $codexHome
    $env:USERPROFILE = $codexHome
    $env:APPDATA = $appData
    $env:LOCALAPPDATA = $localAppData
    $env:CODEX_HOME = $codexHome
    Remove-Item Env:OPENAI_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:CODEX_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:OPENAI_BASE_URL -ErrorAction SilentlyContinue

    & $codexCmd login --device-auth
} finally {
    foreach ($key in $previous.Keys) {
        if ($null -eq $previous[$key] -or $previous[$key] -eq "") {
            Remove-Item "Env:$key" -ErrorAction SilentlyContinue
        } else {
            Set-Item "Env:$key" $previous[$key]
        }
    }
}

if (-not (Test-Path (Join-Path $codexHome "auth.json"))) {
    throw "Codex OAuth login did not create auth.json under $codexHome"
}

Write-Host "Repository-local Codex OAuth login complete: $(Join-Path $codexHome 'auth.json')"
