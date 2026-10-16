@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto install
where py >nul 2>nul
if errorlevel 1 (
    python -m venv .venv
) else (
    py -3 -m venv .venv
)
if errorlevel 1 goto failed
:install
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
start "" ".venv\Scripts\pythonw.exe" snapshot_pro.py
exit /b 0
:failed
echo Setup failed. Install Python 3.11 or newer and try again.
pause
exit /b 1
