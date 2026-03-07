$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $scriptDir "backend"
$dashboardDir = Join-Path $scriptDir "dashboard"
$logsDir = Join-Path $scriptDir "logs"
$backendOutLog = Join-Path $logsDir "backend.out.log"
$backendErrLog = Join-Path $logsDir "backend.err.log"
$dashboardOutLog = Join-Path $logsDir "dashboard.out.log"
$dashboardErrLog = Join-Path $logsDir "dashboard.err.log"
$backendPort = 8001
$dashboardPort = 3000

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

function Reset-LogFile {
    param([string]$Path)

    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        try {
            Set-Content -Path $Path -Value ""
            return
        } catch [System.IO.IOException] {
            Start-Sleep -Milliseconds 250
        }
    }

    throw "Failed to reset log file after waiting for release: $Path"
}

Write-Host "Starting AI Dev Automation Dashboard..."

Require-Command -Name "uv" -InstallHint "Install it with: winget install --id=astral-sh.uv -e"
Require-Command -Name "npm" -InstallHint "Install Node.js LTS from https://nodejs.org/ and reopen the terminal."

Write-Host "Stopping existing processes on ports $backendPort and $dashboardPort..."
Stop-PortProcess -Port $backendPort
Stop-PortProcess -Port $dashboardPort

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

New-Item -ItemType Directory -Force -Path $logsDir | Out-Null
Reset-LogFile -Path $backendOutLog
Reset-LogFile -Path $backendErrLog
Reset-LogFile -Path $dashboardOutLog
Reset-LogFile -Path $dashboardErrLog

$npmCmd = (Get-Command "npm.cmd" -ErrorAction Stop).Source

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

Write-Host ""
Write-Host "Backend:   http://localhost:$backendPort"
Write-Host "Dashboard: http://localhost:$dashboardPort"
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
