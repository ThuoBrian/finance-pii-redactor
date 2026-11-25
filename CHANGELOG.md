# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
the `version` field in `pyproject.toml`.

## [Unreleased]

### Changed

- **A more polished look.** White cards on a soft grey page, gentle
  shadows instead of a border around everything, clearer headings, and
  proper icons in place of text symbols. Loading screens show placeholder
  shapes, the running scan's bar moves, and the Review panel tabs and the
  Download cards are easier to tell apart. The Inter typeface is bundled
  with the app, so it still makes no outside requests. Wording and
  behaviour are unchanged.
  - In dark mode, the red **Close the app** button now has enough contrast
    for its white label. A new test checks every text colour pair in both
    themes against WCAG AA.
- **A new, calmer interface.** The app is now a React page served by a small
  local web server, in place of Streamlit. It still runs only on your
  computer, opens in your browser at the same address
  (http://127.0.0.1:8501), and starts the same way (`run.bat`, `run.sh`, or
  the Desktop shortcut). Redaction, the outputs and the data classifications
  are unchanged.
  - The sidebar is gone. The master list shows as a name count at the top;
    click it for the details and **Refresh**. **Start over**, **Help** and
    **Close the app** are in the **⋯** menu.
  - Each step has one main button. Options show only the essentials, with
    the rest under **Customize**.
  - Review is one screen: the findings on the left, a **Preview**,
    **Mapping** and **Where found** panel on the right, and a bar at the
    bottom with **Apply changes** and **Continue to download**. PDF pages
    can now be previewed, redacted or original.
  - For a PDF, the names-free label mapping is now in the **Safe to share**
    card, next to the PDF it decodes.
  - Light and dark mode follow your system setting, with the same
    contrast-checked colours as before.
- **Review is quicker to check.** Click a term to jump the preview to the
  exact cell (Excel) or page (PDF) and step through every place it occurs.
  ↑ ↓ and Space work through the list from the keyboard. A **Worth a closer
  look** filter shows the model guesses most likely to be wrong.
- **Fewer steps.** Choosing the file and its settings is now one stage
  (**File → Review → Download**), with **Redact with recommended settings**
  as the main button. Customize choices are remembered for the next file
  until you close the app.
- **Nothing gets lost by accident.** Each file shows **✓ Downloaded** once
  you have it, and leaving, starting over or closing the app before
  downloading everything asks first. With no master list loaded, the Upload
  screen says so and offers the setup.
- **Long scans can be cancelled**, and show roughly how long is left.
- **Calmer screens.** Help text moved behind small **?** buttons, "Rebuilt
  the file" is a brief message that clears itself, tables sort and search,
  focus moves to each new step's heading for screen readers, and "reduce
  motion" is respected.
- **Leaner code, no change in behaviour.** Removed code only the old
  Streamlit screens or nothing at all used (two unused `execute()` methods,
  single-sheet Excel methods, a never-used crosswalk-sheet option in the Excel
  writer, the one-off `scripts/migrate_to_master_list.py`, and fields the
  interface never read), and gave the routers and the three format screens one
  shared copy of what they repeated. Tests now go through the same scan-then-
  redact path the app uses.
- **Fixed:** the Excel settings screen no longer redraws itself every 400 ms
  while it is open.
- **The launchers install updated components by themselves.** `run.bat` and
  `run.sh` now set the program up again whenever `uv.lock` has changed since
  the last setup, not only on the first run. Copying a new version over an
  existing folder (or a `git pull`) no longer leaves it missing packages. The
  installer already started each update from a fresh folder.

### Added

- **Detection test harness (for developers).** `just eval` builds a
  synthetic set of Excel, Word and PDF files with a matching made-up master
  list, runs them through the app's real redaction, and reports how many
  names leaked and how many words were flagged wrongly, by file type and by
  kind of name. It uses no real data and changes nothing in the app. See
  `eval/README.md`.
- **PDF and Word scans show live progress**, like Excel's. The scanning box
  now has a progress bar ("12 of 40 pages checked", or paragraphs for Word),
  so a long OCR run no longer looks frozen.
- **A Back button on the Options step**, in all three formats. It returns to
  Upload with the file still loaded: **Continue to options** carries on with
  your choices, and dropping in a different file starts that one fresh.
  Before, the folded file box was the only way back.
- **Whole table columns can be redacted in a PDF.** When a PDF holds a table,
  the Review step lists its columns under "Table columns to redact in full".
  Every entry in a chosen column gets a label, like a found name, and goes into
  the mapping. A cell that matches a master-list name gets that name's
  Internal ID. Columns whose header looks like a name, account or contact
  (Payee, Account No, Phone) start chosen. Tables on text pages are found by
  PyMuPDF. On scanned pages they're worked out from where the OCR'd lines sit.
  Changing the choice rebuilds the file without scanning again.
- **The PDF Options step says up front when a run will be long.** When
  reading the scanned pages would take a minute or more, it estimates the
  time ("25 scanned pages, about 3 minutes to read", at a cautious 6
  seconds a page). A PDF of 300 pages or more gets a warning to split it,
  since a run cannot be stopped halfway.
- **Scanned PDF pages are read with OCR.** A scanned page used to be either
  fully black or unredacted. Now its printed text is read (RapidOCR on ONNX
  Runtime; models ship with the package and run offline), names in it are
  replaced with labels, and with "Black out images" on, everything the OCR
  could not read with confidence (signatures, handwriting, stamps) is covered
  by a solid black box, so a signature's shape does not show. The page comes
  out as a single cleaned picture, with nothing hidden from the original. On
  by default, under Customize as "Read the text on scanned pages"; several
  seconds a page. The Review step lists the pages read with OCR to check.
  Installing grows by about 100 MB (`rapidocr`, `onnxruntime`, OpenCV
  headless and Shapely).
- **The PDF Review step says which pages are scans.** A scanned page (images,
  no text layer) used to pass through with no word about it. The warning
  lists the pages and says what happened to them: read with OCR (check them
  in the download), or, for pages OCR did not read, fully black with "Black
  out images" on and unredacted with it off.
- **An optional PDF mapping with names.** Under the PDF mapping download there
  is now a toggle, "Also prepare a mapping with names (Confidential)", off by
  default. Switched on, it adds a second download, `<name>_crosswalk.csv`, with
  an `Original name` column (the name as it appeared in the document) next to
  the label, Internal ID, category, flag and possible match. The default
  mapping is unchanged: no names, **Internal**, safe to keep with the redacted
  PDF, and a test now pins its exact header list. The names file is
  **Confidential**, the same as Word's, and the screen says so. Excel and Word
  already carried names and are unchanged.
- **Excel workbooks with several tabs are now processed in full.** Before,
  only the first tab was read, scanned and written out; every other tab was
  silently dropped. Now every tab is scanned (hidden ones too), you can pick
  which tabs and which columns per tab, and the download has each tab redacted
  in its original order. One name gets one code across all tabs, with a single
  Crosswalk sheet at the end. **Tab names are redacted too**, since a tab named
  after a vendor or person is PII; a tab you leave unselected is left out of
  the download rather than copied unredacted. Output tabs keep their source
  names instead of the old single "Redacted" tab, and a source tab called
  "Crosswalk" is renamed to "Crosswalk (2)".
- **The Windows installer adds a "Finance PII Redactor" shortcut** to the
  Desktop and Start menu, so reopening the tool is a double-click instead of
  finding `run.bat`. Updating refreshes it. If a managed machine blocks
  shortcuts, the install carries on and `run.bat` still works. The installer
  now also confirms the shortcut files actually landed (some locked-down
  machines let shortcut creation report success without writing anything),
  and `run.bat` re-creates the Desktop shortcut on launch if it's missing,
  for anyone who skipped the installer or deleted it.
- **The logo reads in both themes.** It is a white-on-transparent SVG
  (`assets/data-privacy-ai-dark-nobg.svg`) and was invisible on a light
  background, so the sidebar draws it on its own dark panel.
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

- **The Review step uses the full width of the window.** Measured in the
  centered column, a 10-column Excel preview showed 4 columns and the review
  table's **Show details** view hid 3 of its 8. Review now switches to the
  wide layout; Upload, Options and Download stay centered.
- **The app follows your light or dark preference.** Dark mode was forced
  for the logo's sake. `.streamlit/config.toml` now defines a light and a
  dark theme with the same blue accent, and the app follows each person's
  system setting. The logo sits on a dark panel that works in both.
- **Consistent, readable wording across the steps.** The step tracker says
  "Options", like the page. The Review tab counts every term as well as the
  guesses ("Review (57 terms, 2 to check)"), so it no longer reads as a
  smaller job than it is. The mapping is called "mapping" everywhere: the
  "Code list" tab is now **Mapping**. Tables on screen show "Email address"
  and "Model guess" rather than `EMAIL_ADDRESS` and `model`, and codes that
  read badly when capitalized get proper names ("Website", "IBAN", "M-Pesa
  number", "Added term" instead of "Url", "Iban code", "Mpesa number",
  "Custom"), here and in the kinds-of-information picker; the downloaded
  CSVs keep the raw codes. An empty Review tab says nothing was found, and
  the "Nothing here is a guess" note now also lists table columns you chose.
  The **Hide in output?** column keeps its name: it was renamed from
  "Redact?" on purpose, and a tick means hidden, which matches every warning
  about terms that "will not be hidden".
- **Each Download card does one job.** The PDF's **Safe to share** card holds
  the download button and one line about it. The label mapping moved under
  the cards as its own **Label mapping** section, with the note about the
  PDF's own bracketed numbers folded into it; a PDF with nothing labelled now
  says there is no mapping file instead of showing nothing. Excel's
  formatting note folds under **What is not carried over**, and the warning
  about tabs left out names the first two and "+ N more" instead of every
  tab.
- **The "Where found" tab is gone from Review.** The per-occurrence table
  (page, cell or paragraph of every match) is folded under **Where each term
  was found** at the bottom of the Review step, in all three formats. Review
  now has two tabs (three in Excel, with Preview).
- **The sidebar's master-list card is flatter.** **Refresh** sits on the card
  instead of inside a "Location and refresh" expander; the workbook's path
  and how to edit it fold into one **Where it is** expander. The summary line
  and the "things to tidy" badge are unchanged. `data/README.md` no longer
  points to an "Advanced settings" panel for the data-quality findings.
- **The Review step does one job: checking what was found.** The PDF's
  "Before you share this PDF" box (items the mapping can't decode, scanned
  pages) moved to the Download step, next to the files. Review keeps the
  warnings that change what you check: scanned pages to look at, and terms
  that could not be found on the page (shown on Download too). The words box
  and the PDF table-column picker now share one folded box, **Add something
  the tool missed (most files need nothing here)**, under the review table;
  the column picker shows only when the PDF has a table.
- **Start over asks first.** The sidebar's **Start over** used to drop the
  file, findings, review choices and downloads on one click. It now asks for
  confirmation, like **Close the app**, and says what will be lost.
- **The launch window points to "Close the app".** When the app starts, the
  terminal window now says to stop it with the **Close the app** button in
  the sidebar, on Windows and macOS/Linux alike.
- **CI also runs on macOS**, so a dependency that ships no macOS build fails
  there rather than on a user's Mac.
- **Behavior change: auto-generated codes are longer, so every one differs
  from earlier runs.** A name not on the master list gets a flagged code made
  from a hash of the name. That hash part is now 8 characters instead of 5
  (`PSN-AUTO-3F9A1C07`, not `PSN-AUTO-3F9A1`), because with 5 two different
  names in one file could share a code and be merged in the crosswalk.
  Every `*-AUTO-*` code changes, including for names already processed, so
  codes in older outputs or crosswalks won't match new runs: re-run a file
  rather than comparing its codes with older ones. Curated `STF-`/`VND-`/
  `FND-` codes and PDF labels (`[001]`) are unchanged.
- **A warning before a large Excel scan.** When the chosen columns hold 3,000
  or more distinct values, or the workbook has 500,000 or more cells, the
  Options step says so before you start, with a rough time (about 30 to 60
  values a second) and a note that fewer tabs or columns make it quicker.
- **Long Excel tabs can be paged through in the preview.** The preview stopped
  at 500 rows with a small caption. A longer tab now gets a "Rows to preview"
  picker (500 rows at a time) and a clear note saying how many rows and
  highlighted cells are off screen, and that the download has every row.
- **One column picker for every Excel tab.** The Options step drew a
  "Columns to scan" box for each tab, so a 10-tab workbook stacked ten of
  them. Now "Which tab's columns?" picks the tab and one box shows its
  columns; each tab keeps its own choice. The tab list above it shows the
  first two names and "+ N more" instead of every name, and a note names any
  tab left with no columns chosen.
- **A calmer, narrower page.** The app now uses Streamlit's centered layout
  instead of stretching across the whole screen, so tables, captions and
  buttons stay in one readable column. The Excel preview shows one full-width
  table at a time: "Redacted" first, and a "Compare with original" tab next
  to it switches to the original, instead of squeezing the two side by side
  or stacking them.
- **A tidier sidebar.** The logo is shown full width, where it can be seen.
  The master-list card fits on one line, with the file location and Refresh
  folded under "Location and refresh". Help is a link next to the privacy
  note, and "Start over" appears only once a file is loaded.
- **The Review tab says the count once.** The "Check what was detected"
  heading and the "How to use this list" expander are gone; the status line
  carries the count and a short caption explains the tick boxes.

- **The Review list is simpler.** It now shows three columns: the tick box,
  the term, and **Why it was found**, in plain words ("On your master list",
  "Looks like a name. Check it: it is an ordinary English word"). **Show
  details** brings back the kind, source, confidence, hint and count. The
  filter, search and "Untick all" buttons appear only once the list is longer
  than one screen. Tabs are renamed: **Mapping** is now **Code list**, and
  **Occurrences** is now **Where found**.
- **One "Before you share this PDF" box replaces up to three PDF warnings.**
  Scanned pages and mapping rows with no Internal ID are listed together above
  the list. The box is yellow only when something may still show. The note
  about the PDF's own bracketed numbers moved to the Download step, next to
  the code list it concerns.
- **Words to add moved from Options to Review (PDF and Word).** The box used
  to ask for missed words before anything had been found. It's now on the
  Review step, under "Missed something? Add words or phrases", so a name that
  the master list and the model both missed can be added while the findings are
  on screen. **Add and rebuild** updates the file without scanning again, and
  the new words join the review list, where they can be unticked like any other
  term. Continue waits until typed words are added. Words still carry over to
  the next file in the same session.
- **`AGENTS.md` is no longer tracked.** It stays local, like `CLAUDE.md`. The
  rules every contributor needs are in `CONTRIBUTING.md`.
- **The installers look like the launchers and update more safely.**
  `install.ps1` and `install.sh` now use the same green banner and numbered
  steps as `run.bat`/`run.sh`, and they finish with a summary: where the app
  is installed, how to open it again, and how to update. Before replacing an
  existing install they ask first, and they refuse to touch a
  `finance-pii-redactor` folder that is not an install. The old copy is moved
  aside, not deleted, until the new one is in place, so a failed download or
  a running app no longer leaves you with no install at all. On Windows, the
  download is faster and errors show as a short message instead of a stack
  trace.
- **The app shows one step at a time.** Upload, Options, Review and Download
  each get their own screen, with **Back** and **Continue** buttons and the
  step tracker on top; choices made under Options are kept when you go back.
  Before, all four steps stacked on one long page, and the review started
  well below the fold after a scan.
- **A master-list card in the sidebar**, on every step: how many names, by
  category, when the workbook last changed, a badge when there are things to
  tidy (the data-quality details open from it), where the file is, and
  **Refresh**. It replaces the master-list block inside each format's options.
  The sidebar also has **Start over** (empties the file and results from
  memory), **Help and troubleshooting**, and **Close the app**.
- **Options is one button for most people.** **Redact my file** runs with the
  recommended settings; everything else (tabs and columns, words to add,
  labels or black boxes, images, kinds of information, confidence) sits under
  **Customize**, in the same place for every format.
- **The Download step sorts files by who may see them**, in two cards: **Safe
  to share** (Internal) and **Keep private** (Confidential).
- **The Excel workbook no longer contains a Crosswalk sheet.** The name
  mapping is now its own CSV in the Keep private card, like Word's, so the
  redacted workbook is **Internal** on its own instead of Confidential as a
  whole.
- **Blue for actions, red for caution.** The accent colour is now blue
  (#2563EB, 5.17:1 against white button text), so red is left for the
  Confidential card and real warnings. Streamlit's developer toolbar (the
  "Deploy" button) is hidden.
- **The review step leads with the review.** "3. Review the results" now opens
  on a **Review** tab, labelled with how many model guesses there are to check
  (PDF and Word used to open on Mapping, with the review hidden in a tab
  called Details). The per-occurrence table moved to its own **Occurrences**
  tab, so the review tab is one table, not two. One status line says what is
  in the list and what is left (terms left visible, changes not applied yet), the
  long explanation folds into "How to read this table", a **Find a term** box
  narrows the list, and the table scrolls inside itself after about 12 rows.
  There is now one **Apply changes** button, under the table (the second one
  above it is gone), and applying shows a one-off "Rebuilt the file" note. When
  nothing is a model guess, the step says so and folds the table away under
  "Review anyway".
- **The redacted Excel workbook keeps the original's formatting.** Column
  widths and row heights, fonts, fills, borders, alignment, number formats
  (currency, dates), merged cells, freeze panes, tab colour, zoom, gridlines
  and the filter range now carry over. The output is still rebuilt from cell
  values, so nothing but cell text can come through: formatting is copied
  through an allow-list and anything not on it is dropped. Formulas stay as
  their values; comments, images and charts, data validation and
  conditional-formatting rules are not carried over, and the Download step
  says how many of each were left behind. A custom number format that holds
  readable text (such as `"Paid to ..." @`) falls back to General. Changed
  cells are still yellow, replacing the source fill. A blank header cell is no
  longer written as "Unnamed: N".
- **The false-positive review table is quicker to get through.** Terms the
  model guessed come first, lowest confidence leading, with your curated
  master-list names last, so the likeliest mistakes are at the top. The table
  gains **Confidence** and **Hint** columns (the hint says "ordinary word",
  "ALL-CAPS" or "one-word organization" for model guesses; a blank hint does
  not mean the term is right). A summary line says what is in the list, a
  **Show** filter narrows it by source, and two bulk buttons ("Untick all
  shown", "Tick all shown") each state how many rows they will touch. **Apply changes** also appears above the table. Nothing is
  ever unticked automatically, filtering only changes what is shown (hidden
  rows keep their state), and nothing is remembered between documents.
- **"Apply changes" in the detection review lights up when there is
  something to apply.** It is a greyed-out button until you untick or re-tick
  a row, then turns solid red and shows how many changes are pending.
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

- **Names split across a line on scanned PDF pages are now caught.** A
  name hyphenated at a line break ("Alex Sam-" / "ple") was read by OCR as
  two fragments and often missed. Scanned pages now go through the same
  clean-up as typed PDF text, so the name is detected whole and covered on
  both lines. Table columns chosen for redaction also match a cell that
  wrapped at a hyphen.

- **The sidebar buttons no longer drop the uploaded file.** Refresh on the
  master-list card, and Cancel under Close the app, emptied the upload box
  and sent you back to Upload, losing the review in progress. The sidebar is
  drawn before the upload box, and those buttons restarted the page before
  the box was drawn. They now act without restarting it. Start over's new
  confirm step works the same way.
- **Word's confidence slider stops at 0.85**, like Excel's. (PDF has no
  confidence slider; it runs at fixed settings.)
- **Going back to Options and redacting again keeps your review.** Changing
  one option used to wipe every untick from the Review step. Terms you
  unticked, and PDF table columns you added, now carry over to the new run
  when it finds them again, and a note on Review lists the kept terms.
- **A Word file uploaded after a PDF no longer keeps the PDF's results in
  memory.** Each format cleared a different list of earlier results on a new
  upload, and Word's left out every PDF one. All three now clear the same
  list, including half-finished review ticks.
- **A file edited and uploaded again under the same name is scanned again.**
  The app used to treat an upload as new only when its name changed, so a
  corrected `report.pdf` uploaded over the old one showed the old scan,
  review and download. An upload is now identified by its name, size and a
  hash of its contents.
- **Intel Macs get a clear message instead of a setup error.** `install.sh`
  and `run.sh` now stop on an Intel Mac and say the tool isn't supported
  there. onnxruntime, used to read scanned pages, publishes no Intel-Mac
  build, so setup used to fail partway with an unreadable uv error.
- **The upload box no longer offers `.xls`.** Old-format workbooks were always
  rejected as unreadable. The box now lists only `.xlsx`, `.pdf` and `.docx`,
  and the error for other files says to re-save a `.xls` as `.xlsx`.
- **Word first-page and even-page headers and footers are redacted.** Only the
  default header and footer of each section were scanned, so a name in a
  "Different first page" or "Different odd and even pages" header or footer
  came through unchanged. All six are scanned now. A Word file with no header
  or footer no longer gets an empty one added.
- **Word tracked changes, comments, footnotes and endnotes no longer leak.**
  Text added with Track Changes on was never checked, and deleted text stayed
  in the file, along with the reviewer's name. Comments, and who wrote them,
  were never touched, and nor were footnotes or endnotes. Now tracked changes
  are accepted before the scan (added text is checked, deleted text dropped),
  comments and the reviewer list are removed, and footnotes and endnotes are
  checked like the body. The redacted file has no comments or change history;
  see the troubleshooting guide.
- **Master-list rows with the wrong Category are reported, not dropped
  silently.** A row whose `Category` cell doesn't match its sheet (blank, a
  different word, or no `Category` column at all) was skipped with no sign,
  so that name was never detected. Such rows are still not loaded, but the
  master-list card now lists them under "things to tidy" ("N row(s) skipped
  because their Category cell doesn't match").
- **A damaged or password-protected master list no longer crashes the app.**
  A truncated, encrypted or locked workbook used to stop the app with a raw
  error. It now loads 0 names like a missing file does, offers the setup
  dialog, and the master-list card says the list could not be opened and why.
- **Master-list names with ` - ` are no longer cut short.** Everything after
  a spaced dash used to be stripped, so `Acme - Kenya` became `Acme` and the
  full form never matched. Only the legacy numeric-ID suffix
  (`Jane Doe - 10001`) is stripped now. Other names are kept whole, and the
  part before the dash is still matched too, so nothing that matched before
  stops matching. The master-list card lists these names ("contain ' - '").
  If two such rows share the short part but have different Internal IDs, a
  bare short form gets a flagged auto-code instead of a guessed ID.
- **The master-list setup dialog no longer saves a wrong folder on one
  click.** "Save and use this folder" was clickable even while the dialog
  warned that the workbook wasn't there. It is now greyed out until a folder
  is entered, and when the workbook isn't found you must tick "Save anyway:
  the folder is still syncing" first.
- **"Skip for now" on the master-list setup dialog is remembered.** It used
  to ask again on every launch. The choice is now saved in
  `~/.finance_pii_redactor/settings.json` next to the folder setting, and
  cleared as soon as a master list loads with names, so a list that later
  goes missing still prompts.
- **Master-list names match with or without accents.** `Jose Garcia` in a
  document was missed by the master-list matcher when the row said
  `José García`, and the other way round. Both sides are now accent- and
  case-folded one character at a time, so the redaction still covers exactly
  the document's characters, and the match resolves to the row's curated ID
  (unless two rows differ only by accents and have different IDs, in which
  case it gets a flagged auto-code). This also fixes an offset bug: a
  dotted capital `İ` anywhere before a name shifted that name's redaction one
  character to the right. Surname-only matching stays off, as before.
- **PDF pages with typed text over a large scanned image are read with OCR.**
  Only pages with no text layer at all used to count as scans, so a typed
  heading over a scanned receipt, or a scanner's searchable PDF, had its
  picture passed through unread: a name visible only in the image survived
  unless "Black out images" was on. A page whose images cover at least 15%
  of it is now treated as a scan. Its text layer is still redacted by
  search first, then the page is read with OCR and rebuilt. With OCR off or
  not installed, such pages are listed in the scanned-pages warning.
- **A PDF term that could not be found on the page is no longer reported as
  hidden.** When a name was read from a page's text but no search could match
  it on the page (a ligature or font encoding the search can't see through),
  nothing covered it, yet the Review step counted it as redacted and Apply
  said "Every detected term is hidden". Such terms now get their own warning
  on the Review step, naming them and their pages, and the reassurance only
  appears when every term was found.
- **PDF comments, form fields, bookmarks and attachments no longer survive
  redaction.** None of them is page text, so detection never saw them, and
  each could carry a name: a comment or its author, a filled-in form field, a
  bookmark title, a file attached to the document. The redacted PDF now drops
  them all on save, as it already did for document properties. Links to
  another page of the same PDF are kept.
- **A PDF name that wraps onto the next line gets one label, not two.** A
  two-word name split over a line break was covered on both lines but had its
  `[001]` label stamped on each part. Only the first part is labelled now;
  both are still covered.
- **The Excel confidence slider stops at 0.85.** It went to 1.0. Above 0.85
  the bank-account, M-Pesa and SWIFT patterns stop being masked, and above
  0.90 every master-list match is dropped.
- **An Excel file with nothing found can still be downloaded.** The Download
  step used to say "Nothing was detected" and offer no file, so a workbook
  trimmed to some tabs could not be saved. The rebuilt workbook is now
  always offered, with the note kept above it.
- **Excel column headers are redacted.** A name used as a column header went
  into the download unchanged, because only cells and tab names were
  scanned. Every header of a scanned tab is now checked, chosen column or
  not, shows in the Review table, and is replaced and highlighted yellow.
- **Excel IDs keep their leading zeros.** A text cell such as `0041` used to
  come out of the redacted workbook as the number `41`. Cells are now kept as
  written: text stays text, and numbers and dates stay numbers and dates.
  Columns that mix text with numbers are now picked for scanning by default.
- **Review tick boxes respond to a single click.** Every other tick or
  untick in the "Hide in output?" column was ignored, so a box seemed to
  need a double click. Each click now registers.
- **`run.bat` reports first-time setup problems correctly.** It read the
  wrong exit code, so on a machine without `uv` it said the setup helper
  failed even when it installed fine, and a failed program setup was
  reported as "Program is ready" before the app failed to start. It now
  checks the real result and, when setup fails, shows the setup log (saved
  as `finance-redact-setup.log` in your temp folder) the way `run.sh`
  already did. Both launchers now mention Word files in their banner.
- **"Continue to download" waits until review changes are applied.** It used
  to go ahead with ticks that had not been applied, so the download was built
  from the older choice. In one case that was a leak: a term unticked and
  applied, then re-ticked to hide it again, still showed. Continue is now
  disabled, with a note, until the changes are applied or undone.
- **PDF "Not in the master list" and "Ambiguous master-list match" notices are
  blue information boxes, not yellow warnings.** Those items were redacted like
  any other; the notice is only about decoding them later. Yellow is kept for
  what affects what shows.
- **Blacked-out images, signatures included, are now really removed from
  PDFs.** "Also black out images" used to draw a black box over each image and
  leave the image itself in the file, where any PDF tool could extract it
  intact. Redactions now blank the pixels underneath (an image covered
  completely is dropped), with a fallback that removes the image outright if
  its format defeats pixel editing. PDFs blacked out before this fix still
  carry their images: redact the originals again.
- **The review step no longer crashes with `KeyError: <DetectionSource.MODEL:
  'model'>`.** It happened when Streamlit re-imported the code while a result
  was still on screen (for example after an update or a code change): findings
  kept in the session held members of the old copy of the enum, and the review
  table compared them by identity. It now compares by value, and any unknown
  source sorts with the model guesses.
- **A short word redacted in a PDF no longer blacks out the same letters inside
  longer words.** Redacting "IPA" also covered the "ipa" in "principal",
  "participant" and "municipal", because the PDF step located each detection
  with a plain substring search. Detection was already whole-word (and Excel
  and Word redact by position), so only the PDF output was affected. Hits that
  sit inside a longer word are now dropped. If a hit cannot be lined up with
  the page text (a name wrapped across lines, an unusual layout) it is kept
  redacted, so the fix never leaves a name showing.
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
