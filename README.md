<p align="center">
  <img src="image/data-privacy-ai-dark-nobg.svg"
       alt="A shield enclosing a neural network, over rows of partly redacted data"
       width="640">
</p>

# Finance PII Redactor

[![CI](https://github.com/ThuoBrian/finance-pii-redactor/actions/workflows/ci.yml/badge.svg)](https://github.com/ThuoBrian/finance-pii-redactor/actions/workflows/ci.yml)

This tool takes the real names out of your finance files and puts a short
code in their place, so you can share the file without showing who anyone
is. It handles Excel, PDF, and Word files.

"Jane Doe" becomes `STF-91345`. "Acme Ltd" becomes `VND-1045`. The same name
always gets the same code, in this file and in every file you redact later,
so you can still spot patterns (one vendor showing up across many payments,
for example) when you're checking for errors or reviewing for fraud.

Everything happens on your own computer. Nothing is uploaded anywhere.

*PII means personally identifiable information: names, email addresses, and
anything else that points back to a real person or organization.*

## What it looks like

| In your file                     | After redaction              |
| -------------------------------- | ---------------------------- |
| Paid to **Jane Doe**             | Paid to **STF-91345**        |
| Vendor: **Acme Ltd**             | Vendor: **VND-1045**         |
| Funder: **Global Aid Partners**  | Funder: **FND-7745**         |
| Memo: approved by **Jane Doe**   | Memo: approved by **STF-91345** |

## What gets redacted

Where the codes come from: a spreadsheet called the **master list**, which
your team controls. It says which name gets which code. If a name turns up
that isn't on the list, the tool still gives it a code and marks it so you
can see it wasn't one of yours. Nothing is left showing.
See **[data/README.md](data/README.md)** for what goes in that file.

**Excel and Word files:** the tool finds people, organizations, email
addresses, and website links on its own.

**PDF files:** email addresses, website links, and images or logos are
found automatically. Names and organizations are not, because in a PDF the
tool can't reliably tell a name from any other text and we'd rather it
didn't guess. So for PDFs you type or paste the exact words you want
covered.

## Installing it

You only do this once. Copy the line below, paste it into a terminal
window, and press Enter. It downloads the tool, asks you where you'd like
it saved, and starts it up.

**Windows** (open PowerShell):

```powershell
irm https://raw.githubusercontent.com/ThuoBrian/finance-pii-redactor/main/install.ps1 | iex
```

**macOS / Linux** (open Terminal):

```bash
curl -fsSL https://raw.githubusercontent.com/ThuoBrian/finance-pii-redactor/main/install.sh | bash
```

Setup downloads about 400 MB and takes a few minutes, so you need internet
for this part. After that the tool works offline.

A few things that surprise people the first time:

- The tool opens in your **web browser**, like a website would. It isn't
  online though; it's only running on your machine. If the browser doesn't
  open by itself, go to http://127.0.0.1:8501.
- A black window opens too. **Leave it open** while you're working. Closing
  it stops the tool.

**Opening it again later:** double-click **`run.bat`** (Windows) or run
**`./run.sh`** (macOS/Linux) in the folder you installed into.

**Updating:** paste the same install command again. Your master list is kept
as it is.

If your team shares one master list from a Box folder, there's a one-time
setup for that in **[docs/BOX_SETUP.md](docs/BOX_SETUP.md)**. Installing or
updating never touches that shared folder, so re-running the command above
is always safe.

## Using it

1. Upload your Excel, PDF, or Word file.
2. Choose what you want redacted, then look over what the tool found. If
   there's something specific you want covered that it wouldn't know about,
   like a codename or a case number, type it into **Advanced settings**.
3. Download the redacted copy.

In Excel, every cell the tool changed is highlighted in yellow, so you can
see at a glance what was touched.

Alongside the redacted file you get a **name mapping**: the list of which
name became which code. For Excel it's included in the workbook as a second
sheet named "Crosswalk". For PDF and Word it's a separate CSV you can
download if you want it.

To change which names get which codes, edit the master list
(`Names List - Organized.xlsx`) and click **🔄 Refresh master list** in
**Advanced settings**.

## Which file is safe to share

A redacted file on its own is approved for **Internal** data. Not
Confidential, not Highly Confidential.

The name mapping is a different matter. Anyone holding it can turn the codes
back into real names, so **the mapping is Confidential**, and that changes
what you can do with each file:

- **Excel:** the mapping is always included in the workbook as a second
  sheet, so the file you download is Confidential as a whole, not Internal.
  Delete the "Crosswalk" sheet before sharing if the recipient shouldn't
  have it.
- **PDF and Word:** the mapping is always a separate CSV. Keep it somewhere
  else, stored securely, and don't send it with the redacted file.

## If something goes wrong

**[docs/GOTCHA.md](docs/GOTCHA.md)** lists the problems people run into
most and how to fix them. If it isn't covered there, email the maintainer
below.

## Testing with users

Running a round of testing before rollout?
**[docs/TESTING.md](docs/TESTING.md)** walks testers through it: installing,
building a small made-up master list to practise on (never real names), and
working through Excel, PDF, and Word along with the known rough edges.

## For developers

This README covers day-to-day use. **[CONTRIBUTING.md](CONTRIBUTING.md)**
covers local setup and the checks to run before opening a PR,
**[docs/GOTCHA.md](docs/GOTCHA.md)** covers known issues,
**[data/README.md](data/README.md)** covers the master-list file format, and
**[CHANGELOG.md](CHANGELOG.md)** tracks notable changes. Architecture and
internal file structure live in a local, non-public `CLAUDE.md` kept out of
this repository. Contact the maintainer if you need it for development.

## Maintainer

Brian Thuo, Systems Engineer, bthuo@poverty-action.org

## License

[Apache 2.0](LICENSE)
