@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_app.ps1" %*
endlocal

