# toji-shell/summon.ps1
# Direct summoner for Toji Desktop Pet and Chat Overlay on Windows

$ErrorActionPreference = "Stop"

# 1. Verify backend health
$backendUrl = "http://127.0.0.1:8000/health"
$backendUp = $false
try {
    $resp = Invoke-RestMethod -Uri $backendUrl -TimeoutSec 2 -ErrorAction SilentlyContinue
    if ($resp.status -eq "ok") { $backendUp = $true }
} catch {}

if (-not $backendUp) {
    Write-Host "[Toji] Starting FastAPI backend server..." -ForegroundColor Cyan
    $projectRoot = Split-Path -Parent $PSScriptRoot
    Start-Process -FilePath "uvicorn" -ArgumentList "orchestrator_core.main:app --host 127.0.0.1 --port 8000 --log-level warning" -WorkingDirectory $projectRoot -WindowStyle Hidden
    Start-Sleep -Seconds 2
}

# 2. Kill any stale electron processes holding the lock
$existing = Get-Process -Name electron -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "[Toji] Releasing electron lock..." -ForegroundColor Yellow
    Stop-Process -Name electron -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 600
}

# 3. Setup environment and launch Electron
$shellDir = $PSScriptRoot
$env:NODE_PATH = "C:\Users\aaqil\toji-shell-deps\node_modules"
$env:TOJI_DEV  = "1"

$electronCmd = "C:\Users\aaqil\toji-shell-deps\node_modules\.bin\electron.cmd"

Write-Host "[Toji] Summoning Desktop Pet & Chat Overlay..." -ForegroundColor Green
Start-Process -FilePath $electronCmd -ArgumentList "`"$shellDir`"" -WorkingDirectory $shellDir -WindowStyle Hidden

Write-Host "[Toji] Summoned! Desktop Pet is active at bottom-right corner. Press Alt+T to toggle chat." -ForegroundColor Cyan
