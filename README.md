<p align="center">
  <img src="image/data-privacy-ai-dark-nobg.svg"
       alt="A shield enclosing a neural network, over rows of partly redacted data"
       width="640">
</p>

# Finance PII Redactor

[![CI](https://github.com/ThuoBrian/finance-pii-redactor/actions/workflows/ci.yml/badge.svg)](https://github.com/ThuoBrian/finance-pii-redactor/actions/workflows/ci.yml)

This tool takes the real names out of your finance files and puts something
short and meaningless in their place, so you can share the file without
showing who anyone is. It handles Excel, PDF, and Word files.

In Excel and Word that replacement is a code like `STF-10010`. In PDFs it is
a numbered label like `[001]`, with a separate file saying what each label
stands for. The next section shows both, and explains why they differ.

Either way you can still spot patterns, like one vendor showing up across
many payments, without ever seeing who the vendor is. That is the point: the
data stays useful for error-checking and fraud review.

Everything happens on your own computer. Nothing is uploaded anywhere.

*PII means personally identifiable information: names, email addresses, and
anything else that points back to a real person or organization.*

## What it looks like

**Excel and Word** put a stable code straight into the file. The same name
gets the same code in this file and in every file you redact later.

| In your file                    | After redaction                 |
| ------------------------------- | ------------------------------- |
| Paid to **Jane Doe**            | Paid to **STF-10010**           |
| Vendor: **Acme Ltd**            | Vendor: **VND-10011**           |
| Memo: approved by **Jane Doe**  | Memo: approved by **STF-10010** |

**PDF** puts a short numbered label in instead, and tells you separately what
each label stands for.

| In your file                    | After redaction      |
| ------------------------------- | -------------------- |
| Paid to **Jane Doe**            | Paid to **[001]**    |
| Vendor: **Acme Ltd**            | Vendor: **[002]**    |
| Memo: approved by **Jane Doe**  | Memo: approved by **[001]** |

The reason for the difference: a code like `STF-10010` has the master list's
own ID number inside it. Anyone who has the master list can decode a redacted
file on their own, without the mapping. `[001]` means nothing outside the one
PDF it came from, so decoding it takes two separate steps held by two
different people:

```
the PDF        [001]
the mapping    [001]  =  10010
the master list        10010  =  Jane Doe
```

Two consequences worth knowing. **Keep the PDF's mapping file** or the labels
cannot be decoded by anyone, including you. And **labels restart at `[001]` in
every PDF**, so to follow one vendor across several PDFs you join their
mapping files on the ID number, not on the label.

## What gets redacted

Where the codes come from: a spreadsheet called the **master list**, which
your team controls. It says which name gets which code. If a name turns up
that isn't on the list, the tool still gives it a code and marks it so you
can see it wasn't one of yours. Nothing is left showing.
See **[data/README.md](data/README.md)** for what goes in that file.

**Excel and Word files:** the tool finds people, organizations, email
addresses, and website links on its own.

**PDF files:** email addresses, website links, images or logos, and any name
or organization **that is on the master list** are found automatically. What
the tool won't do in a PDF is guess at a name it doesn't already know: the
statistical name-spotting it uses for Excel and Word is unreliable on
scanned financial PDFs, so it's switched off there. For a name that isn't on
the master list yet, either add it to the list or type it into the box for
that one run.

**Bank and payment details, in all three formats:** card numbers, IBANs,
Kenyan bank account numbers, M-Pesa till/paybill numbers, and SWIFT/BIC
codes. They're replaced with a fixed mask such as `[ACCOUNT]` or `[CARD]`,
with nothing to decode and no entry in the crosswalk or mapping file. Card
numbers and IBANs are checked against their checksum. The other three are
only caught when their label is right in front of them ("A/C No:",
"Paybill", "SWIFT"). A bare number could be an invoice number or a staff ID,
so it's left alone, and so is a bare number in an Excel column headed
"Account No". Type it into the words box, or check the column yourself.

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
3. Look over **Check what was detected** and untick anything that isn't
   really a name. Ordinary words sometimes get caught, usually because
   someone added one to the master list as a payee. The **Source** column
   says why it matched. Unticking rebuilds the file without that word and
   leaves everything else redacted.
4. Download the redacted copy.

In Excel, every cell the tool changed is highlighted in yellow, so you can
see at a glance what was touched.

Alongside the redacted file you get a **mapping**: what each code or label
stands for.

- **Excel:** included in the workbook as a second sheet named "Crosswalk". It
  lists the real names.
- **Word:** a separate CSV you can download. It lists the real names.
- **PDF:** a separate CSV that contains **no names at all**, only
  `[001] = 10010` rows. You need the master list as well to get from there to
  a person or organization.

To change which names get which codes, edit the master list
(`Names List - Organized.xlsx`) and click **🔄 Refresh master list** in
**Advanced settings**.

## Which file is safe to share

A redacted file on its own is approved for **Internal** data. Not
Confidential, not Highly Confidential.

The mapping is where it gets more careful, and the three formats differ:

- **PDF:** the mapping has no names in it, so it cannot identify anyone on
  its own. It is **Internal**, and you can keep it with the redacted PDF.
  What has to stay locked down is the master list, which is the only thing
  that turns an ID number back into a name.
- **Word:** the mapping is a separate CSV listing real names, so it is
  **Confidential**. Store it somewhere else, securely, and don't send it with
  the redacted file.
- **Excel:** the mapping is inside the workbook as a second sheet, so the file
  you download is **Confidential as a whole**, not Internal. Delete the
  "Crosswalk" sheet before sharing if the recipient shouldn't have it.

The safest thing to hand someone is therefore a redacted PDF, with or without
its mapping. A redacted Excel workbook needs a look at the Crosswalk sheet
first.

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
