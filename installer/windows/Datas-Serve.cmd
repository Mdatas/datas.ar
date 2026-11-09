@echo off
title Datas.ar
set "DATAS_HOME=%LOCALAPPDATA%\Datas"
echo Datas.ar is starting. Your browser will open http://127.0.0.1:8420 - close this window to stop.
"%~dp0datas.exe" serve
if errorlevel 1 pause
