@echo off
setlocal DisableDelayedExpansion
set "PYTHONUTF8=1"
cd /d "%~dp0.."
where py >nul 2>nul
if errorlevel 1 (
  echo Install Python 3.12 x64 from https://www.python.org/downloads/windows/ with the Python launcher enabled. Then reopen this window.
  exit /b 1
)
py -3.12 scripts\setup.py %*
exit /b %errorlevel%
