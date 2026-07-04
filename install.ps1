# install.ps1 - one-line installer for the Finance PII Redactor.
#
# Users paste this into a PowerShell window (nothing else required):
#
#   irm https://raw.githubusercontent.com/ThuoBrian/finance-pii-redactor/main/install.ps1 | iex
#
# It downloads the latest version, extracts it to your user folder, and starts
# the app. The first launch sets up the environment (a few minutes, once).
# To install somewhere else, set $env:FPR_INSTALL_DIR before running.

$ErrorActionPreference = 'Stop'

$Repo    = 'ThuoBrian/finance-pii-redactor'
$Branch  = 'main'
$AppName = 'finance-pii-redactor'
$DataRel = 'finance_redactor\infrastructure\names\data\master_list.csv'

$InstallRoot = if ($env:FPR_INSTALL_DIR) { $env:FPR_INSTALL_DIR } else { $env:USERPROFILE }
$Target      = Join-Path $InstallRoot $AppName

$green = @{ ForegroundColor = 'Green' }
$cyan  = @{ ForegroundColor = 'Cyan' }

Write-Host ""
Write-Host "Finance PII Redactor - installer" @green
Write-Host "Installing to: $Target"
Write-Host ""

# 1. Download the current source as a zip (works for a public repo, no login).
$zipUrl     = "https://github.com/$Repo/archive/refs/heads/$Branch.zip"
$tmpZip     = Join-Path $env:TEMP "$AppName-$Branch.zip"
$tmpExtract = Join-Path $env:TEMP "$AppName-extract"

Write-Host "Downloading the latest version..." @cyan
Invoke-WebRequest -Uri $zipUrl -OutFile $tmpZip -UseBasicParsing

# 2. Extract (the zip contains a single top-level <repo>-<branch> folder).
if (Test-Path $tmpExtract) { Remove-Item $tmpExtract -Recurse -Force }
Expand-Archive -Path $tmpZip -DestinationPath $tmpExtract -Force
$extracted = Get-ChildItem $tmpExtract -Directory | Select-Object -First 1

# 3. Preserve a local master list (it is intentionally not shipped in the repo).
$savedMaster = $null
$existingMaster = Join-Path $Target $DataRel
if (Test-Path $existingMaster) {
    Write-Host "Preserving your existing master_list.csv..." @cyan
    $savedMaster = Join-Path $env:TEMP 'master_list.csv.bak'
    Copy-Item $existingMaster $savedMaster -Force
}

# 4. Put the new version in place (step out of the folder before replacing it).
Set-Location $InstallRoot
if (Test-Path $Target) { Remove-Item $Target -Recurse -Force }
Move-Item $extracted.FullName $Target
if ($savedMaster) {
    Copy-Item $savedMaster (Join-Path $Target $DataRel) -Force
    Remove-Item $savedMaster -Force -ErrorAction SilentlyContinue
}

# 5. Tidy up temp files.
Remove-Item $tmpZip -Force -ErrorAction SilentlyContinue
Remove-Item $tmpExtract -Recurse -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Done. Starting the app (first run sets up the environment)..." @green
Write-Host ""

# 6. Launch. run.bat resolves its own location, so cwd does not matter.
Set-Location $Target
& (Join-Path $Target 'run.bat')
