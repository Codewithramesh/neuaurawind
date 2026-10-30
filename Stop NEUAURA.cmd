@echo off
setlocal DisableDelayedExpansion
call "%~dp0scripts\stop.cmd" %*
set "NEUAURA_EXIT=%errorlevel%"
echo.
pause
exit /b %NEUAURA_EXIT%
