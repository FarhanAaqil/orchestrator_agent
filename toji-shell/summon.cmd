@echo off
set "NODE_PATH=C:\Users\aaqil\toji-shell-deps\node_modules"
set "TOJI_DEV=1"
cd /d "%~dp0"
start "" "C:\Users\aaqil\toji-shell-deps\node_modules\electron\dist\electron.exe" main.js
