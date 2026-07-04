@echo off
setlocal EnableDelayedExpansion
title Finance PII Redactor

:: -- Colours (Windows 10+ VT100) ----------------------------------------------
for /f %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"
set "RESET=%ESC%[0m"
set "BOLD=%ESC%[1m"
set "DIM=%ESC%[2m"
set "CYAN=%ESC%[1;36m"
set "GREEN=%ESC%[1;32m"
set "YELLOW=%ESC%[1;33m"
set "RED=%ESC%[1;31m"
set "MAGENTA=%ESC%[1;35m"
set "WHITE=%ESC%[1;37m"
:: IPA brand colour (primary green #49ac57) - 24-bit truecolor (Windows 11+)
set "IPA_GREEN=%ESC%[38;2;73;172;87m"

call :banner

:: -- 1. Install uv if not already present -------------------------------------
call :stepnum 1 2 "Checking the setup helper"
where uv >nul 2>&1
if %errorlevel% neq 0 (
    call :info "First-time setup: installing a small helper (one-time)."
    call :wait "This can take a minute. Please leave this window open..."
    powershell -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex" >nul 2>&1
    if %errorlevel% neq 0 (
        call :error "Setup helper could not be installed."
        call :hint "Please check your internet connection, then run this again."
        call :bye
        exit /b 1
    )
    :: Reload PATH so uv is available in this session
    for /f "tokens=*" %%i in ('powershell -Command "[System.Environment]::GetEnvironmentVariable(\"PATH\",\"User\")"') do set "PATH=%%i;%PATH%"
    call :ok "Setup helper installed."
) else (
    call :ok "Setup helper is ready."
)

:: -- 2. Create virtual environment and install dependencies -------------------
:: Strip trailing backslash from %~dp0 before passing to --project
set "APPDIR=%~dp0"
if "%APPDIR:~-1%"=="\" set "APPDIR=%APPDIR:~0,-1%"

call :stepnum 2 2 "Preparing the program"
if not exist "%APPDIR%\.venv" (
    call :info "First-time setup: installing the program and language model (one-time)."
    call :wait "This downloads about 400 MB and can take a few minutes. Please leave this window open..."
    uv sync --python 3.12 --project "%APPDIR%" >nul 2>&1
    if %errorlevel% neq 0 (
        call :error "The program could not be set up."
        call :hint "Please check your internet connection, then run this again."
        call :bye
        exit /b 1
    )
    call :ok "Program is ready."
) else (
    call :ok "Program is ready."
)

:: -- 3. Launch the app --------------------------------------------------------
call :ready
"%APPDIR%\.venv\Scripts\streamlit.exe" run "%APPDIR%\app.py" --server.address=127.0.0.1

endlocal
goto :eof

:: -- Subroutines --------------------------------------------------------------
:banner
cls
echo.
echo  %IPA_GREEN%====================================================================%RESET%
echo.
echo      %BOLD%%WHITE%FINANCE PII REDACTOR%RESET%
echo      %DIM%Removes names and organizations from your Excel and PDF files.%RESET%
echo      %BOLD%%IPA_GREEN%Runs 100%% on your computer - nothing is ever uploaded.%RESET%
echo.
echo  %IPA_GREEN%====================================================================%RESET%
echo.
echo     %DIM%Getting things ready. This usually takes only a few seconds.%RESET%
echo     %DIM%The first time you run it, setup can take a few minutes.%RESET%
echo.
goto :eof

:stepnum
echo.
echo    %IPA_GREEN%[ Step %~1 of %~2 ]%RESET% %BOLD%%~3%RESET%
goto :eof

:ok
echo       %IPA_GREEN%[OK]%RESET% %~1
goto :eof

:info
echo       %DIM%%WHITE%[INFO]%RESET% %~1
goto :eof

:wait
echo       %YELLOW%[WAIT]%RESET% %~1
goto :eof

:hint
echo       %DIM%%~1%RESET%
goto :eof

:error
echo.
echo       %RED%[PROBLEM]%RESET% %~1
goto :eof

:ready
echo.
echo  %IPA_GREEN%====================================================================%RESET%
echo.
echo      %BOLD%%IPA_GREEN%All set - starting the app now!%RESET%
echo.
echo      %WHITE%Your web browser will open automatically in a moment.%RESET%
echo      %DIM%If it does not, open this address:%RESET% %IPA_GREEN%http://127.0.0.1:8501%RESET%
echo.
echo      %YELLOW%Keep this window open while you use the app.%RESET%
echo      %DIM%When you are finished, close this window to stop the app.%RESET%
echo.
echo  %IPA_GREEN%====================================================================%RESET%
echo.
goto :eof

:bye
echo.
echo    %DIM%Press any key to close this window.%RESET%
pause >nul
goto :eof
