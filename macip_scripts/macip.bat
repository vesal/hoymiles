@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if not errorlevel 1 (
    py -3 "%~dp0macip_local_server.py"
) else (
    python "%~dp0macip_local_server.py"
)

if errorlevel 1 pause
