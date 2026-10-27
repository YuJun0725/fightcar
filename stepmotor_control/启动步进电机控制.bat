@echo off
chcp 65001 >nul
setlocal
set "STEPPER_APP_DIR=%~dp0步进电机简易控制"
if not exist "%STEPPER_APP_DIR%\步进电机简易控制.exe" (
    echo 未找到程序，请保持本启动文件与“步进电机简易控制”文件夹放在同一目录。
    pause
    exit /b 1
)
start "" /D "%STEPPER_APP_DIR%" "%STEPPER_APP_DIR%\步进电机简易控制.exe"
