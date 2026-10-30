@echo off
setlocal DisableDelayedExpansion
call "%~dp0windows-run.cmd" scripts\manage.py dev %*
exit /b %errorlevel%
