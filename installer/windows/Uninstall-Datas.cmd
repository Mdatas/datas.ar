@echo off
title Datas.ar uninstaller
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-Datas.ps1" -Uninstall %*
echo.
pause
