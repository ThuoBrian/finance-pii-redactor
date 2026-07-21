# Finance PII Redactor

A desktop tool that replaces people's names and organization names in Excel and
PDF files with stable ID codes (e.g. `STF-91345`). The same name always gets the
same code, so you can still spot patterns in the data for error-checking and
fraud monitoring — without exposing real identities. Everything runs on your
own computer; no data is uploaded anywhere.

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

The installer asks where to put the tool (default: Desktop), downloads it, and
starts it. The first launch installs everything (~400 MB, a few minutes, needs
internet once); after that it is fast and works offline. Run the same command
again anytime to update.

Already have a copy? Just double-click **`run.bat`** (Windows) or run
**`./run.sh`** (macOS / Linux).

## How it works

1. **Load the master list.** Put your `Names List - Organized.xlsx` in the
   `data/` folder. It should have three sheets:
   - `Staff` — people names → IDs like `STF-<Internal ID>`
   - `Vendors` — vendor names → IDs like `VND-<Internal ID>`
   - `Funders` — funder names → IDs like `FND-<Internal ID>`

   Required columns per sheet: `Category`, `Internal ID`, `Name`.

2. **Upload a file.** Choose an Excel or PDF file from your computer. The file
   is processed entirely on your machine.

3. **Choose what to redact.** Pick the entity types to detect (people,
   organizations, emails) and a confidence threshold. Lower thresholds catch
   more names but may add false positives.

4. **Review and download.** The app shows a side-by-side preview for Excel files
   and a summary of detected names for PDFs. Download the pseudonymized file.

5. **Optional: download the crosswalk.** This is the name-to-code mapping. It is
   the **re-identification key** — keep it separate and secure.

## Sharing the tool with your team

Send people the one-line command for their operating system, or point them to
the repo's **Download ZIP** button. The first run installs everything
automatically.

If you want to pre-load the master list for your team, give them a copy of your
`data/Names List - Organized.xlsx` to place in the `data/` folder after
installation. The master list is not included in the repo because it contains
real names.

## Updating the master list

- Edit `data/Names List - Organized.xlsx` in Excel.
- **Save and close the workbook.** The app cannot read it while Excel has it
  open.
- Refresh the browser page. The app reloads the master list automatically.

If a name appears in more than one sheet, the app warns you in the **Advanced
settings** panel. Keep each name in a single category to avoid conflicting IDs.

## Handling sensitive data

Approved for **Internal** data only. Do not use for Confidential or Highly
Confidential data.

The **name-to-code mapping** (crosswalk) the tool can export is the key that
re-identifies people, so it is itself **Confidential**: store it securely and
never send it alongside the pseudonymized file.

## Developer notes

- Architecture and contribution guidance: **[CLAUDE.md](CLAUDE.md)**
- Known issues and troubleshooting: **[docs/GOTCHA.md](docs/GOTCHA.md)**
- Master list format details: **[data/README.md](data/README.md)**

## Limitations

- The tool only processes selectable PDF text. Scanned/image PDFs need OCR
  first.
- The built-in language model is English-only. Non-English names should be added
  to the master list.
- All-caps names are handled by a recasing pass, but standalone acronyms may
  occasionally be flagged as organizations.
