# install.ps1 - one-line installer for the Finance PII Redactor.
#
# Users paste this into a PowerShell window (nothing else required):
#
#   irm https://raw.githubusercontent.com/ThuoBrian/finance-pii-redactor/main/install.ps1 | iex
#
# It asks where to install, downloads the latest version there, adds a
# "Finance PII Redactor" shortcut to the Desktop and Start menu, and starts the
# app. The first launch sets up the environment (a few minutes, once).
# To skip the prompt, set $env:FPR_INSTALL_DIR before running.
#
# Master list note: this script only preserves a master list kept locally at
# <install>\data\Names List - Organized.xlsx. If your team instead points
# installs at a shared Box folder via $env:FPR_MASTER_LIST_DIR (see
# data/README.md), that setup lives entirely outside this script's install
# folder, so it is untouched by install/update either way - but this script
# also does NOT set FPR_MASTER_LIST_DIR up for you on a first run. A
# brand-new machine still needs that one-time env-var setup done separately.

$ErrorActionPreference = 'Stop'

$Repo    = 'ThuoBrian/finance-pii-redactor'
$Branch  = 'main'
$AppName = 'finance-pii-redactor'
$DataRel = 'data\Names List - Organized.xlsx'

$green = @{ ForegroundColor = 'Green' }
$cyan  = @{ ForegroundColor = 'Cyan' }

function Get-InstallRoot {
    # Ask which parent folder to install into; the app folder is created inside it.
    # An explicit override wins and skips the prompt (scriptable / non-interactive).
    if ($env:FPR_INSTALL_DIR) { return $env:FPR_INSTALL_DIR }

    $desktop = [Environment]::GetFolderPath('Desktop')

    # Preferred: a graphical "Browse For Folder" dialog.
    try {
        Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
        $dlg = New-Object System.Windows.Forms.FolderBrowserDialog
        $dlg.Description = "Choose where to install Finance PII Redactor (a 'finance-pii-redactor' folder will be created inside)."
        $dlg.ShowNewFolderButton = $true
        try { $dlg.SelectedPath = $desktop } catch { }
        # Owned by a TopMost form so the dialog appears in front of the console.
        $owner  = New-Object System.Windows.Forms.Form -Property @{ TopMost = $true }
        $result = $dlg.ShowDialog($owner)
        $owner.Dispose()
        if ($result -eq [System.Windows.Forms.DialogResult]::OK -and $dlg.SelectedPath) {
            return $dlg.SelectedPath
        }
        Write-Host "No folder chosen - installing to the Desktop." @cyan
        return $desktop
    }
    catch {
        # Fallback for hosts without a usable WinForms dialog (e.g. PowerShell 7
        # running MTA, or a headless session): a simple numbered menu.
        Write-Host ""
        Write-Host "Where should Finance PII Redactor be installed?"
        Write-Host "  [1] Desktop (default)"
        Write-Host "  [2] Documents"
        Write-Host "  [3] Home folder"
        Write-Host "  [4] Type a path"
        switch (Read-Host "Enter 1-4 (or press Enter for Desktop)") {
            '2' { return [Environment]::GetFolderPath('MyDocuments') }
            '3' { return [Environment]::GetFolderPath('UserProfile') }
            '4' {
                $p = Read-Host "Full path to the folder to install into"
                if ([string]::IsNullOrWhiteSpace($p)) { return $desktop } else { return $p }
            }
            default { return $desktop }
        }
    }
}

Write-Host ""
Write-Host "Finance PII Redactor - installer" @green

$InstallRoot = Get-InstallRoot
$Target      = Join-Path $InstallRoot $AppName

Write-Host "Installing to: $Target" @green
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
    Write-Host "Preserving your existing master list..." @cyan
    $savedMaster = Join-Path $env:TEMP 'Names List - Organized.xlsx.bak'
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

# 6. Desktop and Start Menu shortcuts, so reopening the app is a double-click
#    instead of finding run.bat. Re-running the installer (the update path)
#    overwrites them, so they always point at this install. Some managed
#    machines block this; the app still works from run.bat.
try {
    $shell = New-Object -ComObject WScript.Shell
    $startMenu = Join-Path ([Environment]::GetFolderPath('Programs')) 'Finance PII Redactor.lnk'
    $onDesktop = Join-Path ([Environment]::GetFolderPath('Desktop')) 'Finance PII Redactor.lnk'
    foreach ($path in @($onDesktop, $startMenu)) {
        $link = $shell.CreateShortcut($path)
        $link.TargetPath       = Join-Path $Target 'run.bat'
        $link.WorkingDirectory = $Target
        $link.Description      = 'Redact names from Excel, PDF and Word files (runs locally)'
        # A padlock from Windows' own icon set; no icon file to ship.
        $link.IconLocation     = "$env:SystemRoot\System32\shell32.dll,47"
        $link.Save()
    }
    Write-Host "Added a 'Finance PII Redactor' shortcut to your Desktop and Start menu." @green
}
catch {
    Write-Host "Could not add shortcuts. Open the app later with run.bat in $Target." @cyan
}

Write-Host ""
Write-Host "Done. Starting the app (first run sets up the environment)..." @green
Write-Host ""

# 7. Launch. run.bat resolves its own location, so cwd does not matter.
Set-Location $Target
& (Join-Path $Target 'run.bat')
