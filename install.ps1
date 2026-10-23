# install.ps1 - one-line installer for the Finance PII Redactor.
#
# Users paste this into a PowerShell window (nothing else required):
#
#   irm https://raw.githubusercontent.com/ThuoBrian/finance-pii-redactor/main/install.ps1 | iex
#
# It asks where to install, downloads the latest version there, adds a
# "Finance PII Redactor" shortcut to the Desktop and Start menu, and starts the
# app. The first launch sets up the environment (a few minutes, once).
# Running it again updates an existing install: it asks first, keeps the old
# copy until the new one is in place, and never replaces a folder that is not
# an install. To skip the prompts, set $env:FPR_INSTALL_DIR before running.
#
# Master list note: this script only preserves a master list kept locally at
# <install>\data\Names List - Organized.xlsx. If your team instead points
# installs at a shared Box folder via $env:FPR_MASTER_LIST_DIR (see
# data/README.md), that setup lives entirely outside this script's install
# folder, so it is untouched by install/update either way - but this script
# also does NOT set FPR_MASTER_LIST_DIR up for you on a first run. A
# brand-new machine still needs that one-time env-var setup done separately.
#
# Keep this file pure ASCII (see docs/troubleshooting.md). It runs under
# `irm | iex` in the user's own window, so it must never call `exit`.

& {
$ErrorActionPreference = 'Stop'

$Repo     = 'ThuoBrian/finance-pii-redactor'
$Branch   = 'main'
$AppName  = 'finance-pii-redactor'
$DataRel  = 'data\Names List - Organized.xlsx'
$OneLiner = "irm https://raw.githubusercontent.com/$Repo/$Branch/install.ps1 | iex"

# -- Colours & styling --------------------------------------------------------
# 24-bit escapes where the console supports them, plain console colours if not.
$e  = [char]27
$vt = $false
try { $vt = [bool]$Host.UI.SupportsVirtualTerminal } catch { }
$palette = @{
    # IPA brand colour (primary green #49ac57)
    Green  = @("$e[38;2;73;172;87m", 'Green')
    Bold   = @("$e[1;37m", 'White')
    Dim    = @("$e[2m", 'DarkGray')
    Yellow = @("$e[1;33m", 'Yellow')
    Red    = @("$e[1;31m", 'Red')
}

function Write-Part([string]$Text, [string]$Color, [switch]$NoNewline) {
    $code, $fallback = $palette[$Color]
    if ($vt) { Write-Host "$code$Text$e[0m" -NoNewline:$NoNewline }
    else { Write-Host $Text -ForegroundColor $fallback -NoNewline:$NoNewline }
}

function Write-Rule { Write-Part (' ' + '=' * 68) Green }

function Write-Step($Number, $Total, $Title) {
    Write-Host ''
    Write-Part "   [ Step $Number of $Total ] " Green -NoNewline
    Write-Part $Title Bold
}

function Write-Ok($Message)   { Write-Part '      [OK] ' Green -NoNewline; Write-Host $Message }
function Write-Info($Message) { Write-Part '      [INFO] ' Dim -NoNewline; Write-Host $Message }
function Write-Warn($Message) { Write-Part '      [NOTE] ' Yellow -NoNewline; Write-Host $Message }
function Write-Hint($Message) { Write-Part "      $Message" Dim }

function Write-Problem($Message) {
    Write-Host ''
    Write-Part '      [PROBLEM] ' Red -NoNewline
    Write-Host $Message
}

function Read-YesNo($Question) {
    # Enter means yes. A host that cannot prompt counts as yes too, so a
    # scripted run never hangs here.
    try { $answer = Read-Host $Question } catch { return $true }
    return ("$answer".Trim() -match '^(y|yes)?$')
}

function Test-IsInstall($Path) {
    (Test-Path (Join-Path $Path 'app.py')) -and (Test-Path (Join-Path $Path 'pyproject.toml'))
}

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
        Write-Info 'Pick a folder in the window that just opened.'
        # Owned by a TopMost form so the dialog appears in front of the console.
        $owner  = New-Object System.Windows.Forms.Form -Property @{ TopMost = $true }
        $result = $dlg.ShowDialog($owner)
        $owner.Dispose()
        if ($result -eq [System.Windows.Forms.DialogResult]::OK -and $dlg.SelectedPath) {
            return $dlg.SelectedPath
        }
        Write-Info 'No folder chosen - installing to the Desktop.'
        return $desktop
    }
    catch {
        # Fallback for hosts without a usable WinForms dialog (e.g. PowerShell 7
        # running MTA, or a headless session): a simple numbered menu.
        Write-Host ''
        Write-Host '      Where should Finance PII Redactor be installed?'
        Write-Host '        [1] Desktop (default)'
        Write-Host '        [2] Documents'
        Write-Host '        [3] Home folder'
        Write-Host '        [4] Type a path'
        switch (Read-Host '      Enter 1-4 (or press Enter for Desktop)') {
            '2' { return [Environment]::GetFolderPath('MyDocuments') }
            '3' { return [Environment]::GetFolderPath('UserProfile') }
            '4' {
                $p = Read-Host '      Full path to the folder to install into'
                if ([string]::IsNullOrWhiteSpace($p)) { return $desktop } else { return $p }
            }
            default { return $desktop }
        }
    }
}

# -- Banner -------------------------------------------------------------------
try { $Host.UI.RawUI.WindowTitle = 'Finance PII Redactor - Installer' } catch { }
Write-Host ''
Write-Rule
Write-Host ''
Write-Part '     FINANCE PII REDACTOR  -  INSTALLER' Bold
Write-Part '     Removes names and organizations from your Excel, PDF and Word files.' Dim
Write-Part '     Runs 100% on your computer - nothing is ever uploaded.' Green
Write-Host ''
Write-Rule

$tmp    = Join-Path $env:TEMP "fpr-install-$([guid]::NewGuid().ToString('N'))"
$Target = $null
$backup = $null
$ready  = $false

try {
    # -- 1. Choose a folder ---------------------------------------------------
    Write-Step 1 4 'Choosing where to install'
    $InstallRoot = Get-InstallRoot
    $Target      = Join-Path $InstallRoot $AppName
    $isUpdate    = Test-Path $Target

    if ($isUpdate) {
        if (-not (Test-IsInstall $Target)) {
            Write-Problem "$Target already exists, but it is not a Finance PII Redactor install."
            Write-Hint 'Nothing was changed. Run the installer again and choose a different folder.'
            return
        }
        Write-Info "Found an existing install at $Target"
        Write-Info 'Updating replaces the program files. Your master list is kept.'
        if (-not $env:FPR_INSTALL_DIR -and -not (Read-YesNo '      Update it? [Y/n]')) {
            Write-Hint 'Cancelled. Nothing was changed.'
            return
        }
    }
    Write-Ok "Installing to $Target"

    # -- 2. Download ----------------------------------------------------------
    Write-Step 2 4 'Downloading the latest version'
    New-Item -ItemType Directory -Path $tmp -Force | Out-Null
    $zip = Join-Path $tmp 'src.zip'
    # Windows PowerShell 5.1 can default to TLS 1.0; GitHub needs 1.2.
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    # The progress bar makes Invoke-WebRequest many times slower on 5.1.
    $ProgressPreference = 'SilentlyContinue'
    Invoke-WebRequest -Uri "https://github.com/$Repo/archive/refs/heads/$Branch.zip" -OutFile $zip -UseBasicParsing
    Write-Ok ('Downloaded {0:N1} MB.' -f ((Get-Item $zip).Length / 1MB))

    # The zip contains a single top-level <repo>-<branch> folder.
    Expand-Archive -Path $zip -DestinationPath (Join-Path $tmp 'src') -Force
    $extracted = Get-ChildItem (Join-Path $tmp 'src') -Directory | Select-Object -First 1
    Write-Ok 'Unpacked.'

    # -- 3. Install -----------------------------------------------------------
    Write-Step 3 4 'Putting the program in place'

    # The master list is intentionally not shipped in the repo, so carry it over.
    $savedMaster = $null
    $existingMaster = Join-Path $Target $DataRel
    if (Test-Path $existingMaster) {
        $savedMaster = Join-Path $tmp 'master-list.xlsx'
        Copy-Item $existingMaster $savedMaster -Force
        Write-Ok 'Saved a copy of your master list.'
    }

    New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
    # Step out of the install folder so it can be moved.
    Set-Location $InstallRoot

    # Move the old version aside rather than deleting it, so a failure below
    # can put it back. A running app locks its files and makes this fail
    # before anything has changed.
    if ($isUpdate) {
        $backup = "$Target.old-$(Get-Date -Format yyyyMMddHHmmss)"
        try { Rename-Item $Target (Split-Path $backup -Leaf) }
        catch {
            $backup = $null
            throw "Could not move the old version aside ($($_.Exception.Message)). If the app is open, close its window and try again."
        }
    }

    Move-Item $extracted.FullName $Target
    if ($savedMaster) {
        $masterPath = Join-Path $Target $DataRel
        New-Item -ItemType Directory -Path (Split-Path $masterPath) -Force | Out-Null
        Copy-Item $savedMaster $masterPath -Force
        Write-Ok 'Restored your master list.'
    }
    if ($backup) {
        try { Remove-Item $backup -Recurse -Force; Write-Ok 'Removed the old version.' }
        catch { Write-Warn "Could not fully remove the old version. You can delete $backup yourself." }
        $backup = $null
    }
    Write-Ok 'Program files are in place.'

    # -- 4. Shortcuts ---------------------------------------------------------
    # Desktop and Start Menu shortcuts, so reopening the app is a double-click
    # instead of finding run.bat. Re-running the installer (the update path)
    # overwrites them, so they always point at this install. Some managed
    # machines block this; the app still works from run.bat.
    Write-Step 4 4 'Adding shortcuts'
    $reopen = "double-click run.bat in $Target"
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
        # CreateShortcut/Save can silently no-op on some managed/locked-down
        # machines instead of throwing, so confirm the files actually landed.
        $missing = @($onDesktop, $startMenu) | Where-Object { -not (Test-Path $_) }
        if ($missing) {
            Write-Warn "Shortcut creation did not report an error, but this is missing: $($missing -join ', ')"
        }
        else {
            Write-Ok "Added 'Finance PII Redactor' to your Desktop and Start menu."
            $reopen = "double-click 'Finance PII Redactor' on your Desktop or Start menu"
        }
    }
    catch {
        Write-Warn "Could not add shortcuts ($($_.Exception.Message))."
    }

    $ready = $true
}
catch {
    $err = $_
    Write-Problem $err.Exception.Message
    if ($backup -and (Test-Path $backup)) {
        if ($Target -and (Test-Path $Target)) { Remove-Item $Target -Recurse -Force -ErrorAction SilentlyContinue }
        try { Rename-Item $backup $AppName; Write-Info 'Your previous version was put back.' }
        catch { Write-Warn "Your previous version is saved at $backup" }
    }
    Write-Hint 'Fix the problem above (often the internet connection), then paste the install line again:'
    Write-Hint "  $OneLiner"
}
finally {
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
}

if (-not $ready) { return }

# -- Summary & launch ---------------------------------------------------------
$verb = if ($isUpdate) { 'Updated' } else { 'Installed' }
Write-Host ''
Write-Rule
Write-Host ''
Write-Part "     $verb - ready to go!" Green
Write-Host ''
Write-Part '     Installed in:  ' Dim -NoNewline; Write-Host $Target
Write-Part '     Open it later: ' Dim -NoNewline; Write-Host $reopen
Write-Part '     Update later:  ' Dim -NoNewline; Write-Host 'paste the same line into PowerShell again:'
Write-Host "                    $OneLiner"
Write-Host ''
Write-Part '     The first start sets up the program. That takes a few minutes, once.' Yellow
Write-Host ''
Write-Rule
Write-Host ''

# The launcher clears the window, so let the summary be read first.
if (-not $env:FPR_INSTALL_DIR) {
    try { [void](Read-Host '     Press Enter to start the app') } catch { }
}

# run.bat resolves its own location, so cwd does not matter.
Set-Location $Target
& (Join-Path $Target 'run.bat')
}
