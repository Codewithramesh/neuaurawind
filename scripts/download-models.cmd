@echo off
setlocal DisableDelayedExpansion
call "%~dp0windows-run.cmd" scripts\manage.py models %*
exit /b %errorlevel%
