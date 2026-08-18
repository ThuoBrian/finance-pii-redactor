# GOTCHA.md

This file records known errors, edge cases, and their solutions when developing or running the Finance PII Redactor.

## Environment and setup

### `uv` is not found when running `run.sh` or `run.bat`

- **Symptom:** "Installing uv (one-time)..." fails, or `uv: command not found`.
- **Cause:** `uv` is downloaded to `~/.local/bin` on Unix or via PowerShell on Windows, but the session PATH may not include it.
- **Solution:**
  - Unix: `export PATH="$HOME/.local/bin:$PATH"` and re-run `./run.sh`.
  - Windows: close and reopen the terminal, or run `run.bat` again so it refreshes PATH.

### `en_core_web_lg` spaCy model fails to download

- **Symptom:** `uv sync` fails while installing `en_core_web_lg`, or hangs during first-run setup.
- **Cause:** No internet connection or firewall blocking `https://github.com/explosion/spacy-models`. The model is a normal pinned dependency (a wheel URL in `pyproject.toml`) installed by `uv sync` — there is no separate `spacy download` step to fall back to.
- **Solution:** Get a working connection to `https://github.com/explosion/spacy-models` (check firewall/proxy rules), then re-run `uv sync --python 3.12`. Running `python -m spacy download en_core_web_lg` instead does **not** fix a `uv sync` failure — it installs the model outside `uv`'s dependency resolution, out of sync with the pinned version in `pyproject.toml`.

### `run.bat` crashes with `'────' is not recognized` or `do was unexpected at this time`

- **Symptom:** Double-clicking `run.bat` prints errors like `'────────────' is not recognized as an internal or external command` and/or `do was unexpected at this time`, instead of showing the banner.
- **Cause:** The combination of `chcp 65001` (switch console to UTF-8) **and** multi-byte characters in the script — box-drawing rules (`─`, 3 bytes each in UTF-8) or em-dashes (`—`). cmd.exe tracks its read position in a batch file by **byte offset**; the multi-byte characters desynchronize that pointer, so cmd jumps into the middle of a line and tries to execute fragments like `────` as commands.
- **Solution:** Keep `run.bat` (and `run.sh`) **strictly ASCII** and do **not** use `chcp 65001`. Use plain ASCII for decoration (`--`, `==`, `+`) and 24-bit truecolor ANSI escapes (`ESC[38;2;R;G;Bm`) for colour — those are ASCII digits and render on Windows 11+ consoles. Verify after editing:

  ```powershell
  $b=[IO.File]::ReadAllBytes('run.bat'); ($b | ? { $_ -gt 127 }).Count   # must be 0
  ```

  For `run.sh`, also confirm it keeps **LF** (not CRLF) line endings, or the `#!/usr/bin/env bash` shebang breaks on Unix.

### Streamlit fails to start because port 8501 is in use

- **Symptom:** `Address already in use`.
- **Cause:** Another Streamlit instance is running.
- **Solution:** Stop the other instance, or launch on a different port:

  ```bash
  uv run streamlit run app.py --server.address=127.0.0.1 --server.port 8502
  ```

### The same name gets a different code for different teammates

- **Symptom:** A name (e.g. `Brian Thuo`) pseudonymizes to `STF-91345` on your machine but to a different code — or a flagged `STF-AUTO-*` code — on a colleague's machine, even though you're both running the same version of the tool.
- **Cause:** By default, each installation reads its master list from a `data/` folder next to that installation's own copy of the code (`Settings.names_dir` in `finance_redactor/config.py`), and nothing seeds or syncs it from anywhere else — updating (a fresh ZIP download or `git pull`) replaces the code folder and does not carry a locally-kept `Names List - Organized.xlsx` forward on its own, so it must be backed up and restored by hand around an update if you're not on a shared location. Two people each maintaining their own independent copy of `Names List - Organized.xlsx` will therefore disagree on a name unless the `Internal ID` they assigned it happens to match. This is expected: each machine's list is genuinely separate data, not a bug in the pseudonymization logic.
- **Solution:** Point every teammate's install at **one shared, access-controlled copy** of the workbook by setting the `FPR_MASTER_LIST_DIR` environment variable to that shared location on each machine, then restart the app. See **[Sharing one master list across a team](../data/README.md#sharing-one-master-list-across-a-team)** in `data/README.md` for the exact steps and the compliance note (the shared location must meet the same Confidential-data handling rules as a local copy). Unset (the default), behavior is unchanged — the local `data/` folder next to the code is used, as before.

### The app fails to read the master list while it is open in Excel

- **Symptom:** A `PermissionError`, `FileNotFoundError`, or a "failed to read Excel" message appears when the app starts or after refreshing the page.
- **Cause:** Microsoft Excel locks the workbook while it is open, so the app's `pd.read_excel` call cannot access it.
- **Solution:** Save and close the Excel workbook before launching or refreshing the app. You can edit the workbook, save it, close Excel, then refresh the browser to pick up the changes.

## Code and dependencies

### Presidio `AnalysisExplanation` keyword arguments changed across versions

- **Symptom:** `TypeError: AnalysisExplanation.__init__() got an unexpected keyword argument ...`.
- **Cause:** Presidio changed the constructor signature between releases.
- **Solution:** Use `inspect.signature(AnalysisExplanation.__init__)` to verify the current signature, or pin `presidio-analyzer` to the version declared in `pyproject.toml`. The current custom recognizer uses `recognizer`, `original_score`, `pattern_name`, `pattern`, and `textual_explanation`.

### `app.py` cannot import from `finance_redactor`

- **Symptom:** `ModuleNotFoundError: No module named 'finance_redactor'`.
- **Cause:** Running `python app.py` directly instead of via `streamlit run app.py`, or not running from the project root.
- **Solution:** Always run from the repository root with `uv run streamlit run app.py`. If you need a standalone script, adjust `PYTHONPATH` first.

### A name gets a flagged `*-AUTO-*` code instead of my curated ID

- **Symptom:** A name shows up in the crosswalk as e.g. `PSN-AUTO-3F9A1` with **Flagged = yes**, not the `STF-12345` you expected.
- **Cause:** The name was detected but is **not in the master list with a curated `Internal ID`** — either it is missing, the `Internal ID` column is blank, or the spelling/spacing in the master list does not match the document text. Matching is case-insensitive and whitespace-normalized, and **alias-aware**: organization suffix equivalents (`Ltd`=`Limited`, `Inc`=`Incorporated`, `Corp`=`Corporation`, `Co`=`Company`; `LLC`/`PLC` period-tolerant) and `&`↔`and` swaps are matched automatically, so `Acme Ltd` in the list covers `Acme Limited` in a document. Spelling, word order, and middle initials are **not** matched.
- **Solution:** Add the name to `data/Names List - Organized.xlsx` with the correct sheet/category and a non-blank `Internal ID`, using the exact text as it appears in the data, then refresh the app in the browser. Edits to the master list take effect on the next Streamlit rerun (the Excel workbook is reloaded each time; only the heavy spaCy model is cached). Auto-codes are deterministic (the same unknown name always yields the same code, even across files), so existing outputs stay consistent until you re-run. Check the crosswalk's **Possible match** column first — if the flagged name is a near-miss typo of a curated name (e.g. document `Micheal Mugo` vs. master-list `Michael Mugo`), it already names the likely intended match as a reviewer hint (`finance_redactor/domain/fuzzy.py`); this is advisory only and is never auto-applied, so you still need to fix the name (in your data or the master list) and re-run.

### Long multi-word names are not matched

- **Symptom:** A phrase like `Kenya Commercial Bank` is not detected even though it is in the master list.
- **Cause:** The recognizer matches whole phrases only (a boundary check requires a non-word character, or start/end of text, on either side of a match). It matches organization-suffix equivalents (`Ltd`/`Limited`, `Inc`/`Incorporated`, `Corp`/`Corporation`, `Co`/`Company`) and `&`/`and` swaps automatically, but it does **not** match acronyms or reworded forms. If the cell contains `KCB Bank` but the master list `name` is `Kenya Commercial Bank`, it will not match.
- **Solution:** Add the exact phrases that appear in your data (one row each), or add shorter canonical forms.

### A name followed by a bare hyphen resolves to a flagged auto-id

- **Symptom (fixed):** A memo like `Field advance to Brian Thuo - Kakamega project supervision` redacted to `Field advance to PSN-AUTO-0BA3D project supervision` instead of the curated `STF-<id>` — and the trailing location (`Kakamega`) disappeared from the output along with the name.
- **Cause:** spaCy's NER model sometimes tags a hyphen-joined trailing phrase as part of the same PERSON entity (`"Brian Thuo - Kakamega"` as one span), which overlaps and outspans the exact master-list match on the name alone (`"Brian Thuo"`). The old dedupe rule was pure leftmost/longest with no regard for detection source, so the longer model guess won even though the shorter span was an exact curated match — and the longer string doesn't exist in the master list, so it fell through to a flagged auto-id.
- **Solution:** `dedupe_overlapping` (`finance_redactor/domain/rules.py`) now breaks overlaps by source first: a master-list-sourced detection always wins over an overlapping model-sourced one, regardless of which span is longer. Same-source overlaps still use leftmost/longest as before.
- **Workaround if you hit a similar case elsewhere:** rephrase without a bare hyphen (e.g. `Brian Thuo (Kakamega)`, `Brian Thuo, Kakamega`, or an em dash) to stop the model fusing the two into one entity — though this should no longer be necessary for names that are in the master list.

### The Advanced settings panel shows master-list data-quality warnings

- **Symptom:** Yellow or blue boxes appear under **Advanced settings** with titles like "Cross-category duplicate", "Conflicting IDs", "Reused Internal ID", or "Blank Internal ID".
- **Cause:** On load, `MasterListRepository.quality_report()` scans the workbook and surfaces five issue kinds: a name under more than one category (warning), the same name in one category with two different `Internal ID`s (warning), one `Internal ID` shared by two different names in a category (warning), a name with a blank `Internal ID` (info — supported, gets a flagged auto-code), and a single-token name that's also an ordinary English word (info — e.g. a funder literally named "Across"; every plain-English occurrence of that word gets detected too). Exact duplicate rows (same name and same ID) are benign and are **not** flagged.
- **Solution:** Fix the offending rows in `data/Names List - Organized.xlsx` (merge duplicates, give each name a unique ID, fill in blank IDs), save and close the workbook, and refresh the page. The warnings clear once the workbook is clean. These are advisories — the app still runs with a dirty list, but the IDs it emits may be ambiguous, so fixing them keeps pseudonyms trustworthy.

### A legacy name in the old `person.txt` had an ID appended (`Name - 90863`)

- **Symptom:** After migrating, a name that previously "never matched" now does.
- **Cause:** The old plain-text lists sometimes embedded an ID in the name itself (`Aaron Elijah Mutungi - 90863`). The recognizer searched for the *whole string* including ` - 90863`, so it almost never matched real document text — a latent bug.
- **Solution:** The app now reads `data/Names List - Organized.xlsx` directly and strips trailing ` - <anything>` from names on every sheet (Staff, Vendors, Funders), using the `Internal ID` column as the curated ID. If you still have legacy `.txt` lists, update `scripts/migrate_to_master_list.py` to write to the Excel workbook, or migrate manually.

### Mixed-language text causes spaCy NER to miss names

- **Symptom:** English names are detected but non-English names are not.
- **Cause:** `en_core_web_lg` is an English-only model.
- **Solution:** Add the non-English names to the master list (this is the recommended way, and they get curated IDs). For broader language support, a language-specific spaCy model or a multilingual transformer would be required, but that increases setup size and runtime cost.

### ALL-CAPS names and acronym false positives

- **Symptom (fixed):** A fully-uppercase name like `MARY WANJIRU` used to be missed.
- **Cause:** `en_core_web_lg` is trained on mixed-case text and does not tag ALL-CAPS tokens as names. The custom recognizer is case-insensitive but only catches master-list names.
- **Solution:** `PresidioEngine.analyze` now runs a second detection pass on a length-preserving recased copy of the text (`finance_redactor/infrastructure/detection/recasing.py` title-cases all-caps tokens, e.g. `MARY` -> `Mary`), then unions and de-duplicates with the original pass. Spans map back to the original text because recasing preserves length.
- **Side effect:** standalone all-caps acronyms (e.g. `USD`, `KCB`) are recased in the *copy* and may occasionally be flagged as organizations. These are reviewable false positives, not errors — confirm in the detection details / crosswalk before downloading. The original-cased pass is unchanged, so this only ever *adds* detections.

### PDF text is not replaced, or organization names are missed in PDFs

- **Symptom:** Some names in a PDF are detected but not replaced, or organization names are missing from the findings entirely.
- **Cause 1:** The PDF page is a scanned image and contains no selectable text layer.
- **Solution 1:** The tool only processes selectable PDF text. Scanned PDFs require OCR first.
- **Cause 2:** The same span was detected by both the spaCy model and the master list, or a name appears under two categories.
- **Solution 2:** The code deduplicates overlapping spans (master-list source wins over an overlapping model source regardless of length; leftmost/longest breaks ties within the same source — see the entry above on a name followed by a bare hyphen), but a name listed under two categories (e.g. Vendor *and* Funder) can still conflict. Keep each name in a single category.
- **Cause 3:** PyMuPDF extracts text with artifacts that break exact matching — typographic ligatures (`ﬁ` instead of `fi`), line-break hyphenation (`Acme Sup-\nplies`), and irregular whitespace. The master-list recognizer and spaCy see a different string than the one in the master list.
- **Solution 3:** The PDF flow now normalizes extracted text before detection: ligatures are expanded, soft line-break hyphens are removed, and whitespace is collapsed. Detection spans are mapped back to the original extracted text, and `page.search_for()` tries a small set of fallback variants (whitespace-collapsed, punctuation-stripped, `&`/`and` swapped, common suffix stripped) when the exact text is not found. The occurrence is still reported in the detection details and crosswalk even if it cannot be written.

### A name inside a Word text box, SmartArt, or embedded object is not detected

- **Symptom:** A name typed into a Word text box, SmartArt diagram, or embedded object is left untouched, even though the same name elsewhere in the body/table/header is pseudonymized correctly.
- **Cause:** `PythonDocxDocument` (`finance_redactor/infrastructure/documents/docx_gateway.py`) enumerates paragraphs from the document body, table cells (including nested tables), and headers/footers - the same "only the selectable text layer is processed" limitation as scanned PDFs, just for a different Word-specific reason: text boxes/SmartArt/embedded objects store their text outside `paragraph.runs`, so python-docx's normal paragraph walk never sees it.
- **Solution:** Retype that text as normal paragraph text, or manually redact it. Widening the gateway to also reach into text-box/SmartArt XML would be a larger follow-up if this becomes common.

### Why doesn't the tool touch dates/times?

- **Symptom:** A memo date like `Jan-26` is left as plain text instead of being pseudonymized, even though Presidio can detect a `DATE_TIME` entity type.
- **Cause:** This is deliberate, not a gap. `Settings.supported_entities` and `Settings.auto_prefixes` (`finance_redactor/config.py`) intentionally list only name/organization/email entity types (`PERSON`, `ORGANIZATION`, `EMAIL_ADDRESS`). Dates and times aren't the PII this tool exists to protect, and turning them into fake IDs would be noise, not redaction. Adding one carelessly is also a silent risk: any entity type missing from `auto_prefixes` falls back to `entity_type[:3].upper()` in `Pseudonymizer._auto_pseudonym` (`domain/pseudonyms.py`) instead of raising an error — so a `DATE_TIME` entity would quietly mint junk ids like `DAT-AUTO-4D8F3` rather than failing loudly.
- **Solution:** Don't add `DATE_TIME` (or other non-name entity types) to `supported_entities`/`auto_prefixes`. `tests/test_config.py::test_date_time_is_never_a_supported_entity` guards against a regression here.

## Testing and linting

### `ruff` flags `E402` for the Streamlit context guard import

- **Symptom:** `Module level import not at top of file` on the `streamlit.runtime.scriptrunner` import.
- **Cause:** The import is deliberately placed at the bottom of `app.py` to avoid running `_main()` when the module is imported by tests or linters.
- **Solution:** Keep the `# noqa: E402` comment on that import line.

### `codespell` flags HTML variable names like `thead` or `ws`

- **Symptom:** False-positive spelling corrections in string literals.
- **Cause:** `codespell` treats short tokens as typos.
- **Solution:** Add the tokens to `ignore-words-list` in `pyproject.toml`.
