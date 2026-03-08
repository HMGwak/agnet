$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $scriptDir "backend"
$dashboardDir = Join-Path $scriptDir "dashboard"
$runtimeCodexDir = Join-Path $scriptDir "runtime\codex"
$sidecarDir = Join-Path $runtimeCodexDir "sidecar"
$projectDir = Join-Path $scriptDir "project"
$logsDir = Join-Path $projectDir "logs"
$codexHome = Join-Path $projectDir "app-codex-home"
$codexAuthFile = Join-Path $codexHome "auth.json"
$codexConfigFile = Join-Path $codexHome "config.toml"
$backendPort = 8001
$dashboardPort = 3000
$sidecarPort = 8765

function Require-Command {
    param(
        [string]$Name,
        [string]$InstallHint
    )

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name is not installed or not on PATH.`n$InstallHint"
    }
}

function Stop-PortProcess {
    param([int]$Port)

    $ids = @(
        Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
    )

    if ($ids.Count -gt 0) {
        Stop-Process -Id $ids -Force -ErrorAction SilentlyContinue
    }
}

function Ensure-CodexAuth {
    param(
        [string]$AuthFile,
        [string]$LoginScript
    )

    if (Test-Path $AuthFile) {
        return
    }

    Write-Host "Project-local Codex OAuth login is required."
    Write-Host "Launching login flow..."
    & $LoginScript

    if (-not (Test-Path $AuthFile)) {
        throw "Codex OAuth login did not create auth.json: $AuthFile"
    }
}

Write-Host "Starting AI Dev Automation Dashboard..."

Require-Command -Name "uv" -InstallHint "Install it with: winget install --id=astral-sh.uv -e"
Require-Command -Name "npm" -InstallHint "Install Node.js LTS from https://nodejs.org/ and reopen the terminal."

Write-Host "Stopping existing processes on ports $backendPort, $dashboardPort, and $sidecarPort..."
Stop-PortProcess -Port $backendPort
Stop-PortProcess -Port $dashboardPort
Stop-PortProcess -Port $sidecarPort

Write-Host "Preparing backend virtual environment with uv..."
Push-Location $backendDir
& uv sync --extra dev
Pop-Location

$venvPython = Join-Path $backendDir ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "Expected virtual environment Python was not created: $venvPython"
}

Write-Host "Preparing dashboard dependencies..."
Push-Location $dashboardDir
if (Test-Path "package-lock.json") {
    if (Test-Path "node_modules") {
        & npm install
    } else {
        & npm ci
    }
} else {
    & npm install
}
Pop-Location

Write-Host "Preparing Codex sidecar dependencies..."
Push-Location $sidecarDir
if (Test-Path "package-lock.json") {
    if (Test-Path "node_modules") {
        & npm install
    } else {
        & npm ci
    }
} else {
    & npm install
}
Pop-Location

New-Item -ItemType Directory -Force -Path (Join-Path $projectDir "database") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $projectDir "repos") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $projectDir "workspaces") | Out-Null
New-Item -ItemType Directory -Force -Path $logsDir | Out-Null
New-Item -ItemType Directory -Force -Path $codexHome | Out-Null
$sessionId = Get-Date -Format "yyMMdd_HHmmss"
$sessionLogsDir = Join-Path $logsDir $sessionId
$tasksLogsDir = Join-Path $sessionLogsDir "tasks"
$latestMarker = Join-Path $logsDir "latest"
$sessionMetaPath = Join-Path $sessionLogsDir "session.json"
$backendOutLog = Join-Path $sessionLogsDir "backend.out.log"
$backendErrLog = Join-Path $sessionLogsDir "backend.err.log"
$dashboardOutLog = Join-Path $sessionLogsDir "dashboard.out.log"
$dashboardErrLog = Join-Path $sessionLogsDir "dashboard.err.log"
New-Item -ItemType Directory -Force -Path $sessionLogsDir | Out-Null
New-Item -ItemType Directory -Force -Path $tasksLogsDir | Out-Null
Set-Content -Path $latestMarker -Value $sessionId
if (-not (Test-Path $codexConfigFile)) {
    Set-Content -Path $codexConfigFile -Value "cli_auth_credentials_store = `"file`"`nforced_login_method = `"chatgpt`"`n"
}
Ensure-CodexAuth -AuthFile $codexAuthFile -LoginScript (Join-Path $scriptDir "tools\codex-login.ps1")

$npmCmd = (Get-Command "npm.cmd" -ErrorAction Stop).Source
$env:SESSION_ID = $sessionId
$env:SESSION_LOGS_DIR = $sessionLogsDir

$backend = Start-Process `
    -FilePath $venvPython `
    -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "$backendPort" `
    -WorkingDirectory $backendDir `
    -RedirectStandardOutput $backendOutLog `
    -RedirectStandardError $backendErrLog `
    -WindowStyle Hidden `
    -PassThru

$frontend = Start-Process `
    -FilePath $npmCmd `
    -ArgumentList "run", "dev" `
    -WorkingDirectory $dashboardDir `
    -RedirectStandardOutput $dashboardOutLog `
    -RedirectStandardError $dashboardErrLog `
    -WindowStyle Hidden `
    -PassThru

@{
    session_id = $sessionId
    started_at = (Get-Date).ToString("o")
    logs_dir = $sessionLogsDir
    ports = @{
        backend = $backendPort
        dashboard = $dashboardPort
        sidecar = $sidecarPort
    }
    processes = @{
        backend = $backend.Id
        dashboard = $frontend.Id
        sidecar = $null
    }
} | ConvertTo-Json -Depth 5 | Set-Content -Path $sessionMetaPath

Write-Host ""
Write-Host "Session:   $sessionId"
Write-Host "Backend:   http://localhost:$backendPort"
Write-Host "Dashboard: http://localhost:$dashboardPort"
Write-Host "Codex auth cache: $codexAuthFile"
Write-Host "Session logs: $sessionLogsDir"
Write-Host "Backend logs:   $backendOutLog / $backendErrLog"
Write-Host "Dashboard logs: $dashboardOutLog / $dashboardErrLog"
Write-Host "Press Ctrl+C to stop."

try {
    while ($true) {
        Start-Sleep -Seconds 2

        if ($backend.HasExited -or $frontend.HasExited) {
            break
        }
    }
}
finally {
    if ($backend -and -not $backend.HasExited) {
        Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
    }
    if ($frontend -and -not $frontend.HasExited) {
        Stop-Process -Id $frontend.Id -Force -ErrorAction SilentlyContinue
    }
}

if ($backend.HasExited) {
    Write-Host ""
    Write-Host "Backend exited with code $($backend.ExitCode). Recent log output:"
    Get-Content $backendOutLog -Tail 40
    Get-Content $backendErrLog -Tail 40
}

if ($frontend.HasExited) {
    Write-Host ""
    Write-Host "Dashboard exited with code $($frontend.ExitCode). Recent log output:"
    Get-Content $dashboardOutLog -Tail 40
    Get-Content $dashboardErrLog -Tail 40
}

exit 1
