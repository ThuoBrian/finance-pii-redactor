# package.ps1 - create a clean, shareable zip of the Finance PII Redactor.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File package.ps1
#   (or just double-click package.bat)
#
# Output:
#   ..\finance-pii-redactor.zip
#
# Produces a lightweight SOURCE zip (no .venv, no model). The recipient extracts
# it and runs run.bat; their first run builds the environment and downloads the
# spaCy model (needs internet once).

$ErrorActionPreference = "Stop"

$AppDir     = $PSScriptRoot
$AppName    = Split-Path $AppDir -Leaf          # finance-pii-redactor
$ParentDir  = Split-Path $AppDir -Parent
$OutputName = "finance-pii-redactor.zip"
$OutputPath = Join-Path $ParentDir $OutputName

# Staging folder in TEMP: <temp>\fpr-package\<AppName>
$StageRoot = Join-Path $env:TEMP "fpr-package"
$StageDir  = Join-Path $StageRoot $AppName

Write-Host "Packaging Finance PII Redactor for sharing..."

# Remove any previous package and stale staging folder.
if (Test-Path $OutputPath) {
    Write-Host "Removing existing $OutputName..."
    Remove-Item $OutputPath -Force
}
if (Test-Path $StageRoot) {
    Remove-Item $StageRoot -Recurse -Force
}

# Stage the project, excluding runtime/cache artifacts (mirrors package.sh).
# robocopy uses exit codes 0-7 for success; only >= 8 is a real failure.
Write-Host "Collecting files..."
$excludeDirs  = @(".venv", "__pycache__", ".ruff_cache", ".claude", ".git", "_legacy")
$excludeFiles = @("*.pyc", ".DS_Store", "*.zip")
robocopy $AppDir $StageDir /E /NFL /NDL /NJH /NJS /NP /XD $excludeDirs /XF $excludeFiles | Out-Null
if ($LASTEXITCODE -ge 8) {
    Remove-Item $StageRoot -Recurse -Force -ErrorAction SilentlyContinue
    throw "Failed to collect files (robocopy exit code $LASTEXITCODE)."
}

# Build the zip from the staged folder, so it contains a top-level
# finance-pii-redactor\ directory (matches package.sh layout).
Write-Host "Creating archive..."
Compress-Archive -Path $StageDir -DestinationPath $OutputPath -CompressionLevel Optimal

# Clean up the staging folder.
Remove-Item $StageRoot -Recurse -Force

$sizeMB = [math]::Round((Get-Item $OutputPath).Length / 1MB, 1)

Write-Host ""
Write-Host "Created: $OutputPath ($sizeMB MB)"
Write-Host ""
Write-Host "Excluded: .venv, __pycache__, .ruff_cache, .claude, .git, _legacy, *.pyc, .DS_Store"
Write-Host "Recipient should extract the zip and run run.bat (Windows) or ./run.sh (macOS/Linux)."
