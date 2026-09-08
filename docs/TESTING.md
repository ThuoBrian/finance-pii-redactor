# User testing script

A checklist for testers to work through before a release goes to everyone.
Pairs with **[README.md](../README.md)** (how the tool works) and
**[docs/GOTCHA.md](GOTCHA.md)** (known issues) — this file turns known edge
cases into things to actually click through and confirm.

## Before you start

- **Use synthetic test data only** — made-up names/vendors/funders, not real
  staff, vendor, or funder records. This round is about the tool's behavior,
  not a review of real Confidential data, and the fewer real identities
  involved the easier it is to share results/screenshots with the team.
- Each tester installs their own local copy (do **not** point at the shared
  Box master list for this round — see [Test data](#test-data) below).
- Have a way to report issues open before you begin: [open a GitHub
  issue](https://github.com/ThuoBrian/finance-pii-redactor/issues/new) or
  reply to whoever sent you this link.

## Install

**Windows** — open PowerShell and paste:

```powershell
irm https://raw.githubusercontent.com/ThuoBrian/finance-pii-redactor/main/install.ps1 | iex
```

**macOS/Linux** — open a terminal and paste:

```bash
curl -fsSL https://raw.githubusercontent.com/ThuoBrian/finance-pii-redactor/main/install.sh | bash
```

Pick a folder when asked, then wait — first run downloads ~400 MB (the
language model) and needs internet once. The app opens in your browser when
it's ready.

If something goes wrong here, check **[GOTCHA.md's "Environment and
setup"](GOTCHA.md#environment-and-setup)** section before reporting it.

## Test data

Build a small test `Names List - Organized.xlsx` (see
**[data/README.md's File format](../data/README.md#file-format)**) with a
handful of made-up entries across all three sheets (`Staff`, `Vendors`,
`Funders`) — 5-10 rows each is enough. Put it in the local `data/` folder the
installer created (do not set `FPR_MASTER_LIST_DIR`, so this stays your own
sandbox, separate from the shared team list).

Then create a few small test files (Excel, PDF, Word) containing some of
those made-up names/vendors/funders in normal sentences — e.g. "Paid to
[test name] on behalf of [test funder]" — plus at least one email address
and one website URL.

## Test scenarios

Check each box against your own test files. For anything that doesn't
match, note: file type, exact text you typed/uploaded, what you expected,
what happened instead — then file it.

### Excel

- [ ] Upload a workbook; text columns are pre-selected, numeric/date columns
  aren't.
- [ ] A test name/vendor/funder in your master list redacts to its curated
  ID (e.g. `STF-91345`), consistently on every occurrence.
- [ ] A name **not** in your master list still redacts, to a flagged
  `*-AUTO-*` ID (check the crosswalk's **Flagged** column).
- [ ] Lowering the confidence threshold flags more text; raising it flags
  less.
- [ ] Unchecking an entity type (e.g. `ORGANIZATION`) stops it from being
  redacted.
- [ ] Downloaded file has a second **Crosswalk** sheet mapping names to IDs.
- [ ] Editing the master list workbook, saving, and clicking **🔄 Refresh
  master list** picks up the change without restarting the app.

### PDF

- [ ] An email address and a website URL redact automatically, with nothing
  typed in.
- [ ] A name/organization does **not** redact unless typed into "Additional
  words/phrases to redact" — this is expected (see
  [GOTCHA.md](GOTCHA.md#pdf-has-no-automatic-nameorganization-detection---only-emails-websites-images-and-typed-words)),
  not a bug to report.
- [ ] Typing a name into that box redacts every occurrence, case-insensitive.
- [ ] Switching **Pseudonymize** vs **Black out** changes the output as
  described in each option's help text.
- [ ] With "Also black out images/logos" checked (default), an embedded
  image on the page is covered by a black box.
- [ ] A scanned/image-only PDF (no selectable text) is left untouched aside
  from images — expected, not a bug.

### Word

- [ ] A test name in the document body, a table cell, and a header/footer
  are all redacted.
- [ ] A name in a text box or SmartArt is **not** redacted — expected (see
  [GOTCHA.md](GOTCHA.md#a-name-inside-a-word-text-box-smartart-or-embedded-object-is-not-detected)).
- [ ] Downloaded document keeps original formatting (bold, tables, etc.)
  around the redacted text.

### Edge cases worth specifically trying

- [ ] An ALL-CAPS name (e.g. `JANE MUTHONI`) is still detected.
- [ ] An org name with a suffix variant not in the master list (list has
  `Acme Ltd`, document says `Acme Limited`) still resolves to the same ID.
- [ ] An accented name (`José García`) typed into a PDF/Word custom-words
  box (using the unaccented approximation, `Jose Garcia`) still matches the
  accented text in the document.
- [ ] Deliberately create a data-quality issue in your test master list (two
  rows with the same name in different categories, or two names sharing one
  `Internal ID`) — a warning banner appears under **Advanced settings** the
  next time you load a file.

## Reporting results

For each unchecked box or unexpected result, [open a GitHub
issue](https://github.com/ThuoBrian/finance-pii-redactor/issues/new) with:

- What you did (exact file type, text, and settings).
- What you expected vs. what happened — a screenshot of the **Detection
  details** table and/or crosswalk helps a lot.
- Whether it's reproducible on a second try.

Check **[GOTCHA.md](GOTCHA.md)** first — several things that look like bugs
(no PDF name detection, text boxes not scanned, scanned PDFs untouched) are
documented, deliberate limits, not something to file.
