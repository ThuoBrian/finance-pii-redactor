# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

A Streamlit application that **pseudonymizes** names and organization names in Excel and PDF files locally — each detected name is replaced with a stable ID (e.g. `STF-91345`, `VND-1045`, `FND-7745`) rather than a generic `[PERSON]` label, so the same entity maps to the same ID everywhere and cross-row/cross-file patterns survive for error-checking and fraud monitoring. It uses Microsoft Presidio with a spaCy `en_core_web_lg` model for PII detection, openpyxl for Excel output, and PyMuPDF for PDF text replacement. This is distributed as an offline-capable desktop tool: users double-click `run.bat` (Windows) or `run.sh` (macOS/Linux) to start the local web server and open the browser.

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

- **Run tests:**
  ```bash
  uv run pytest
  ```
  Tests under `tests/` cover the framework-free logic (pseudonym assignment,
  span replacement, master-list parsing) and run without the spaCy model.

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
  the master-list-derived bundle (parsed rows, custom recognizers, detection engine)
  keyed on the workbook's modification time, so unrelated reruns reuse both while
  edits to `data/Names List - Organized.xlsx` still take effect on the next refresh
  without a server restart.
- **`finance_redactor/domain/`** — framework-free core. `entities.py`
  (`PiiDetection`, `Span`, `Finding`, `DetectionSource` = `MODEL`/`MASTER_LIST`) is
  the one representation of a finding all layers speak. `rules.py` holds
  `dedupe_overlapping` (leftmost/longest wins) and `classify_source` (score →
  model/master list). `pseudonyms.py` holds the pseudonymization core:
  `normalize`, the `Pseudonymizer` (master-list lookup + deterministic auto-id
  fallback, accumulating the crosswalk), and `apply_replacements` (dedupe + slice
  spans right-to-left). **This is the single seam where a name becomes an ID.** No
  imports of Presidio/pandas/Streamlit.
- **`finance_redactor/application/`** — use cases over abstract **ports**.
  `ports.py` defines `Protocol`s (`PiiDetector`, `ExcelGateway`, `PdfDocument`,
  `PdfDocumentFactory`) — there is no `TextRedactor`; replacement is done in the
  domain. `redact_excel.py` (`RedactExcelService`) and `redact_pdf.py`
  (`RedactPdfService`) build a `Pseudonymizer` per run, orchestrate domain + ports,
  and return the DTOs in `results.py` plus the run's `crosswalk` (list of
  `Assignment`). This layer imports no concrete framework.
- **`finance_redactor/infrastructure/`** — concrete adapters implementing the
  ports. `detection/` (`PresidioEngine` for `PiiDetector` only — detection, no
  anonymizer; `CustomNameRecognizer`; `recasing.py`; `pdf_text_normalizer.py`),
  `documents/` (`OpenpyxlExcelGateway`, `PyMuPdfDocument`), `names/`
  (`MasterListRepository` + `data/Names List - Organized.xlsx`). Presidio's
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
  expander + guarded CSV download.
- **`finance_redactor/config.py`** — the single source of truth: an immutable
  `Settings` dataclass (language, spaCy model, entities, `categories`
  (category → (prefix, entity_type)), `category_sheets`, `auto_prefixes`,
  `custom_match_score`, default threshold, `master_list_file`). Replaces scattered
  module-level constants and the duplicated `0.9` magic number.
- **Master list:** `data/Names List - Organized.xlsx` — a **top-level, user-owned folder**
  outside the package (resolved by `Settings.names_dir` from `config.py`), so it
  is easy to find/edit and stays separate from the code (and out of git). The
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
  category show in the Advanced settings panel. **Duplicate-name detection:** the
  repository also reports any name that appears under more than one category, and
  the Excel/PDF flows show a warning in Advanced settings because such duplicates
  can create conflicting pseudonyms.
- **Master-list caching:** `MasterListRepository` caches parsed rows keyed by the
  workbook's file modification time, and `app.py` wraps the whole
  repo/recognizers/engine bundle in an `@st.cache_resource` factory keyed on that
  same mtime. The first parse of the full ~26k-row workbook takes a few seconds;
  subsequent Streamlit reruns with an unchanged mtime reuse the cached bundle
  (instead of re-parsing and recompiling recognizer patterns on every widget
  interaction), so widget interactions stay fast while edits to the Excel file
  still take effect immediately on refresh (the new mtime busts the cache).
- **Pseudonyms & crosswalk:** a name in the master list resolves to its curated ID;
  an unknown name gets a deterministic, stable auto-id (`PSN-AUTO-<hash>` /
  `ORG-AUTO-<hash>`, same input → same id across files) and is flagged for review.
  Each run's name→pseudonym crosswalk is shown and downloadable as CSV — it is the
  **re-identification key (Confidential)**; the UI warns against sharing it with the
  pseudonymized file.
- **Excel flow:** the gateway reads the workbook (pandas/openpyxl); selected text
  columns are scanned positionally; detections are kept per cell (`CellFinding`).
  `redact` runs `apply_replacements` per cell against one sheet-wide `Pseudonymizer`
  (so a name is consistent across cells) and the gateway writes the workbook with
  changed cells highlighted yellow.
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

- `pyproject.toml` defines dependencies, dev dependency group (`ruff`, `pytest`, `codespell`, `pre-commit`), and ruff rules. Key lint selections: `F`, `E`, `W`, `I`, `D`, `UP`, `SIM`. The `ignore` list is broader than just docstrings — besides `D100`/`D104`/`D105` (module/package/magic-method docstrings), it also disables the pydocstyle rules that conflict with the formatter (`D203`, `D205`, `D213`, `D206`, `D300`), several pycodestyle indentation rules, `E501` (length is the formatter's job), `SIM110`, and `TRY003`. Check the actual `ignore` array before assuming a rule is active.
- `line-length = 88` and `target-version = "py312"`. `requires-python = ">=3.12,<3.14"`.
- `codespell` is configured to skip `uv.lock`, all `.txt`, and all `.csv` files (the master list contains many names that look like typos), and to ignore the word `master`.
- `pytest` is configured with `pythonpath = ["."]` so tests can import from the repo root. Tests live under `tests/` and cover the pure logic (`pseudonyms`, `master_list_repository`); `tests/**` is exempt from `D103` via `per-file-ignores`.
- `pre-commit` is listed as a dev dependency but there is **no `.pre-commit-config.yaml`**, so no hooks actually run. There is no CI configuration in this repo.

## Distribution notes

- The tool is targeted at Windows 11+ end users. `run.bat` is the canonical launch method.
- First run downloads `uv` and installs the Python environment including the `en_core_web_lg` spaCy model (~380 MB), all via `uv sync`. Subsequent starts are fast.
- PyMuPDF (`pymupdf`) is added for PDF support; it is installed automatically by `uv sync`.
- **Sharing the tool:** distribution is via the one-line installers (`install.ps1` for Windows, `install.sh` for macOS/Linux) that download the source from the public GitHub repo and launch `run.bat`/`run.sh`. Each installer prompts for an install location, preserves any local `Names List - Organized.xlsx`, and re-running updates to the latest `main`. For a plain source zip, GitHub's **Download ZIP** button on the repo works too. (The old `package.sh`/`package.bat`/`package.ps1` zip-builder scripts were removed as redundant.)
- Approved for **Internal** data only under IPA's data classification policy; do not use for Confidential or Highly Confidential data. **Caveat:** the name→pseudonym **crosswalk** the tool produces is itself the re-identification key and is **Confidential** — it must be stored/handled accordingly and never shared alongside the pseudonymized output.

### Launcher scripts (`run.bat` / `run.sh`) — keep them pure ASCII

- Both launchers must stay **strictly ASCII**. They previously crashed (`'────' is not recognized` / `do was unexpected at this time`) because `chcp 65001` + multi-byte box-drawing/em-dash characters desynchronized cmd.exe's byte-offset file parser. Do **not** reintroduce `chcp 65001` or non-ASCII decoration. Verify after editing: a byte scan should report zero bytes > 127, `run.sh` must keep LF line endings.
- Both use 24-bit truecolor ANSI escapes (`ESC[38;2;R;G;Bm`) for **IPA brand green `#49ac57`** (RGB `73;172;87`); semantic status colors stay distinct (yellow = waiting, red = problem). Truecolor relies on a Windows 11+ console.

## Git attribution

Commits made with assistance from Claude Code should be attributed to the human user only. Do **not** append a `Co-Authored-By: Claude ...` trailer to commit messages, and do not commit under an Anthropic/Claude identity. Ensure `user.name` and `user.email` in this repository point to Brian Thuo’s GitHub identity.
