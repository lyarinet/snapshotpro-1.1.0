@echo off
title GitHub Private Repo Auto-Setup
cd /d "%~dp0"

echo ========================================================
echo       GitHub Private Repo Auto-Setup ^& Manager
echo ========================================================
echo Starting PowerShell with ExecutionPolicy Bypass...
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0github_auto_setup.ps1" %*

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Setup encountered an issue or was cancelled.
    pause
)
