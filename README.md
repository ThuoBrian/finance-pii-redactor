# Finance PII Redactor

[![CI](https://github.com/ThuoBrian/finance-pii-redactor/actions/workflows/ci.yml/badge.svg)](https://github.com/ThuoBrian/finance-pii-redactor/actions/workflows/ci.yml)

A desktop tool that replaces people's and organizations' names in Excel,
PDF, and Word files with stable ID codes (e.g. `STF-91345`) — so patterns in
the data (like one vendor across many payments) stay visible for
error-checking and fraud monitoring, without ever exposing a real identity.
Runs entirely on your own computer; nothing is uploaded anywhere.

## Example

|In your file|After redaction|
|-|-|
|Paid to **Jane Doe**|Paid to **STF-91345**|
|Vendor: **Acme Ltd**|Vendor: **VND-1045**|
|Funder: **Global Aid Partners**|Funder: **FND-7745**|
|Memo: approved by **Jane Doe**|Memo: approved by **STF-91345**|

The same name always gets the same code — in this file and every future
one — so a repeat pattern stays visible without ever showing the name.

## What it does

- **Excel and Word:** automatically redacts people, organizations, emails,
  and websites, using codes from a master list you control (see
  **[data/README.md](data/README.md)**). Anyone not on the list still gets
  a consistent, flagged code — nothing slips through un-redacted.
- **PDF:** emails, websites, and images/logos are redacted automatically;
  names and organizations aren't guessed at, so type or paste the exact
  words/phrases you want covered instead.
- Same identity → same code, every time, across every file.
- Works offline after first-time setup.

## Quick start

**Windows** — open PowerShell and paste:

```powershell
irm https://raw.githubusercontent.com/ThuoBrian/finance-pii-redactor/main/install.ps1 | iex
```

**macOS / Linux** — open a terminal and paste:

```bash
curl -fsSL https://raw.githubusercontent.com/ThuoBrian/finance-pii-redactor/main/install.sh | bash
```

The installer asks where to install, sets everything up (~400 MB, a few
minutes, needs internet once), and launches the app — after that it works
offline. Run the same command again anytime to update; it preserves your
local master list automatically.

Already installed? Double-click **`run.bat`** (Windows) or run
**`./run.sh`** (macOS/Linux). If your team keeps the master list in a shared
Box folder, see
**[data/README.md](data/README.md#sharing-one-master-list-across-a-team)**
for the one-time setup — the installer above doesn't touch that shared
folder either way, so it's safe to re-run anytime.

## How it works

1. Upload an Excel, PDF, or Word file — it's processed entirely on your
   computer.
2. **Excel and Word:** choose what to detect and review the results.
   **PDF:** emails, websites, and images are caught automatically either
   way. You can also type/paste extra words or phrases into **Advanced
   settings** for anything one-off (a codename, a case number).
3. Download the redacted file. Excel embeds the name-to-code mapping
   (**crosswalk**) as a second sheet; PDF and Word offer it as a separate,
   optional download instead.

The master list (`Names List - Organized.xlsx`) controls which names get
which codes — see **[data/README.md](data/README.md)** for the file format
and how to point the app at a shared copy. To update it, edit it in place
and click **🔄 Refresh master list** in **Advanced settings**.

## Handling sensitive data

Approved for **Internal** data only — not Confidential or Highly
Confidential.

The **crosswalk** (name-to-code mapping) re-identifies people, so it's
**Confidential** on its own, even though the redacted file itself stays
Internal:

- **Excel:** the crosswalk is embedded in the workbook by default, so the
  whole downloaded file is Confidential, not just Internal.
- **PDF and Word:** the crosswalk is only ever a separate CSV — keep it
  apart from the redacted file and store it securely.

## For developers

This README covers day-to-day use. See **[CLAUDE.md](CLAUDE.md)** for
architecture and file structure, **[docs/GOTCHA.md](docs/GOTCHA.md)** for
known issues and troubleshooting, and **[data/README.md](data/README.md)**
for the master-list file format.

## License

[MIT](LICENSE)
