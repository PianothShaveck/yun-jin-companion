@echo off
chcp 65001 >nul
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\windows.ps1"
if errorlevel 1 exit /b 1
exit /b 0
