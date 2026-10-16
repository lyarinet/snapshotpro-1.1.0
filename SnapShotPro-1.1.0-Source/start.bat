@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" snapshot_pro.py %*
) else (
    call Run_Setup.bat
)
