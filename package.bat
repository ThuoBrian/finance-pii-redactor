@echo off
:: package.bat - double-click to build a shareable zip of the Finance PII Redactor.
:: Runs package.ps1 (built-in PowerShell) and keeps the window open to show the result.
powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0package.ps1"
echo.
pause
