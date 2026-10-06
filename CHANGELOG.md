# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
the `version` field in `pyproject.toml`.

## [Unreleased]

### Added

- **The Windows installer adds a "Finance PII Redactor" shortcut** to the
  Desktop and Start menu, so reopening the tool is a double-click instead of
  finding `run.bat`. Updating refreshes it. If a managed machine blocks
  shortcuts, the install carries on and `run.bat` still works. The installer
  now also confirms the shortcut files actually landed (some locked-down
  machines let shortcut creation report success without writing anything),
  and `run.bat` re-creates the Desktop shortcut on launch if it's missing,
  for anyone who skipped the installer or deleted it.
- **The app defaults to Streamlit's dark theme** (`.streamlit/config.toml`),
  since the logo (`assets/data-privacy-ai-dark-nobg.svg`) is a white-on-
  transparent SVG and was invisible on the default light background.
- **A "Close the app" button in the sidebar** (`presentation/shutdown.py`)
  fully quits the tool from the browser, with one confirm step. Closing only
  the browser tab, or only the console window, used to leave the other one
  running in the background with the master list and NLP model still in
  memory; this button (hard process exit, `os._exit`) ends both at once.
- **A corrupted or wrongly-renamed upload now gets a plain-language message**
  instead of a raw traceback, in all three formats. `UnreadableFileError`
  (`domain/errors.py`) is raised by the Excel/Word/PDF gateways and caught in
  their views, the same pattern `EncryptedPdfError` already used for a
  locked PDF.
- A custom `primaryColor` (`.streamlit/config.toml`) replaces Streamlit's
  default button red, which only cleared 3.30:1 against white button-label
  text - below WCAG AA's 4.5:1 for normal text, and this app leans on
  primary buttons for most of its key actions.
- Developer docs use a system `just` (`winget install Casey.Just`), so it's
  `just check` rather than `uv run just check`. The `rust-just` dev
  dependency stays as a fallback and is what CI uses.

### Changed

- **Streamlit usage statistics are switched off** (`gatherUsageStats = false`
  under `[browser]` in `.streamlit/config.toml`), so the app makes no
  telemetry requests.
- **Cleaner layout, using Streamlit's own components only (no custom CSS, no
  HTML injection).** Each step sits in a bordered box; the step tracker is a
  row of native badges; results show as counts (`st.metric`) with
  **Preview / Mapping / Details** tabs (Word and PDF have no preview, so just
  Mapping / Details); scanning shows a progress status instead of a spinner.
  PDF redaction style, additional words and the image option are now plain
  options, and **Advanced settings** (confidence threshold, kinds of
  information) starts collapsed, with master-list quality warnings shown above
  it. Nothing about detection or redaction changed.
- **Excel preview is now a table you can scroll and sort**, not HTML. Changed
  cells are yellow (the same yellow as the downloaded workbook, replacing the
  orange/green preview colours) and also start with `»`, so they show
  without relying on colour. The preview stops at 500 rows and says how many
  highlighted cells it hid; the download always has every row. This removes
  the app's only `unsafe_allow_html`. `presenters.highlighted_html` is replaced
  by `presenters.preview_styler`.
- **Plain-language help** for the confidence threshold and kinds of
  information; the "Redact?" tick column is now "Hide in output?"; counts read
  "1 match" / "2 matches" instead of "match(es)".
- **The built Excel file is kept in session state**, like Word and PDF, so it
  is no longer rebuilt on every click.
- `jinja2>=3.1.5` is now a declared dependency (locked at 3.1.6): pandas'
  `Styler`, used for the preview, refuses to import with the previously locked
  3.1.4.

### Fixed

- **Editing the master list, or choosing a different master-list folder, now
  takes effect on the next rerun.** The cache arguments in `app.py`'s
  `_get_master_list_bundle` started with an underscore, which Streamlit leaves
  out of the cache key, so the list was never reloaded except by **Refresh
  master list** or a restart. They are now plain `path` and `mtime`.
- **Excel's before/after comparison table was unreadable in the new dark
  theme.** `highlighted_html` (`presentation/presenters.py`) shaded a
  highlighted cell's background but never set its text color, so the text
  inherited the page's theme color — near-black on the old light theme
  (fine), near-white on the new dark default (close to invisible against the
  light orange/green highlight colors). The highlighted branch now sets an
  explicit dark text color, since the highlight colors themselves never
  change with the theme.
- Excel's "Advanced settings" expander now starts open, like PDF's and
  Word's, instead of being the one collapsed-by-default panel of the three.
- The "Entity types to pseudonymize" multiselect (Excel, Word) now has a
  `help=` tooltip explaining what the entity types mean in plain language,
  matching the other inputs in the same panel.

### Added

- **PDF detects names that aren't on the master list.** The PDF flow now uses
  the same spaCy-backed engine as Excel and Word, which reverses the old
  "no guessing in PDF" rule. An unlisted name gets a label in the document and
  a flagged `AUTO-` row in the mapping, which still holds no names. Model
  false positives are unticked in the review table. `PatternDetector` is gone.
- **Postal and street addresses are masked as `[ADDRESS]`** in all three
  formats: P.O. boxes, plot/house/L.R. numbers, and street addresses
  (`infrastructure/detection/address_recognizers.py`). Town and country names
  on their own are deliberately left alone.
- **Link destinations are removed from Word and PDF output.** Web, email and
  file links are stripped, and the visible text still goes through detection.
  Links within the same PDF stay. The download section shows how many were
  removed.

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

- **Rebuilding a PDF after unticking a false positive is much faster.**
  `RedactPdfService` now splits into `scan()` (runs name/entity detection once)
  and `redact()` (rebuilds the output from that cached scan), the same split
  Excel already used. Unticking a term in the review table no longer re-runs
  detection at all — only the redaction-building/apply step reruns.
- **Rebuilding a Word document after unticking a false positive is much
  faster, the same way.** `RedactDocxService` now splits into `scan()` and
  `redact()` too, so unticking a term no longer re-runs spaCy over every
  paragraph. Also fixes a `NameError` on that same path: the "words to
  redact" list is now computed once per rerun instead of only inside the
  button's own click handler.
- **Rejecting false positives is now reviewed in one batch.** The
  **Check what was detected** table sits inside a form with an **Apply
  changes** button: tick or untick as many rows as you like, and the file
  rebuilds once, on Apply, instead of once per tick. Previously every single
  tick triggered its own full Streamlit rerun and rebuild.
- **Download is now the one clearly emphasized action once a file is
  processed.** Previously the main action button (Pseudonymize/Black out),
  Apply changes, and Download were all highlighted red at the same time,
  with no visual cue for which to use next. The main action button and
  Apply changes now render as plain buttons once a result exists, leaving
  Download as the single highlighted next step.
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
- **Repository layout.** Docs renamed to lowercase-dash names:
  `docs/GOTCHA.md` is now `docs/troubleshooting.md`, `docs/TESTING.md` is now
  `docs/user-testing.md`, and `docs/BOX_SETUP.md` is now `docs/box-setup.md`.
  `image/` is now `assets/`. `tests/` is split into folders that mirror the
  package layers. `pdf_text_normalizer` moved from `infrastructure/detection/`
  to `domain/`, so the application layer no longer imports infrastructure.
- Added public `ARCHITECTURE.md`, `AGENTS.md` and `.github/SECURITY.md`.
  Public docs no longer point at the untracked `CLAUDE.md`.
- `tests/test_layers.py` fails if a module imports across layers the wrong
  way, or if `domain/` imports anything outside the standard library.
- CI now runs `uv run just check` instead of repeating each command, so the
  justfile is the one list of checks.

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

- The visible text of a Word hyperlink was never scanned, because python-docx
  leaves hyperlinked runs out of `paragraph.runs`. A name written as a link
  went through untouched, along with its `mailto:` target. Hyperlinks are now
  unwrapped before detection.

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
