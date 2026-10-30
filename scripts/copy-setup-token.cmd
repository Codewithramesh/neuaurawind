@echo off
setlocal DisableDelayedExpansion
call "%~dp0windows-run.cmd" scripts\desktop.py copy-setup-token %*
exit /b %errorlevel%
