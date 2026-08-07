@echo off
setlocal EnableDelayedExpansion
title Finance PII Redactor - Change Master List Location

echo.
echo    Clearing your saved master list location...
powershell -Command "[Environment]::SetEnvironmentVariable(\"FPR_MASTER_LIST_DIR\",$null,\"User\")" >nul
powershell -Command "[Environment]::SetEnvironmentVariable(\"FPR_MASTER_LIST_CONFIGURED\",$null,\"User\")" >nul
echo    Done.
echo.
echo    Starting the app so you can choose again...
echo.

set "SELFDIR=%~dp0"
if "%SELFDIR:~-1%"=="\" set "SELFDIR=%SELFDIR:~0,-1%"
call "%SELFDIR%\run.bat"

endlocal
