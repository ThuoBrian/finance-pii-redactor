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
call :stepnum 1 3 "Checking the setup helper"
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

call :stepnum 2 3 "Preparing the program"
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

:: -- 3. Choose where the master list lives -------------------------------------
call :stepnum 3 3 "Choosing your master list location"
set "MASTERCONFIGURED="
for /f "tokens=*" %%i in ('powershell -Command "[Environment]::GetEnvironmentVariable(\"FPR_MASTER_LIST_CONFIGURED\",\"User\")"') do set "MASTERCONFIGURED=%%i"
if defined MASTERCONFIGURED (
    set "SAVEDMASTERDIR="
    for /f "tokens=*" %%i in ('powershell -Command "[Environment]::GetEnvironmentVariable(\"FPR_MASTER_LIST_DIR\",\"User\")"') do set "SAVEDMASTERDIR=%%i"
    if defined SAVEDMASTERDIR set "FPR_MASTER_LIST_DIR=!SAVEDMASTERDIR!"
    call :ok "Master list location already set. Run reconfigure_master_list.bat to change it."
) else (
    echo.
    echo    Where is your master list?
    echo       1. On this computer only - the default
    echo       2. Shared with my team - I will pick the folder
    echo.
    set "MASTERCHOICE="
    set /p MASTERCHOICE="   Enter 1 or 2 and press Enter - default 1: "
    if "!MASTERCHOICE!"=="2" (
        call :wait "Opening the folder picker window - if you do not see it, check your taskbar."
        set "MASTERPICK="
        for /f "tokens=*" %%i in ('powershell -ExecutionPolicy Bypass -Command "Add-Type -AssemblyName System.Windows.Forms; $d = New-Object System.Windows.Forms.FolderBrowserDialog; if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { Write-Output $d.SelectedPath }"') do set "MASTERPICK=%%i"
        if defined MASTERPICK (
            set "FPR_MASTER_LIST_DIR=!MASTERPICK!"
            powershell -Command "[Environment]::SetEnvironmentVariable(\"FPR_MASTER_LIST_DIR\",\"!MASTERPICK!\",\"User\")" >nul
            if exist "!MASTERPICK!\Names List - Organized.xlsx" (
                call :ok "Using the shared master list: !MASTERPICK!"
            ) else (
                call :info "Folder set, but Names List - Organized.xlsx was not found there yet."
                call :hint "The app will use it as soon as the file is added to that folder."
            )
        ) else (
            set "FPR_MASTER_LIST_DIR="
            powershell -Command "[Environment]::SetEnvironmentVariable(\"FPR_MASTER_LIST_DIR\",$null,\"User\")" >nul
            call :info "No folder selected - using the master list on this computer instead."
        )
    ) else (
        set "FPR_MASTER_LIST_DIR="
        powershell -Command "[Environment]::SetEnvironmentVariable(\"FPR_MASTER_LIST_DIR\",$null,\"User\")" >nul
        call :ok "Using the master list on this computer."
    )
    powershell -Command "[Environment]::SetEnvironmentVariable(\"FPR_MASTER_LIST_CONFIGURED\",\"1\",\"User\")" >nul
)

:: -- 4. Launch the app --------------------------------------------------------
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
