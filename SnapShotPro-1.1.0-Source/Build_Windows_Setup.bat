@echo off
setlocal
cd /d "%~dp0"
if exist ".venv-build\Scripts\python.exe" goto build
where py >nul 2>nul
if errorlevel 1 (
    python -m venv .venv-build
) else (
    py -3 -m venv .venv-build
)
:: Kill lingering instances to avoid file lock / Access Denied error
taskkill /f /im "SnapShot_Pro_Setup.exe" >nul 2>nul
taskkill /f /im "SnapShotPro.exe" >nul 2>nul

:build
".venv-build\Scripts\python.exe" -m pip install -r requirements-build.txt
if errorlevel 1 goto failed
".venv-build\Scripts\python.exe" build_all.py --windows %*
if errorlevel 1 goto failed
echo Portable output is in dist\SnapShotPro and the matching ZIP.
echo Inno Setup 6 is required for the optional Setup.exe.
pause
exit /b 0
:failed
echo Build failed. Read the error above. No successful build is being claimed.
pause
exit /b 1
