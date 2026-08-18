# Finance PII Redactor

[![CI](https://github.com/ThuoBrian/finance-pii-redactor/actions/workflows/ci.yml/badge.svg)](https://github.com/ThuoBrian/finance-pii-redactor/actions/workflows/ci.yml)

A desktop tool that replaces people's names and organization names in Excel,
PDF, and Word files with stable ID codes (e.g. `STF-91345`). The same identity always
gets the same code, so patterns in the data still show up for error-checking
and fraud monitoring — without exposing real identities. Everything runs on
your own computer; no data is uploaded anywhere.

## Example

|In your file|After redaction|
|-|-|
|Paid to **Jane Doe**|Paid to **STF-91345**|
|Vendor: **Acme Ltd**|Vendor: **VND-1045**|
|Funder: **Global Aid Partners**|Funder: **FND-7745**|
|Memo: approved by **Jane Doe**|Memo: approved by **STF-91345**|

Every occurrence of the same name gets the same code — in this file and every
future file — so a repeat pattern (e.g. one vendor showing up across many
payments) stays visible in the data without ever showing the name.

## What it does

- Redacts people, organizations, and email addresses in Excel, PDF, and Word files.
- Same identity → same code, every time, across every file you process.
- Codes come from a master list you control (see
  **[data/README.md](data/README.md)**), so IDs stay stable over time.
- Names not on the list still get a consistent, flagged auto-code — nothing
  slips through un-redacted.
- Runs entirely offline on your own computer after first-time setup.

## Quick start

1. On the [GitHub repo page](https://github.com/ThuoBrian/finance-pii-redactor),
   click **Code → Download ZIP**, then unzip it wherever you want the tool to
   live (e.g. your Desktop). (If you have Git, `git clone` works too, and
   makes updating later a `git pull`.)
2. **Windows:** double-click **`run.bat`**. **macOS / Linux:** open a terminal
   in that folder and run **`./run.sh`**.

The first launch installs everything (~400 MB, a few minutes, needs internet
once); after that it works offline.

To update later, download a fresh ZIP over the old folder (or `git pull`).
If you keep your master list locally rather than on a shared drive (see
**[data/README.md](data/README.md)**), copy `data/Names List - Organized.xlsx`
out before replacing the folder and back in afterward — nothing does this for
you automatically.

To share the tool with a colleague, send them the repo link and these two steps.

## How it works

1. The master list, `Names List - Organized.xlsx`, lives in the team's
   shared Box folder — **not** in this repo's local `data/` folder. See
   **[Sharing one master list across a team](data/README.md#sharing-one-master-list-across-a-team)**
   in `data/README.md` for the required, one-time setup that points your
   install at it, and for the file format.
2. Upload an Excel, PDF, or Word file. It's processed entirely on your computer.
3. Choose what to detect (people, organizations, emails) and review the
   results.
4. Download the pseudonymized file.
   - **Excel:** the download already includes the name-to-code mapping as a
     second sheet ("Crosswalk"), so the whole file is Confidential — see
     below.
   - **PDF and Word:** optionally download the crosswalk separately (the
     name-to-code key). Keep it separate from the pseudonymized file and
     secure — see below.

To update the master list, edit it in place in the shared Box folder, save
and close it, then refresh the browser page — every teammate's install picks
up the change automatically.

## Handling sensitive data

Approved for **Internal** data only. Do not use for Confidential or Highly
Confidential data.

The **crosswalk** (name-to-code mapping) is the key that re-identifies
people, so it is itself **Confidential** — how you keep it separate depends
on the file type:

- **Excel:** the crosswalk is embedded as a "Crosswalk" sheet in every
  pseudonymized workbook by default, so the downloaded `.xlsx` file is
  **Confidential as a whole**, not just Internal. Store and share it the way
  you would the crosswalk itself.
- **PDF and Word:** the crosswalk is only ever a separate CSV download. Store
  it securely and never send it alongside the pseudonymized file, which stays
  Internal on its own.

## For developers

This README covers day-to-day use. For the architecture, file structure, and
how the pieces fit together, see **[CLAUDE.md](CLAUDE.md)**. Known issues and
troubleshooting are in **[docs/GOTCHA.md](docs/GOTCHA.md)**; the master list
file format is in **[data/README.md](data/README.md)**.
