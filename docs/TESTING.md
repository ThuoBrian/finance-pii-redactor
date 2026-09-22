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
- The same rule applies to anything committed to this repository, including
  test fixtures, docstrings, and examples in these docs. It is enforced by
  `tests/test_no_real_pii_in_repo.py`, which fails if a known real name,
  organization, or `Internal ID` reappears in a tracked file. It stores those
  values as hashes rather than plaintext, so a failure tells you the file and
  line but not the matched value — look at the line it reports. Use IDs from
  the `10001`+ synthetic block so they can never collide with real ones.
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
  ID (e.g. `STF-10010`), consistently on every occurrence.
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
- [ ] A name/organization **that is on your test master list** redacts with
  nothing typed into "Additional words/phrases to redact".
- [ ] A name that is **not** on the master list does **not** redact unless
  typed into that box — expected (see
  [GOTCHA.md](GOTCHA.md#pdf-only-auto-detects-what-can-be-matched-exactly---no-spacy-guessing)),
  not a bug to report.
- [ ] The master-list summary appears in PDF's **Advanced settings**, showing
  the same row counts as Excel and Word. If it shows 0 names, curated names
  will silently not be redacted — that is the check that catches it.
- [ ] Typing a name into that box redacts every occurrence, case-insensitive.
- [ ] Redacted text is replaced by a numbered label (`[001]`, `[002]`, and so on),
  **not** an ID code, and the same name gets the same label everywhere in
  that one PDF.
- [ ] Redact a **second** PDF: its labels start over at `[001]`. Expected -
  labels are per-document by design.
- [ ] A name that **is** in your test master list shows a real `Internal ID`
  in the mapping's **Internal ID** column.
- [ ] A name that is **not** in the master list still redacts, and its
  mapping row shows an `AUTO-` placeholder plus a reason under **Flagged**.
  A warning about it appears *above* the mapping panel, not buried inside it.
- [ ] **Download the label mapping (CSV) and confirm it contains no names.**
  This is the most important check on this page: the file is only safe to
  keep with the redacted PDF because it cannot identify anyone alone.
- [ ] The mapping's **Master list** column names the workbook it was made
  from, with a timestamp and row count.
- [ ] Redact a PDF that already contains bracketed numbers of its own (e.g.
  a footnote marker `[4]`) — a warning says labels may be ambiguous in the
  output.
- [ ] Switching **Pseudonymize** vs **Black out** changes the output as
  described in each option's help text. Blackout produces no mapping, since
  there is nothing to decode.
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
- [ ] Put the **same name in two categories with different `Internal ID`s**,
  then type it into a PDF's words box. It should still redact, but its
  mapping row should say `ambiguous` and carry no `Internal ID` — the tool
  refuses to guess between the two rather than recording a wrong ID.
- [ ] Redact the **same data** as both an Excel file and a PDF. The outputs
  deliberately look different (`STF-10010` vs `[001]`); they can only be
  cross-referenced through the `Internal ID`, not by eye.

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
