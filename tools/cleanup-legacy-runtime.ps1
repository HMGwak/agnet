$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoDir = Split-Path -Parent $scriptDir

Set-Location $repoDir

$ports = @(3000, 8001, 8765)
$legacyPaths = @(
    ".codex",
    ".codex-sdk",
    "codex-sidecar",
    "codex-login.bat",
    "codex-login.ps1",
    "codex-login.sh",
    "codex-policy.toml",
    "codex-contract.toml",
    "database",
    "logs",
    "repos",
    "workspaces",
    "%SystemDrive%",
    "backend\app\prompts"
)

$removed = New-Object System.Collections.Generic.List[string]
$failed = New-Object System.Collections.Generic.List[string]

Write-Host "Repo root: $repoDir"
Write-Host "Stopping app processes on ports 3000, 8001, 8765..."

foreach ($port in $ports) {
    $pids = @(
        Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
    )

    foreach ($pid in $pids) {
        try {
            Stop-Process -Id $pid -Force -ErrorAction Stop
            Write-Host "Stopped PID $pid on port $port"
        }
        catch {
            $failed.Add("Failed to stop PID $pid on port ${port}: $($_.Exception.Message)")
        }
    }
}

Write-Host ""
Write-Host "Removing legacy root paths..."

foreach ($path in $legacyPaths) {
    if (-not (Test-Path $path)) {
        continue
    }

    try {
        Remove-Item $path -Recurse -Force -ErrorAction Stop
        $removed.Add($path)
        Write-Host "Removed: $path"
    }
    catch {
        $failed.Add("Failed to remove ${path}: $($_.Exception.Message)")
    }
}

Write-Host ""
Write-Host "Verifying canonical contract..."
try {
    & python tools\codex_contract.py verify
}
catch {
    $failed.Add("Failed to run codex contract verify: $($_.Exception.Message)")
}

Write-Host ""
Write-Host "Removed paths:"
if ($removed.Count -eq 0) {
    Write-Host "  (none)"
}
else {
    foreach ($item in $removed) {
        Write-Host "  $item"
    }
}

Write-Host ""
Write-Host "Remaining root entries:"
Get-ChildItem -Force -Name | ForEach-Object { Write-Host "  $_" }

if ($failed.Count -gt 0) {
    Write-Host ""
    Write-Host "Failures:"
    foreach ($item in $failed) {
        Write-Host "  $item"
    }
    exit 1
}

Write-Host ""
Write-Host "Legacy cleanup completed."
