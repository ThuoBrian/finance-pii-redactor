# Improvement plan

Findings from the 2026-11-15 project review (architecture, tests, UX, and
redaction guarantees). Work through the tiers in order; every item lists the
files to touch and how to verify it.

Scope check before starting: the test suite is green — 460 passed, 1 skipped,
96.8% coverage under `pyproject.toml`'s 80% floor. Keep it that way; several
items below add a test, not just a fix.

## P0 — Redaction-guarantee gaps

These break the tool's core promise ("nothing is left showing"). Names can
survive redaction with no signal to the user.

### 1. PDF: a "detected but not located" term is reported as redacted

- **Where:**
  `finance_redactor/application/redact_pdf.py:583-591` records the Finding and
  ordinal before the gateway searches.
  `finance_redactor/infrastructure/documents/pdf_gateway.py:359` —
  `if not rects: continue` drops the term with no counter.
  `finance_redactor/presentation/presenters.py:644` then says
  "Every detected term is hidden."
- **Failure:** the scan detects a span on the normalized text, but
  `page.search_for` fails on every candidate variant (ligatures, OCR spelling
  drift, encoding). Nothing is blacked out, yet the user is told all is done.
- **Fix:** return a "not located" count/list from the gateway as part of the
  scan result; surface it in the Review step as its own warning; make the
  "Every detected term is hidden" reassurance display only when the count is 0.
- **Verify:** a test that crafts a detection which fails all variants
 (e.g. ligature text through `_search_variants`) and asserts the warning
 appears and the reassurance doesn't.

### 2. DOCX: first-page/even-page headers and footers are never scanned

- **Where:** `finance_redactor/infrastructure/documents/docx_gateway.py:195-203`
  iterates only `section.header` and `section.footer`.
- **Failure:** "Different first page" is a common Word setting, and a name in
  `first_page_header`/`even_page_header` (and the footers) ships intact.
- **Fix:** add the four extra parts per section to the loop. The dedupe by
  `id(header_or_footer.part)` still applies — several sections often share a
  part.
- **Verify:** a test docx with a name in the first-page header; assert it
  appears in the scan before the fix and is redacted after.

### 3. DOCX: footnotes, endnotes, comments, and track-changes survive

- **Where:** `finance_redactor/infrastructure/documents/docx_gateway.py:57-65,
  179-204, 243-245`, and the docstring at `:178` which claims "notes" are
  covered.
- **Failure:**
  - `paragraph.runs` returns only direct `w:r` children — runs inside
    `w:ins` (tracked insertions) are invisible to detection and replacement;
    `w:del`/`w:delText` deleted text stays in the saved file.
  - `word/comments.xml` is never scanned: comment text, the comment author's
    name, and the anchor survive.
  - Footnotes/endnotes parts are never scanned.
- **Fix (in order of value):** strip or flatten revisions on save; scan
  comments.xml and remove the part (comment authors alone are PII); scan
  footnotes/endnotes parts. Then fix the `:178` docstring to say what's
  actually covered.
- **Verify:** one test part per case (insertion, deletion, comment, footnote);
  open the output and assert the strings are gone.

### 4. Master-list rows silently dropped on Category mismatch

- **Where:** `finance_redactor/infrastructure/names/master_list_repository.py:411-413`
  (`if category != expected_category: continue`).
- **Failure:** a blank Category cell, a missing "Category" column, or a
  wording difference ("Employee" vs "STAFF") drops the row. The name is then
  never detected — under-redaction with no signal. The quality report at
  `:208-373` checks duplicates/blank IDs/common words but not this.
- **Fix:** collect dropped rows during `_parse` and emit them as quality
  findings ("N rows skipped because their Category cell doesn't match", with
  the names). Show in the sidebar master-list card alongside the existing
  findings.
- **Verify:** a workbook with one valid and one mismatched row; assert the
  valid one loads, the other is reported, and the count matches.

### 5. Corrupt master-list workbook crashes the app

- **Where:** `finance_redactor/infrastructure/names/master_list_repository.py:381-385`
  catches only `FileNotFoundError`; `app.py:107-138` guards only the `stat()`.
- **Failure:** a truncated, corrupt, or password-protected workbook raises
  `zipfile.BadZipFile` / `ValueError` straight through `_get_master_list_bundle`
  — the user gets a raw Streamlit traceback instead of the "0 names" dialog.
- **Fix:** widen the catch to `(FileNotFoundError, zipfile.BadZipFile,
  ValueError, OSError)` and route it into the same degraded path the
  missing-file case uses.
- **Verify:** a truncated xlsx fixture; assert the 0-names dialog appears and
  the app stays usable.

## P1 — Data loss and dead ends in the flow

### 6. Same-filename re-upload reuses the stale scan

- **Where:** `finance_redactor/presentation/session.py:54-58` treats a file as
  new only when `uploaded.name` or `file_type` changes.
- **Failure:** editing "report.pdf" and re-uploading under the same name
  silently shows the previous scan, review table, and redacted output. The
  user can ship output built from the wrong document — the worst failure mode
  this tool has.
- **Fix:** extend the identity check to size, or a hash of the first KB of
  `uploaded.getbuffer()`.

### 7. Going Back to Options and re-redacting destroys the whole review

- **Where:** `finance_redactor/presentation/pdf_view.py:216-220`,
  `excel_view.py:200-205`, `docx_view.py:150-156` — re-clicking "Redact my
  file" resets the applied-exclusion set to empty and overwrites
  `*_all_findings`.
- **Failure:** changing one option (e.g. the threshold) costs the entire
  review pass, with no warning.
- **Fix options:** carry over exclusions whose terms still resolve after the
  new scan (the `merge_findings` machinery in `presenters.py:556-567` already
  supports untickable rows across scans); or at minimum warn before
  discarding. Carrying over is the right behavior.

### 8. Excel Download step offers no download when zero findings

- **Where:** `finance_redactor/presentation/excel_view.py:320-323` shows only
  "Nothing was detected, so the file is already clean" and returns — no button.
- **Failure:** the user cannot get their output workbook at all (relevant when
  they deselected tabs expecting a trimmed file). PDF and Word always offer a
  download.
- **Fix:** always build and offer the download; keep the info message.

### 9. "Start over" wipes everything with no confirmation

- **Where:** `finance_redactor/app.py:167-170`.
- **Failure:** one misclick discards a completed review; "Close the app" does
  confirm, this doesn't.
- **Fix:** two-step confirm like `presentation/shutdown.py:21-52`, mentioning
  that findings and downloads are lost.

### 10. Options step has no Back button

- **Where:** the wizard's Back control first appears from the Review step
  (`excel_view.py:292`, `pdf_view.py:342`, `docx_view.py:237`).
- **Fix:** render Back on the Options step too (the folded file expander is
  the only non-destructive route back today).

## P2 — Release and reach

### 11. Intel Macs cannot install the tool

- **Where:** `uv.lock` pins `onnxruntime` 1.31.0, which ships **no macOS
  x86_64 wheel**. `run.sh:108` and `run.bat:52` run `uv sync`, which fails on
  an Intel Mac with "no wheel for the current platform" (verified locally on
  this machine). CI (`.github/workflows/ci.yml:14`) runs only on
  `ubuntu-latest`, so nothing catches it.
- **Fix options (pick one):**
  - Pin `onnxruntime<1.21` (recent versions with Intel-Mac wheels), or
  - Add uv's suggested `tool.uv.required-environments` guard
    (`sys_platform == 'darwin' and platform_machine == 'x86_64'` excluded) and
    make `install.sh`/`run.sh` detect Intel Macs and print a plain-English
    "not supported on this Mac" instead of a uv traceback.
- **Also:** add a CI job on a macOS runner (or at minimum `uv lock --check`
  under a macOS platform matrix) so a future dep pin can't silently break
  macOS again. The README and install.sh both advertise macOS support.

### 12. .xls files pass the upload filter but crash

- **Where:** `app.py:193` accepts `"xls"`; `finance_redactor/infrastructure/documents/excel_gateway.py:44-47`
  forces `engine="openpyxl"`, which cannot open `.xls`.
- **Fix:** either read `.xls` honestly or refuse it at upload with the
  "unsupported" message (`app.py:259` already has the shape).

### 13. Phone numbers are not covered at all

- **Where:** `finance_redactor/config.py:151-160` (`fixed_masks`) and
  `:185-191` (`supported_entities`) omit `PHONE_NUMBER`; Presidio ships a
  PHONE_NUMBER recognizer that is deliberately not enabled.
- **Fix:** enable it under a new fixed mask (e.g. `[PHONE]`) and add it to the
  README's "What gets redacted" list. Watch the false-positive rate — start
  with the same "check the review table" framing as names.

### 14. Partial names never match; accent handling differs between paths

- **Where:** `finance_redactor/infrastructure/detection/custom_recognizer.py:111-114`
  enforces hard word boundaries, so "Wanjiru" never matches the list entry
  "Mary Wanjiru". `:73,105` lowercases but never accent-folds, while the
  custom-words path does fold (`domain/custom_words.py:41-47`) — so "Jose
  Garcia" (document typo) finds nothing but "José García" on the list would
  resolve if it got there.
- **Fix:** at minimum, make master-list matching accent-insensitive so both
  paths behave the same. Surname-only matching is a design decision — the docs
  currently argue against initials/suffixes; if it stays off, say so in the
  troubleshooting doc.

### 15. Mixed text+image PDF pages are treated as text-only

- **Where:** `finance_redactor/application/redact_pdf.py:384` —
  `scanned = not has_text and ...`.
- **Failure:** a page with boilerplate text and a scanned image of the real
  content is never OCR'd; names visible only in the image survive unless
  "Black out images" happens to be on.
- **Fix:** OCR such pages too, or at minimum list them in the scanned-pages
  warning so the user knows an image went through unexamined.

### 16. No size or scaling guards

- **Where:** `excel_gateway.py:45` loads all sheets plus a second full openpyxl
  copy (`:49-60`); `redact_pdf.py:367-399` OCRs serially with no page cap.
- **Fix (minimal for now):** report an estimate up front ("200 scanned pages,
  about 7 minutes"), and add an early-abort or page-count warning for very
  large jobs. Full chunking can wait — the Excel unique-value cache
  (`redact_excel.py:70-88`) is already a good scaling device.

### 17. `_LEGACY_SUFFIX` mangles legitimate names

- **Where:** `finance_redactor/infrastructure/names/master_list_repository.py:42-43,
  427-433` — the regex `\s+-\s+.*$` turns "Oxfam - Kenya" into "Oxfam".
- **Failure:** the full form never matches, and two collapsed rows can trip
  the "conflicting IDs" quality warning, pointing the operator at the wrong
  rows.
- **Fix:** only strip the suffix when it matches the sanctioned suffix list
  (if the legacy format warrants it), or log every strip as a quality finding.

## P3 — Interaction polish (one-liners)

| # | Item | Where |
| --- | --- | --- |
| 18 | "Where found" tables leak raw enums (`EMAIL_ADDRESS`, `master_list`, `model`); pass them through humanization | `presenters.py:186-202, 394-405` |
| 19 | Review tab badge counts only model guesses — "Review (2 to check)" beside "57 terms found" reads as a 30× smaller job | `presenters.py:604-621` |
| 20 | "Hide in output?" defaulted to True is a double negative; consider "Keep in file?" | `exclusion_view.py:230-231` |
| 21 | Zero findings leaves the Review tab completely blank | `exclusion_view.py:101-102` |
| 22 | PDF download: empty crosswalk renders nothing (no "no mapping" note) | `crosswalk_view.py:76-77` |
| 23 | Tracker says "Set options", page says "Options" | `steps.py:14` vs `pdf_view.py:110` etc. |
| 24 | Dark mode is forced for the logo's sake; light-mode users have no choice | `.streamlit/config.toml:4-9` |
| 25 | Threshold slider allows values its own tooltip forbids (> 0.90); clamp it | `excel_view.py:152-159` |
| 26 | `run.sh` says "Ctrl+C to stop", Windows says "close the window"; neither mentions the in-app "Close the app" button | `run.sh:79`, `run.bat:139` |
| 27 | Options caption comma-joins every tab name — a wall of names at 30 sheets; summarize ("First 5 of 12 tabs…") | `excel_view.py:110-113` |
| 28 | Only Excel shows a live progress bar; PDF/Word scans (especially OCR) can look frozen | `excel_view.py:179-199` vs `pdf_view.py:170-191` |
| 29 | "Skip for now" on the 0-names dialog re-prompts every launch; remember the dismissal | `master_list_setup.py:66-78` |
| 30 | Tab-preview caps at 500 rows with only a caption to tell you more matches lie beyond | `presenters.py:91`, `excel_view.py:251-257` |

## UI de-clutter

The user's own observation: the UI feels crowded. The crowding is not spread
evenly — it concentrates in the Review step and the Download cards. The theme
of every fix below is the same: **one screen = one job**. Review = "what did
we find"; Download = "how to share it"; Options = "what to scan".

### U1. Review step: move the sharing notes to Download

- **Where:** `finance_redactor/presentation/pdf_view.py:260-278` (the
  "Before you share this PDF" box) and `pdf_view.py:281` (column picker),
  `pdf_view.py:283` (words box); `excel_view.py:312` already does exclusion
  warnings at Download — copy that discipline.
- **Change:** the "Before you share" box is about the downloaded file, not
  about ticking rows — move it to the Download step (it currently duplicates
  what Download's captions say again anyway). Review keeps one caption and
  the tabs. The exception: the scanned-pages warning genuinely changes how
  you review (check the OCR pages) — keep that one in Review.

### U2. Review step: fold the rare-path controls

- **Where:** the table-column picker (`pdf_view.py:352-375`) and the
  words-to-add box (`words_view.py`). The words box was deliberately moved
  from Options to Review (commit `f0754c1`) — keep it in Review, just not at
  full width at the top.
- **Change:** put both under one collapsed expander, e.g.
  **"Add something the tool missed"**, with the column picker inside it only
  when a table was found. Default collapsed; the caption can say
  "(most files need nothing here)". The scan/redact split
  (`pdf_view.py:308-340`) already makes applying these cheap, so this costs
  nothing functionally.

### U3. Review step: cut the fourth tab

- **Where:** `pdf_view.py:300-306` and `excel_view.py:266-275` — the
  "Where found" occurrences tab is a raw detections table (page/cell/entity/
  score/source), overlapping what the Review editor's **Show details** toggle
  already reveals (`exclusion_view.py:173-177`).
- **Change:** merge into the editor's details view or an expander at the
  bottom of Review. Three tabs become two (Review, Preview) plus Mapping,
  which for PDF is the only place mapping belongs.

### U4. Preview: one table, with a compare toggle

- **Where:** `finance_redactor/presentation/excel_view.py:245-250` —
  Redacted and Original stacked, each full width.
- **Change:** default to the **Redacted** table only, with a
  "Compare with original" toggle that switches (not stacks) the view. Rows
  line up 1:1 today, so switching loses nothing. Halves the scroll.

### U5. Options: stop rendering one multiselect per tab

- **Where:** `finance_redactor/presentation/excel_view.py:140-151` — with N
  tabs, N stacked "Columns to scan: X" multiselects; plus the caption at
  `:110-113` comma-joins every tab name.
- **Change:** one selectbox "Which tab's columns?" + a single multiselect
  that writes back to `excel_cols_{name}`. The caption shows the first two
  tab names and "+ 8 more". A 10-tab workbook goes from ~10 rows of widgets
  to 2.

### U6. Download cards: one job per card

- **Where:** `finance_redactor/presentation/pdf_view.py:389-424` — the
  "Safe to share" card holds the button, two long captions, the mapping
  download, the names-v toggle and the bracketed-numbers explanation.
- **Change:** button + one-line caption stay; the mapping download sits
  **under the card** (it's a separate artifact, not a property of the PDF),
  and the bracketed-numbers note folds into the mapping section or a
  details expander. Same treatment for Excel's formatting-note caption
  (`excel_view.py:343-350`): one line if short, expander if long.

### U7. Sidebar: flatten the master-list card

- **Where:** `finance_redactor/presentation/master_list_view.py:82-95` —
  a bordered card containing two stacked expanders; **Refresh** (the one
  button people use) is inside the second one.
- **Change:** keep the summary line and the things-to-tidy badge; surface
  **Refresh** directly on the card; fold path + instructions into one
  expander, or behind the card. Sidebar then reads: logo, one-line status,
  issues badge, Refresh, Start over, Close.

### U8. Consistency pass (feeds the P3 table)

"Set options" → "Options" (`steps.py:14`); "Code list" vs "name mapping" vs
"label mapping" → pick one word and use it everywhere
(`crosswalk_view.py:80/105/153`); empty Review tab renders nothing
(`exclusion_view.py:101-102`) — show "Nothing to check: every term came from
your master list, words you typed, or a strict pattern." as the empty state.

### U9. Consider wide layout for the Review step only

Streamlit is set to `layout="centered"` (`app.py:57`), which is right for the
wizard's prose screens but forces the Review tables to scroll horizontally.
`st.set_page_config` is set once per script, so a per-step layout switch is
not possible — but the Review tables themselves accept `width="stretch"`
already; if tables still feel cramped in the centered column, moving just the
Review step's tables into `st.container()` wide styling (Streamlit's
`use_container_width` + a wide-mode app setting toggled in config) is the
fallback. Measure first; don't guess.

### Suggested UI order

U1 + U2 together (one Review redesign touching `pdf_view.py`, `excel_view.py`,
`docx_view.py` in one commit), then U7 (sidebar, self-contained), then U4/U5
(two small view-local changes), then U3/U6/U8.

## Small tech-debt notes (not urgent)

- Auto-id IDs use 5 hex chars of SHA-1 (30 bits) — a collision inside one
  document would silently merge two identities in the crosswalk. Cheap fix:
  6-8 chars. `domain/pseudonyms.py:315-318`.
- `custom_recognizer.py:105` uses `.lower()` on text where a detection-offset
  map assumes length preservation (`İ` expands to 2 chars); a length-preserving
  fold like `recasing.py` would be safer. Also `.lower()` vs `.casefold()` for
  'ß' can make a name match in detection yet fail to resolve. Both are edge
  cases; worth folding into #14 if that one is taken on.
- `pdf_gateway.py:368-372`: a multi-word candidate that wraps lines can get
  its label stamped on every line rect instead of only the first.
- `redact_excel.py:252-256` mixes positional `enumerate` with label-based
  `df.at` — safe today (RangeIndex) but fragile.
- `domain/aliases.py:127-153` `name_pattern` is dead in production (automaton
  replaced it) and the module docstring still claims otherwise.
- The Word flow's new-upload reset list omits all `pdf_*` keys
  (`docx_view.py:57-76`), so a prior PDF's buffers linger in session state
  until Start over.
- `master_list_setup.py:60-73` allows "Save and use this folder" even when the
  warning says the workbook isn't there.

## Suggested order for tomorrow

1. **P0 #2** (docx header parts) — the smallest fix with the biggest silent
   leak behind it.
2. **P0 #1** (PDF not-located counter + drop the false reassurance).
3. **P1 #6** (stale same-name re-upload) — small, prevents the worst user
   outcome.
4. **P0 #4, #5** (master-list quality findings + crash guard).
5. **P0 #3** (docx comments/footnotes/revisions) — largest; budget the rest of
   the session.
6. Batch P1 #8, #9, #10 in one UI pass.

Ship each as its own commit with the test named in the item; the existing
CI (`justfile`, coverage floor 80%) will carry the rest.
