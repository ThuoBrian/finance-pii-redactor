# Finance PII Redactor

A desktop tool that replaces people's names and organization names in Excel and
PDF files with stable ID codes (e.g. `STF-91345`). The same name always gets the
same code, so you can still spot patterns in the data for error-checking and
fraud monitoring — without exposing real identities. Everything runs on your own
computer; no data is uploaded anywhere.

## Install & run

**Windows** — open PowerShell and paste:

```powershell
irm https://raw.githubusercontent.com/ThuoBrian/finance-pii-redactor/main/install.ps1 | iex
```

**macOS / Linux** — open a terminal and paste:

```bash
curl -fsSL https://raw.githubusercontent.com/ThuoBrian/finance-pii-redactor/main/install.sh | bash
```

The installer asks where to put the tool (default: Desktop), downloads it, and
starts it. The first launch sets everything up (~400 MB, a few minutes, needs
internet once); after that it is fast and works offline. Run the same command
again anytime to update.

Already have a copy? Just double-click **`run.bat`** (Windows) or run
**`./run.sh`** (macOS / Linux).

## Sharing it

Send people the one-line command above, or point them to the repo's **Download
ZIP** button. The first run installs everything automatically — nothing else to
set up.

## Using it

Upload an Excel or PDF file, choose what to pseudonymize, review the results,
and download the cleaned copy. Developer and architecture notes are in
**[CLAUDE.md](CLAUDE.md)**; known issues in **[GOTCHA.md](docs/GOTCHA.md)**.

## Handling sensitive data

Approved for **Internal** data only under IPA's data-classification policy — not
for Confidential or Highly Confidential data.

The **name-to-code mapping** (crosswalk) the tool can export is the key that
re-identifies people, so it is itself **Confidential**: store it securely and
never send it alongside the pseudonymized file.
