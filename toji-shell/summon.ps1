# toji-shell/summon.ps1
# Direct summoner for Orchestrator Agent Executive Control Panel on Windows

$ErrorActionPreference = "Stop"

$shellDir    = $PSScriptRoot
$env:NODE_PATH = "C:\Users\aaqil\toji-shell-deps\node_modules"
$env:TOJI_DEV  = "1"

$electronExe = "C:\Users\aaqil\toji-shell-deps\node_modules\electron\dist\electron.exe"

# If an instance is already running, launching brings the existing Executive Control Panel to focus
$existing = Get-Process -Name electron -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "[Orchestrator Agent] Executive Control Panel already running -- focusing window..." -ForegroundColor Cyan
} else {
    Write-Host "[Orchestrator Agent] Launching Executive Control Panel..." -ForegroundColor Green
}

Start-Process -FilePath $electronExe -ArgumentList @("main.js") -WorkingDirectory $shellDir
Write-Host "[Orchestrator Agent] Launched." -ForegroundColor Cyan
