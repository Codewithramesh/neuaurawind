@echo off
setlocal DisableDelayedExpansion
call "%~dp0scripts\copy-setup-token.cmd" %*
set "NEUAURA_EXIT=%errorlevel%"
echo.
pause
exit /b %NEUAURA_EXIT%
