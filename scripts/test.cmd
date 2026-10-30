@echo off
setlocal DisableDelayedExpansion
call "%~dp0windows-run.cmd" scripts\manage.py test %*
exit /b %errorlevel%
