@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (python launcher.py) else (py -3 launcher.py)
pause
