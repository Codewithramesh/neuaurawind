@echo off
setlocal DisableDelayedExpansion
set "PYTHONUTF8=1"
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Run Setup NEUAURA.cmd first. Windows needs its own .venv; do not copy a Mac environment.
  exit /b 1
)
".venv\Scripts\python.exe" %*
exit /b %errorlevel%
