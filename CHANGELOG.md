# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
the `version` field in `pyproject.toml`.

## [Unreleased]

### Added

- **Bank and payment details are detected and masked.** Card numbers and
  IBANs (Presidio's checksum-validated recognizers), plus Kenyan bank account
  numbers, M-Pesa till/paybill numbers and SWIFT/BIC codes
  (`infrastructure/detection/financial_recognizers.py`, matched only when
  their label is right in front of them). They are replaced with a fixed mask
  from `Settings.fixed_masks` (`[CARD]`, `[IBAN]`, `[ACCOUNT]`, `[MPESA]`,
  `[SWIFT]`) and never enter the crosswalk or the PDF mapping, so no PDF
  label number is used up. Works in all three formats, including the
  spaCy-free PDF detector. Untick PERSON/ORGANIZATION to scan for bank
  details alone in Excel and Word.
- The three redaction services take a required `fixed_masks` argument.
  Required on purpose: a masked type falling through to the pseudonymizer
  would write the raw number into the downloaded crosswalk.

- **A way to reject a false positive.** Every detection now appears in a
  **Check what was detected** table with a `Redact?` tick box; unticking a term
  rebuilds the output without it, for that document only. Nothing persists.
  Prompted by the ordinary word "salaries" being redacted from a PDF, which
  turned out to be a master-list row named `Salaries` — and which nothing in
  the tool could refuse, since every stage only ever added detections.
  Available in all three formats; for PDF it is the first such lever of any
  kind, as that flow has no confidence threshold or entity filter.
- The table reports **Source** per term, because that determines the lasting
  fix: `master list` means edit the workbook, `model` means raise the
  threshold, `custom word` means clear the words box. Terms are grouped by
  normalized text, so a word appearing forty times is one tick box and
  unticking it covers every casing and spacing of it.
- Unticking is a deliberate under-redaction, so the affected terms are named
  in a warning above the download button and the downloaded file contains them
  verbatim.
- `RedactExcelService.redact`, `RedactPdfService.execute` and
  `RedactDocxService.execute` take an `exclude` set of normalized terms,
  applied before the pseudonymizer so an excluded term reaches neither the
  output nor the crosswalk, and the PDF labels that are written stay
  contiguous. Re-applying in Excel reuses the existing scan result and never
  re-runs detection.
- `docs/GOTCHA.md` gains "An ordinary word is being redacted", covering how to
  tell the three causes apart. It also documents that raising the confidence
  threshold past 0.90 stops **every** curated master-list name from matching,
  which was previously undocumented.

### Changed

- **PDF redaction now writes a per-document label (`[001]`) instead of a
  pseudonym.** A pseudonym is literally `<prefix>-<Internal ID>`, so the
  redacted PDF used to carry the master list's own join key: anyone holding
  the master list could re-identify the file with no mapping at all. A label
  means nothing outside the document it came from. Decoding takes two hops —
  the mapping says `[001] = 17728`, the master list says what 17728 is — which
  splits re-identification between two sets of hands.
- **The PDF mapping download contains no names**, only label, Internal ID,
  category, entity type, a flag, and which master list it was made from. It is
  therefore *Internal* rather than *Confidential* and can be kept with the
  redacted PDF. Names are still shown in the on-screen review table.
  Filename changed from `*_crosswalk.csv` to `*_mapping.csv`.
- Labels restart at `[001]` in every document. Cross-document linkage is now
  recovered by joining two mapping files on the Internal ID, not by reading the
  documents. Old and new redacted PDFs cannot be cross-referenced by eye.
- **Excel and Word are unchanged**: still `STF-10010`-style pseudonyms, still a
  names-bearing crosswalk, same classification as before. One entity therefore
  looks different in a PDF than in an Excel export of the same data.

### Added

- PDF typed words are now resolved against the master list, so a word on the
  list carries its curated `Internal ID` into the mapping. This adds no
  automatic name detection to PDFs — it only resolves matches the user asked
  for. A word that is not on the list, or that matches several rows with
  conflicting IDs, is still redacted but flagged with no Internal ID rather
  than being given a guessed one.
- Unresolved entities get a deterministic `AUTO-` placeholder in the mapping's
  Internal ID column rather than a blank, so they stay visibly unresolved and
  still link across documents. It is a hash of the name, not the name.
- PDF mappings are stamped with the master list's filename, modification time,
  and row count, so a decode against a since-edited list is detectable.
- A warning when a PDF already contains its own bracketed numbers (footnote
  markers, line items), since those are indistinguishable from labels, and
  when a typed word is itself label-shaped.

### Fixed

- Clearing the entity-type list in Excel or Word made Presidio run *every*
  recognizer it has (dates, phone numbers, US bank numbers), because it reads
  an empty list as "all". It now detects nothing.
- Excel: a whole-number float cell (how pandas reads an integer column with a
  blank) is scanned as `1234567890`, not `1234567890.0`, and blank cells are no
  longer scanned as the text `nan`. Writing a replacement into a numeric
  column no longer raises on pandas 3.

- **PDFs now redact names that are on the master list, without them being
  typed in.** Previously a PDF full of curated names came back with only its
  email addresses redacted. Excluding spaCy from the PDF flow was meant to
  keep *statistical guessing* out, but it also dropped exact matching against
  the master list, which is as deterministic as the email regex that was
  already running. The curated recognizer (an Aho-Corasick automaton, the same
  object Excel and Word use) now runs in the PDF flow. spaCy still does not: a
  name not on the master list is still only redacted if typed into the box.
- PDF's Advanced settings now shows the master-list status panel, like Excel
  and Word. The PDF flow depends on the master list for detection, so an empty
  or unsynced list silently leaves curated names in the document; that panel is
  what makes the condition visible.
- Accent folding was applied when matching typed words but not when resolving
  them, so a typed `Jose Garcia` could match `José García` in a document and
  then silently fail to resolve against a `Jose Garcia` master-list row. Both
  paths now share one implementation.
- PDF label numbering follows position on the page. `dedupe_overlapping` sorts
  by detection source before position, which would otherwise have numbered a
  match late in the document before one near the top.

### Security

- Replaced real staff names, a real vendor/country pairing, and their real
  `Internal ID`s with synthetic equivalents across test fixtures, docstrings,
  and docs. These had been committed since `2ea8edd` and this repository is
  public. Synthetic IDs now come from a reserved `10001`+ block. Removing them
  from the working tree does not remove them from earlier commits, so the
  disclosure stands on its own and is being handled separately.
- Added `tests/test_no_real_pii_in_repo.py`, which fails if any of those
  values reappears in a tracked file. The forbidden values are stored as
  truncated hashes, never plaintext, so the guard cannot reintroduce what it
  checks for.

## [0.1.0] - 2026-09-07

Initial development version. No tagged releases yet; this summarizes the
project's history to date.

### Added

- Excel, PDF, and Word redaction flows, pseudonymizing names/organizations to
  stable ID codes from a master list (`data/Names List - Organized.xlsx`).
- Master-list data-quality checks on load: cross-category duplicates,
  conflicting or reused `Internal ID`s, blank IDs, and ambiguous common-word
  names.
- Support for one shared master list across a team, via the
  `FPR_MASTER_LIST_DIR` environment variable or an in-app "Set up your
  shared master list" dialog.
- A **🔄 Refresh master list** button so edits are picked up without
  restarting the app.
- Crosswalk output: an embedded second sheet in Excel, or a separate CSV
  download for PDF/Word.
- Automatic email, website, and image/logo redaction in PDF; a
  words/phrases-to-redact box for anything PDF or Word can't detect
  automatically (names, codenames, case numbers).
- Fuzzy "possible match" suggestions for flagged auto-ids, and accent-folding
  so an unaccented approximation (`Jose Garcia`) matches an accented name
  (`José García`) in the words-to-redact box.
- Alias-aware master-list matching (`Ltd`/`Limited`, `&`/`and`, etc.) so one
  master-list row covers common surface-form variants.
- One-line installers (`install.ps1`, `install.sh`) and local launchers
  (`run.bat`, `run.sh`).
- CI (`ruff`, `ruff format`, `mypy`, `pytest` with an 80% coverage gate,
  `codespell`) and Dependabot.
- `docs/GOTCHA.md` (known issues/troubleshooting) and `docs/TESTING.md` (a
  user-acceptance testing checklist).

### Changed

- Master list migrated from plain-text lists to a single Excel workbook
  (`Names List - Organized.xlsx`).
- PDF detection scoped down to emails, websites, and images only — names and
  organizations are no longer guessed at in PDF (an intentional accuracy
  trade-off; see `docs/GOTCHA.md`), and must be typed into the
  words-to-redact box instead.
- Overlapping-span dedupe now prefers a master-list match over an overlapping
  model guess, regardless of which span is longer.
- `CustomNameRecognizer` switched from a per-name regex loop to an
  Aho-Corasick automaton for matching performance.
- Relicensed from MIT to Apache 2.0.

### Fixed

- PDF redaction in tightly single-spaced documents no longer bleeds into the
  line above the matched text.
- Legacy names with an ID appended in the name itself (`Jane Doe - 10001`)
  now match correctly.
- ALL-CAPS names are now detected (spaCy's NER model misses them in the
  original casing).

### Removed

- `CLAUDE.md` (internal architecture notes) is no longer tracked in this
  repository — kept local-only; ask the maintainer for a copy.
