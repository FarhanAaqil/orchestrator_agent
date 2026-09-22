# toji-shell/summon.ps1
# Direct summoner for Toji Desktop Pet and Chat Overlay on Windows

$ErrorActionPreference = "Stop"

# 1. Kill any stale electron processes holding the lock
$existing = Get-Process -Name electron -ErrorAction SilentlyContinue
if ($existing) {
    Stop-Process -Name electron -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 500
}

# 2. Setup environment and launch Electron directly
$shellDir    = $PSScriptRoot
$env:NODE_PATH = "C:\Users\aaqil\toji-shell-deps\node_modules"
$env:TOJI_DEV  = "1"

$cmdExe = "C:\Users\aaqil\toji-shell-deps\node_modules\.bin\electron.cmd"

Write-Host "[Toji] Summoning Desktop Pet & Chat Overlay..." -ForegroundColor Green
Start-Process -FilePath "cmd.exe" -ArgumentList "/c `"`"$cmdExe`" .`"" -WorkingDirectory $shellDir -WindowStyle Hidden
Write-Host "[Toji] Summoned successfully." -ForegroundColor Cyan
