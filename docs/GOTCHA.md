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
- **Symptom:** Error during first-run model download.
- **Cause:** No internet connection or firewall blocking `https://github.com/explosion/spacy-models`.
- **Solution:** Run manually with a working connection:
  ```bash
  uv run python -m spacy download en_core_web_lg
  ```

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

### The app fails to read the master list while it is open in Excel
- **Symptom:** A `PermissionError`, `FileNotFoundError`, or a "failed to read Excel" message appears when the app starts or after refreshing the page.
- **Cause:** Microsoft Excel locks the workbook while it is open, so the app's `pd.read_excel` call cannot access it.
- **Solution:** Save and close the Excel workbook before launching or refreshing the app. You can edit the workbook, save it, close Excel, then refresh the browser to pick up the changes.

## Code and dependencies

### Presidio `AnalysisExplanation` keyword arguments changed across versions
- **Symptom:** `TypeError: AnalysisExplanation.__init__() got an unexpected keyword argument ...`.
- **Cause:** Presidio changed the constructor signature between releases.
- **Solution:** Use `inspect.signature(AnalysisExplanation.__init__)` to verify the current signature, or pin `presidio-analyzer` to the version declared in `pyproject.toml`. The current custom recognizer uses `recognizer`, `original_score`, `pattern_name`, `pattern`, and `textual_explanation`.

### `app.py` cannot import from `redactor`
- **Symptom:** `ModuleNotFoundError: No module named 'redactor'`.
- **Cause:** Running `python app.py` directly instead of via `streamlit run app.py`, or not running from the project root.
- **Solution:** Always run from the repository root with `uv run streamlit run app.py`. If you need a standalone script, adjust `PYTHONPATH` first.


### A name gets a flagged `*-AUTO-*` code instead of my curated ID
- **Symptom:** A name shows up in the crosswalk as e.g. `PSN-AUTO-3F9A1` with **Flagged = yes**, not the `STF-12345` you expected.
- **Cause:** The name was detected but is **not in the master list with a curated `Internal ID`** — either it is missing, the `Internal ID` column is blank, or the spelling/spacing in the master list does not match the document text. Matching is case-insensitive and whitespace-normalized, but otherwise exact.
- **Solution:** Add the name to `data/Names List - Organized.xlsx` with the correct sheet/category and a non-blank `Internal ID`, using the exact text as it appears in the data, then refresh the app in the browser. Edits to the master list take effect on the next Streamlit rerun (the Excel workbook is reloaded each time; only the heavy spaCy model is cached). Auto-codes are deterministic (the same unknown name always yields the same code, even across files), so existing outputs stay consistent until you re-run.

### Long multi-word names are not matched
- **Symptom:** A phrase like `Kenya Commercial Bank` is not detected even though it is in the master list.
- **Cause:** The recognizer uses whole-phrase word-boundary matching (`\b...\b`). If the cell contains `KCB Bank` but the master list `name` is `Kenya Commercial Bank`, it will not match.
- **Solution:** Add the exact phrases that appear in your data (one row each), or add shorter canonical forms.

### A legacy name in the old `person.txt` had an ID appended (`Name - 90863`)
- **Symptom:** After migrating, a name that previously "never matched" now does.
- **Cause:** The old plain-text lists sometimes embedded an ID in the name itself (`Aaron Elijah Mutungi - 90863`). The recognizer searched for the *whole string* including ` - 90863`, so it almost never matched real document text — a latent bug.
- **Solution:** The app now reads `data/Names List - Organized.xlsx` directly and strips trailing ` - <anything>` from `Staff` names, using the `Internal ID` column as the curated ID. If you still have legacy `.txt` lists, update `scripts/migrate_to_master_list.py` to write to the Excel workbook, or migrate manually.

### Mixed-language text causes spaCy NER to miss names
- **Symptom:** English names are detected but non-English names are not.
- **Cause:** `en_core_web_lg` is an English-only model.
- **Solution:** Add the non-English names to the master list (this is the recommended way, and they get curated IDs). For broader language support, a language-specific spaCy model or a multilingual transformer would be required, but that increases setup size and runtime cost.

### ALL-CAPS names and acronym false positives
- **Symptom (fixed):** A fully-uppercase name like `MARY WANJIRU` used to be missed.
- **Cause:** `en_core_web_lg` is trained on mixed-case text and does not tag ALL-CAPS tokens as names. The custom recognizer is case-insensitive but only catches master-list names.
- **Solution:** `PresidioEngine.analyze` now runs a second detection pass on a length-preserving recased copy of the text (`finance_redactor/infrastructure/detection/recasing.py` title-cases all-caps tokens, e.g. `MARY` -> `Mary`), then unions and de-duplicates with the original pass. Spans map back to the original text because recasing preserves length.
- **Side effect:** standalone all-caps acronyms (e.g. `USD`, `KCB`) are recased in the *copy* and may occasionally be flagged as organizations. These are reviewable false positives, not errors — confirm in the detection details / crosswalk before downloading. The original-cased pass is unchanged, so this only ever *adds* detections.

### PDF text is not replaced, or two codes stack on the same area
- **Symptom:** Some PDF text keeps the original name, or the output shows two ID codes stacked on the same spot.
- **Cause 1:** The PDF page is a scanned image and contains no selectable text layer.
- **Solution 1:** The tool only processes selectable PDF text. Scanned PDFs require OCR first.
- **Cause 2:** The same span was detected by both the spaCy model and the master list, or a name appears under two categories.
- **Solution 2:** The code deduplicates overlapping spans (leftmost/longest wins), but a name listed under two categories (e.g. Vendor *and* Funder) can still conflict. Keep each name in a single category.
- **Cause 3:** A detected substring cannot be located on the page with `page.search_for()`, e.g., due to hyphenation or complex layout encoding.
- **Solution 3:** The occurrence is reported in the detection details and the crosswalk but not written into the page. Manually review the output.

## Testing and linting

### `ruff` flags `E402` for the Streamlit context guard import
- **Symptom:** `Module level import not at top of file` on the `streamlit.runtime.scriptrunner` import.
- **Cause:** The import is deliberately placed at the bottom of `app.py` to avoid running `_main()` when the module is imported by tests or linters.
- **Solution:** Keep the `# noqa: E402` comment on that import line.

### `codespell` flags HTML variable names like `thead` or `ws`
- **Symptom:** False-positive spelling corrections in string literals.
- **Cause:** `codespell` treats short tokens as typos.
- **Solution:** Add the tokens to `ignore-words-list` in `pyproject.toml`.
