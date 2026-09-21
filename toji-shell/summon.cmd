@echo off
taskkill /F /IM electron.exe >nul 2>&1
set "NODE_PATH=C:\Users\aaqil\toji-shell-deps\node_modules"
set "TOJI_DEV=1"
start "" "C:\Users\aaqil\toji-shell-deps\node_modules\electron\dist\electron.exe" "%~dp0."
