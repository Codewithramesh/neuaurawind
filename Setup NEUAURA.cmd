@echo off
setlocal DisableDelayedExpansion
call "%~dp0scripts\setup.cmd" %*
set "NEUAURA_EXIT=%errorlevel%"
echo.
pause
exit /b %NEUAURA_EXIT%
