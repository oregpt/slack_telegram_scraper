@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tray_app.ps1" %*
endlocal

