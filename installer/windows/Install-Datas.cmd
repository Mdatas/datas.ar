@echo off
:: Double-click installer for Datas.ar (runs the PowerShell script with the execution policy bypassed for this run only).
title Datas.ar installer
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-Datas.ps1" %*
echo.
pause
