# Finance PII Redactor

[![CI](https://github.com/ThuoBrian/finance-pii-redactor/actions/workflows/ci.yml/badge.svg)](https://github.com/ThuoBrian/finance-pii-redactor/actions/workflows/ci.yml)

A desktop tool that replaces people's names and organization names in Excel and
PDF files with stable ID codes (e.g. `STF-91345`). The same name always gets the
same code, so patterns in the data still show up for error-checking and fraud
monitoring — without exposing real identities. Everything runs on your own
computer; no data is uploaded anywhere.

## Quick start

### Windows

Open PowerShell and paste:

```powershell
irm https://raw.githubusercontent.com/ThuoBrian/finance-pii-redactor/main/install.ps1 | iex
```

### macOS / Linux

Open a terminal and paste:

```bash
curl -fsSL https://raw.githubusercontent.com/ThuoBrian/finance-pii-redactor/main/install.sh | bash
```

The installer asks where to put the tool, downloads it, and starts it. The
first launch installs everything (~400 MB, a few minutes, needs internet once);
after that it works offline. Run the same command again anytime to update.

Already have a copy? Just double-click **`run.bat`** (Windows) or run
**`./run.sh`** (macOS / Linux).

To share the tool with a colleague, send them the command above for their
operating system — the first run sets everything up automatically.

## How it works

1. Put your master list (`Names List - Organized.xlsx`) in the `data/` folder.
   See **[data/README.md](data/README.md)** for the file format.
2. Upload an Excel or PDF file. It's processed entirely on your computer.
3. Choose what to detect (people, organizations, emails) and review the
   results.
4. Download the pseudonymized file.
5. Optional: download the crosswalk (the name-to-code key). Keep it separate
   and secure — see below.

To update the master list, edit `data/Names List - Organized.xlsx`, save and
close it, then refresh the browser page.

## Handling sensitive data

Approved for **Internal** data only. Do not use for Confidential or Highly
Confidential data.

The **crosswalk** (name-to-code mapping) the tool can export is the key that
re-identifies people, so it is itself **Confidential**: store it securely and
never send it alongside the pseudonymized file.

## For developers

This README covers day-to-day use. For the architecture, file structure, and
how the pieces fit together, see **[CLAUDE.md](CLAUDE.md)**. Known issues and
troubleshooting are in **[docs/GOTCHA.md](docs/GOTCHA.md)**; the master list
file format is in **[data/README.md](data/README.md)**.
