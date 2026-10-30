@echo off
setlocal DisableDelayedExpansion
call "%~dp0windows-run.cmd" scripts\desktop.py start %*
exit /b %errorlevel%
