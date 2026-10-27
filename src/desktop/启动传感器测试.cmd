@echo off
cd /d "%~dp0"
py -3 sensor_client.py %*
if errorlevel 1 pause
