# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

A Streamlit application that **pseudonymizes** names and organization names in Excel and PDF files locally — each detected name is replaced with a stable ID (e.g. `STF-91345`, `VND-1045`, `FND-7745`) rather than a generic `[PERSON]` label, so the same entity maps to the same ID everywhere and cross-row/cross-file patterns survive for error-checking and fraud monitoring. It uses Microsoft Presidio with a spaCy `en_core_web_lg` model for PII detection, a `pyahocorasick` automaton for fast master-list name matching, openpyxl for Excel output, and PyMuPDF for PDF text replacement. This is distributed as an offline-capable desktop tool: users double-click `run.bat` (Windows) or `run.sh` (macOS/Linux) to start the local web server and open the browser.

IDs come from a maintained **master list** (`data/Names List - Organized.xlsx`, a top-level user-owned folder outside the package). Names not in the list are still pseudonymized with a stable, flagged auto-id and surfaced in a downloadable name→pseudonym **crosswalk** (the re-identification key — treat as Confidential).

## Common development commands

This project uses `uv` for environment management and Python 3.12.

- **Set up environment and install all dependencies (including dev):**

  ```bash
  uv sync --python 3.12
  ```

- **Run the app:**

  ```bash
  uv run streamlit run app.py --server.address=127.0.0.1
  ```

- **Run linting and auto-fixes:**

  ```bash
  uv run ruff check --fix app.py finance_redactor/
  uv run ruff format app.py finance_redactor/
  ```

- **Run spell-check:**

  ```bash
  uv run codespell
  ```

- **Run prose linting** (docs only: `*.md`; IPA code-quality check). Requires
  [Vale](https://vale.sh) installed separately (`winget install errata-ai.Vale`
  / `brew install vale`) — it is not a Python dependency, so `uv sync` does not
  install it:

  ```bash
  vale sync   # first time only, fetches style packages into .vale/styles/
  vale README.md CLAUDE.md docs/ data/README.md
  ```

  (Don't run bare `vale .` — it recurses into `.vale/styles/` itself and lints
  the downloaded style packages' own README/LICENSE files.)
  Config lives in `.vale.ini` (styles: `write-good`, `alex`, `proselint`,
  plus Vale's built-in spelling check). `.vale/styles/config/vocabularies/Base/accept.txt`
  is this project's custom vocabulary (domain/tooling jargon that isn't in
  Vale's dictionary) — add a term there rather than rewording a sentence to
  dodge a spelling false-positive. `alex.Race`, `alex.Profanity*`, and
  `write-good.E-Prime` are disabled in `.vale.ini`: they had a near-100%
  false-positive rate on this repo's own vocabulary (this is fraud-monitoring
  software — "fraud" isn't profanity — and "master list" isn't the master/slave
  sense the race rule targets).

- **Run tests:**

  ```bash
  uv run pytest
  ```

  Tests under `tests/` cover the framework-free logic (pseudonym assignment,
  span replacement, master-list parsing, fuzzy matching, data-quality checks),
  the infrastructure adapters (the Presidio detector, via a mocked
  `NlpEngineProvider` rather than the real spaCy model, the PDF gateway, and
  the Excel gateway), and presentation-layer formatting (presenters,
  master-list view). None of them require the real spaCy model to be
  installed.

- **Regenerate the master list from legacy `.txt` lists** (one-off migration helper,
  only useful when migrating old plain-text lists to the Excel format):

  ```bash
  uv run python scripts/migrate_to_master_list.py
  ```

- **Check known issues:** see `docs/GOTCHA.md` for recurring errors and solutions.

- **The spaCy model is a pinned dependency**, so `uv sync` installs it (and never
  prunes it). It is declared in `pyproject.toml` as a wheel-URL requirement
  (`en_core_web_lg @ https://.../en_core_web_lg-3.8.0-...whl`); there is no longer
  a separate `spacy download` step. To bump it, change the pinned URL and re-sync.

## Architecture

The code follows **clean architecture**: four concentric layers under
`finance_redactor/`, with dependencies pointing inward only (outer layers depend
on inner; inner layers never import outer). Third-party libraries (Presidio,
PyMuPDF, openpyxl, Streamlit) are confined to the outermost layers.

- **`app.py`** — the Streamlit entry point **and composition root**. It builds the
  object graph (wires concrete adapters into use cases via constructor injection),
  routes the upload to the Excel or PDF flow by extension. The `get_script_run_ctx()`
  guard at the bottom keeps `_main()` from running on import (tests/linters). It
  caches the heavy spaCy NLP model with `@st.cache_resource`, and separately caches
  the master-list-derived bundle (parsed rows, custom recognizers, detection engine,
  and the run's `quality_report()`) keyed on the workbook's modification time, so
  unrelated reruns reuse both while edits to `data/Names List - Organized.xlsx` still
  take effect on the next refresh without a server restart. Both the Excel and PDF
  flows receive that `quality_report()` and render it in the Advanced settings panel
  via the shared `master_list_view`.
- **`finance_redactor/domain/`** — framework-free core. `entities.py`
  (`PiiDetection`, `Span`, `Finding`, `DetectionSource` = `MODEL`/`MASTER_LIST`) is
  the one representation of a finding all layers speak. `rules.py` holds
  `dedupe_overlapping` and `classify_source` (score → model/master list).
  `dedupe_overlapping` breaks overlaps by source first (a `MASTER_LIST`
  detection always wins over an overlapping `MODEL` detection, regardless of
  which span is longer — a curated exact match is a stronger signal than a
  statistical guess, e.g. spaCy fusing a trailing hyphenated phrase onto a
  curated name, `"Brian Thuo - Kakamega"`, must not out-vote the exact
  master-list match `"Brian Thuo"`), then leftmost/longest within the same
  source. `pseudonyms.py` holds the pseudonymization core:
  `normalize`, the `Pseudonymizer` (master-list lookup + deterministic auto-id
  fallback, accumulating the crosswalk), and `apply_replacements` (dedupe + slice
  spans right-to-left). **This is the single seam where a name becomes an ID.**
  On an auto-id (no exact/alias match), the `Pseudonymizer` also asks
  `fuzzy.py`'s `closest_match` for the nearest curated name of the same entity
  type and, if one clears `Settings.fuzzy_match_threshold`, records it on the
  `Assignment` (`suggested_pseudonym`/`suggested_name`/`suggested_score`) as a
  reviewer hint only — it never changes which pseudonym gets assigned. `fuzzy.py`
  is deliberately conservative for the same reason `aliases.py` skips middle
  initials: two distinct real names can be one edit apart (`Kevin Otieno` vs.
  `Kelvin Otieno`), so auto-merging on similarity risks silently attaching one
  person's history to another's ID — worse than leaving a flagged auto-id for a
  human to resolve. `aliases.py` derives variant surface forms of a name
  (org-suffix equivalents `Ltd`↔`Limited`, `&`↔`and`): `aliases()` feeds both the
  master map's extra lookup keys and the literal keys inserted into the
  recognizer's Aho-Corasick automaton (see `CustomNameRecognizer` below), so a
  document's `Acme Limited` resolves to the curated `VND-` id of a workbook
  `Acme Ltd`. `quality.py` defines the `QualityIssue` DTO for master-list
  data-quality findings. No imports of Presidio/pandas/Streamlit.
- **`finance_redactor/application/`** — use cases over abstract **ports**.
  `ports.py` defines `Protocol`s (`PiiDetector`, `ExcelGateway`, `PdfDocument`,
  `PdfDocumentFactory`) — there is no `TextRedactor`; replacement is done in the
  domain. `redact_excel.py` (`RedactExcelService`) and `redact_pdf.py`
  (`RedactPdfService`) build a `Pseudonymizer` per run, orchestrate domain + ports,
  and return the DTOs in `results.py` plus the run's `crosswalk` (list of
  `Assignment`). This layer imports no concrete framework.
- **`finance_redactor/infrastructure/`** — concrete adapters implementing the
  ports. `detection/` (`PresidioEngine` for `PiiDetector` only — detection, no
  anonymizer; `CustomNameRecognizer`, which builds one `pyahocorasick`
  Aho-Corasick automaton per entity type from every alias variant
  (`domain.aliases.aliases`) of every master-list name, lowercased for
  case-insensitive matching — a single pass over the text finds all loaded
  names regardless of master-list size, replacing an earlier per-name regex
  loop that cost O(number of names) per scan (~64ms/call against the real
  ~26.5k-row list; ~0.28ms/call with the automaton). Since automaton keys are
  literal strings, not regexes, whitespace flexibility (previously `\s+`) is
  replicated by normalizing the text first (reusing `pdf_text_normalizer.py`
  below — generic despite its name), and the old `\b...(?!\w)` boundary check
  is replicated manually against raw match positions; `recasing.py`;
  `pdf_text_normalizer.py`), `documents/` (`OpenpyxlExcelGateway`,
  `PyMuPdfDocument`), `names/` (`MasterListRepository` +
  `data/Names List - Organized.xlsx`). Presidio's
  `RecognizerResult` is translated to the domain `PiiDetection` **only** here.
  `PresidioEngine.analyze` runs spaCy on the raw text and — when ALL-CAPS tokens
  are present — a **second pass on a length-preserving recased copy**
  (`recase_uppercase`, `MARY` → `Mary`) so the model catches ALL-CAPS names;
  results from both passes are unioned and de-duplicated via the domain
  `dedupe_overlapping` (spans stay valid because recasing preserves length;
  detections are sliced from the original text). For PDFs, `RedactPdfService`
  normalizes the extracted page text before detection (ligatures, line-break
  hyphenation, irregular whitespace) and maps detection spans back to the original
  text so replacements can be applied.
- **`finance_redactor/presentation/`** — the only layer importing Streamlit.
  `excel_view.py`/`pdf_view.py` own widgets + session state and delegate to use
  cases; `presenters.py` turns results into UI artifacts (highlighted HTML, the
  findings + crosswalk tables); `crosswalk_view.py` renders the shared crosswalk
  expander + guarded CSV download; `master_list_view.py` renders the shared
  master-list summary line + data-quality warnings shown in both flows' Advanced
  settings panel.
- **`finance_redactor/config.py`** — the single source of truth: an immutable
  `Settings` dataclass (language, spaCy model, entities, `categories`
  (category → (prefix, entity_type)), `category_sheets`, `auto_prefixes`,
  `custom_match_score`, default threshold, `fuzzy_match_threshold`,
  `master_list_file`). Replaces scattered module-level constants and the
  duplicated `0.9` magic number.
- **Master list:** `data/Names List - Organized.xlsx` — a **top-level, user-owned folder**
  outside the package by default (resolved by `Settings.names_dir` via
  `config.py`'s `_resolve_data_dir()`), kept separate from the code (and out of
  git). `_resolve_data_dir()` honors the `FPR_MASTER_LIST_DIR` environment
  variable when set, so a team can instead point every install at one shared,
  access-controlled location and get identical curated IDs across users — see
  `data/README.md`'s "Sharing one master list across a team" and the matching
  `docs/GOTCHA.md` entry; unset, behavior is unchanged (per-install local
  folder). Note this only affects *curated* IDs — the auto-id fallback for
  names not on the list is already consistent across installs by construction
  (a plain hash of the normalized name plus a hardcoded prefix table), with or
  without a shared list. The
  workbook has one sheet per category (`Vendors`, `Funders`, `Staff`) with columns
  `Category`, `Internal ID`, `Name`, `Primary Subsidiary`, `Country`. It is the
  **single source** for both detection and pseudonym IDs. `Category` maps via
  `Settings.categories` to a prefix + entity type (`Staff`→`STF`/PERSON,
  `Vendor`→`VND`/ORGANIZATION, `Funder`→`FND`/ORGANIZATION); pseudonym =
  `f"{prefix}-{Internal ID}"`. Every name drives detection (custom recognizer, fixed score
  `0.9` = `Settings.custom_match_score`); a row with a **blank `Internal ID`** is still
  detected but pseudonymizes to a flagged auto-id. Trailing legacy ID suffixes in
  `Staff` names (e.g. `Jane Doe - 22463`) are stripped and the `Internal ID` column
  is always used as the curated ID. Edit the workbook and restart; counts by
  category show in the Advanced settings panel. **Alias/variant matching:** each
  curated name also registers its variant surface forms (`aliases()`:
  org-suffix equivalents, `&`/`and` swaps, period-tolerant) as extra lookup keys,
  and the recognizer inserts the same variants as literal keys into its
  Aho-Corasick automaton, so `Acme Limited` / `Acme Ltd.` resolve to the same
  `VND-<id>` as a workbook `Acme Ltd` without editing the list. The master map
  is built in two passes — canonical names first
  (first row wins an exact-name collision), then aliases fill only still-empty
  keys — so an alias can never clobber another row's canonical name. Middle
  initials are intentionally not normalized (would merge distinct people).
  **Data-quality guards:** `MasterListRepository.quality_report()` surfaces five
  issue kinds in the Advanced settings panel — cross-category duplicate names,
  conflicting Internal IDs (same name, one category, multiple IDs), blank
  `Internal ID` rows (advisory — they get flagged auto-ids), reused Internal
  IDs (one id shared by different names), and ambiguous common-word names
  (advisory — a single-token name, e.g. a funder literally named `Across`,
  that is also an ordinary English word, so every plain-English occurrence of
  the word gets detected too). Benign exact-duplicate rows (same name *and*
  same id) are not flagged.
- **Master-list caching:** `MasterListRepository` caches parsed rows keyed by the
  workbook's file modification time, and `app.py` wraps the whole
  repo/recognizers/engine bundle in an `@st.cache_resource` factory keyed on that
  same mtime. The first parse of the full ~26k-row workbook takes a few seconds;
  subsequent Streamlit reruns with an unchanged mtime reuse the cached bundle
  (instead of re-parsing and recompiling recognizer patterns on every widget
  interaction), so widget interactions stay fast while edits to the Excel file
  still take effect immediately on refresh (the new mtime busts the cache).
- **Pseudonyms & crosswalk:** a name in the master list (or any of its alias
  variants — org-suffix equivalents, `&`/`and`) resolves to its curated ID; an
  unknown name gets a deterministic, stable auto-id (`PSN-AUTO-<hash>` /
  `ORG-AUTO-<hash>`, same input → same id across files) and is flagged for review.
  For a flagged auto-id, the crosswalk's **Possible match** column (see
  `fuzzy.py` above) shows the nearest curated name when one is close enough to
  suggest a typo (e.g. document text `Micheal Mugo` against a workbook
  `Michael Mugo`) — advisory only, never auto-applied. Each run's name→pseudonym
  crosswalk is shown in a review table and is the **re-identification key
  (Confidential)** — how it reaches the user differs by file type: for Excel
  it's embedded as a "Crosswalk" sheet in the pseudonymized workbook itself
  (`OpenpyxlExcelGateway.write`, see "Excel flow" below), making that whole
  `.xlsx` download Confidential, not just Internal; for PDF (no sheet
  concept) it's still only a separate, warning-gated CSV download
  (`crosswalk_view.render_crosswalk_section` with `download_separately=True`,
  its default), and the UI still warns there against ever sharing it
  alongside the pseudonymized PDF.
- **Excel flow:** the gateway reads the workbook (pandas/openpyxl); selected text
  columns are scanned positionally; detections are kept per cell (`CellFinding`).
  `redact` runs `apply_replacements` per cell against one sheet-wide `Pseudonymizer`
  (so a name is consistent across cells) and the gateway writes the workbook with
  changed cells highlighted yellow. `OpenpyxlExcelGateway.write` also takes the
  run's crosswalk (as a DataFrame, via `presenters.crosswalk_dataframe` — the
  same shaping used for the PDF flow's crosswalk CSV) and writes it as a second
  "Crosswalk" sheet alongside "Redacted", so every downloaded Excel file
  carries its own re-identification key by default (see "Pseudonyms &
  crosswalk" below for the confidentiality consequence of that).
- **PDF flow:** the use case pulls per-page raw text from the gateway, normalizes
  it (`pdf_text_normalizer.py`) to remove ligatures / hyphenation / irregular
  whitespace, detects on the normalized text, applies the domain
  `dedupe_overlapping`, resolves each kept detection to its pseudonym via a
  document-wide `Pseudonymizer`, records a `Finding`, and tells the gateway to
  write the pseudonym into the text layer. Spans found in normalized text are
  mapped back to the original extracted text before replacement. The gateway also
  tries fallback search variants when the exact text cannot be located. A
  detection whose text can't be found on the page is still reported (and in the
  crosswalk) but not written.
- **Entry points:**
  - Windows: `run.bat` is the intended end-user launcher.
  - macOS/Linux: `run.sh` performs the equivalent setup and launches Streamlit.
  - Both install `uv` if missing, run `uv sync --python 3.12` (which installs the pinned spaCy model along with the other deps — there is no separate model-download step), and start Streamlit on `127.0.0.1`. They are now a two-step flow (setup helper, then `uv sync`).

## Tooling configuration

- `pyproject.toml` defines dependencies, dev dependency group (`ruff`, `pytest`, `codespell`), and ruff rules. Key lint selections: `F`, `E`, `W`, `I`, `D`, `UP`, `SIM`. The `ignore` list is broader than just docstrings — besides `D100`/`D104`/`D105` (module/package/magic-method docstrings), it also disables the pydocstyle rules that conflict with the formatter (`D203`, `D205`, `D213`, `D206`, `D300`), several pycodestyle indentation rules, `E501` (length is the formatter's job), `SIM110`, and `TRY003`. Check the actual `ignore` array before assuming a rule is active.
- `line-length = 88` and `target-version = "py312"`. `requires-python = ">=3.12,<3.14"`.
- `codespell` is configured to skip `uv.lock`, all `.txt`, and all `.csv` files (the master list contains many names that look like typos), and to ignore a short list of words (`ignore-words-list` in `pyproject.toml`) — domain jargon like `master`, and `slave` (flagged only because `CLAUDE.md`'s own prose *about* the disabled `alex.Race` rule mentions the word it's disabling).
- `pytest` is configured with `pythonpath = ["."]` so tests can import from the repo root. Tests live under `tests/` (18 files) and cover the pure domain logic (`pseudonyms`, `rules`, `aliases`, `fuzzy`, `quality`), the `master_list_repository` parser, infrastructure adapters (Presidio detector, PDF gateway, Excel gateway), and presentation-layer formatting; `tests/**` is exempt from `D103` via `per-file-ignores`.
- `pre-commit` is **not** currently declared as a project dependency, and there is **no `.pre-commit-config.yaml`**, so no hooks (pre-commit or otherwise) run locally.
- **CI:** `.github/workflows/ci.yml` runs on every push to `main` and on pull requests — `uv sync --locked`, then `ruff check`, `ruff format --check`, `pytest`, and `codespell`. Since distribution installs straight from `main` (`install.ps1`/`install.sh`), this is what stops a broken `main` from breaking the tool for every user on their next install/update.

## Distribution notes

- The tool is targeted at Windows 11+ end users. `run.bat` is the canonical launch method.
- First run downloads `uv` and installs the Python environment including the `en_core_web_lg` spaCy model (~380 MB), all via `uv sync`. Subsequent starts are fast.
- PyMuPDF (`pymupdf`) is added for PDF support; it is installed automatically by `uv sync`.
- **Sharing the tool:** distribution is via the one-line installers (`install.ps1` for Windows, `install.sh` for macOS/Linux) that download the source from the public GitHub repo and launch `run.bat`/`run.sh`. Each installer prompts for an install location, preserves any local `Names List - Organized.xlsx`, and re-running updates to the latest `main`. For a plain source zip, GitHub's **Download ZIP** button on the repo works too. (The old `package.sh`/`package.bat`/`package.ps1` zip-builder scripts were removed as redundant.)
- Approved for **Internal** data only under IPA's data classification policy; do not use for Confidential or Highly Confidential data. **Caveat:** the name→pseudonym **crosswalk** the tool produces is itself the re-identification key and is **Confidential**. For PDF output the crosswalk is only ever a separate CSV, which must be stored/handled accordingly and never shared alongside the pseudonymized PDF (which stays Internal on its own). For Excel output the crosswalk is embedded as a "Crosswalk" sheet in the pseudonymized workbook by default — so the whole downloaded `.xlsx` file is **Confidential**, not just Internal, and must be stored/handled accordingly.

### Launcher scripts (`run.bat` / `run.sh`) — keep them pure ASCII

- Both launchers must stay **strictly ASCII**. They previously crashed (`'────' is not recognized` / `do was unexpected at this time`) because `chcp 65001` + multi-byte box-drawing/em-dash characters desynchronized cmd.exe's byte-offset file parser. Do **not** reintroduce `chcp 65001` or non-ASCII decoration. Verify after editing: a byte scan should report zero bytes > 127, `run.sh` must keep LF line endings.
- Both use 24-bit truecolor ANSI escapes (`ESC[38;2;R;G;Bm`) for **IPA brand green `#49ac57`** (RGB `73;172;87`); semantic status colors stay distinct (yellow = waiting, red = problem). Truecolor relies on a Windows 11+ console.

## Git attribution

Commits made with assistance from Claude Code should be attributed to the human user only. Do **not** append a `Co-Authored-By: Claude ...` trailer to commit messages, and do not commit under an Anthropic/Claude identity. Ensure `user.name` and `user.email` in this repository point to Brian Thuo’s GitHub identity.
