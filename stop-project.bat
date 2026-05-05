@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "STOP_SCRIPT=%SCRIPT_DIR%scripts\stop-project.ps1"

if not exist "%STOP_SCRIPT%" (
    echo [ERROR] Stop script not found: "%STOP_SCRIPT%"
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%STOP_SCRIPT%" %*
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo [ERROR] Stop project failed with exit code %EXIT_CODE%.
)

exit /b %EXIT_CODE%
