# Data folder

Put your **master list** here as **`Names List - Organized.xlsx`**. This is the one
file you edit to control which names get which ID codes. After editing it,
save and close the file, then refresh the page in your browser — no need to
restart the app; it picks up the change automatically.

The workbook has one sheet per category:

|Sheet|Category column|Entity type|Pseudonym prefix|
|-|-|-|-|
|`Vendors`|`Vendor`|organization|`VND-`|
|`Funders`|`Funder`|organization|`FND-`|
|`Staff`|`Staff`|person|`STF-`|

Each sheet must have these columns:

- **Category** — `Staff`, `Vendor`, or `Funder`.
- **Internal ID** — the number you assign. The app builds the code as
  `<prefix>-<Internal ID>` (Staff `91345` → `STF-91345`). Leave blank to still
  detect the name but give it a flagged auto-code for now.
- **Name** — the name as it appears in your files. You only need **one row per
  entity**: matching is alias-aware, so equivalent surface forms resolve to the
  same curated ID. Specifically:
  - Organization suffix equivalents: `Ltd` = `Limited`, `Inc` = `Incorporated`,
    `Corp` = `Corporation`, `Co` = `Company` (with or without a trailing period);
    `LLC` and `PLC` match with or without a period.
  - `&` and `and` swapped between words (`Smith & Co` = `Smith and Co`).

  Spelling, word order, and middle initials are **not** matched automatically —
  add a separate row for each genuinely distinct surface form. For `Staff`,
  legacy entries sometimes embed the ID inside the name (e.g. `Jane Doe - 22463`).
  The app strips the trailing `- <anything>` and uses the `Internal ID` column as
  the curated ID.
- **Primary Subsidiary** and **Country** — ignored by the app; kept for reference.

## Data-quality checks (shown on load)

When the workbook loads, the app surfaces any of these in the **Advanced
settings** panel so the IDs it emits stay trustworthy:

- **Cross-category duplicate** (warning) — a name appears under more than one
  category. Keep each name in a single category to avoid conflicting IDs.
- **Conflicting IDs** (warning) — the same name in the same category has two
  different `Internal ID`s. Merge the rows or pick one ID.
- **Reused Internal ID** (warning) — one `Internal ID` is shared by two different
  names within a category. Give each name its own ID.
- **Blank Internal ID** (info, not an error) — a name with no `Internal ID` is
  still detected but gets a flagged auto-code. Fill in the ID when you want a
  curated code.

Exact duplicate rows (same name and same ID) are benign and are not flagged.

**`Names List - Organized.xlsx` contains real names, so it is Confidential and is**
**never committed to git** (it is gitignored). Keep it stored securely.

## Sharing one master list across a team

By default, this `data/` folder lives next to your own copy of the tool, so
each teammate who installs it starts with their own independent, empty master
list. That's fine if you're the only one using the tool — codes stay stable
for you across every file, forever, because the list itself never changes
codes for a name once assigned. But if two people each keep their own separate
copy of the list, the same name can end up with two different codes (one
person's `Brian Thuo` = `STF-91345`, a colleague's = `STF-77712`, or one of you
just hasn't added him yet) — not a bug, just two different lists.

To get the same codes for the same names across a whole team, point every
teammate's install at **one shared copy** of the workbook instead of each
person's own local file:

1. Put `Names List - Organized.xlsx` on one properly access-controlled shared
   location your team already uses for Confidential data (e.g. an
   access-controlled SharePoint or network-drive folder) — **never** a
   generally-shared or public folder, and never inside this git repo.
2. On each teammate's machine, set the `FPR_MASTER_LIST_DIR` environment
   variable to that shared folder's path, then restart the app (`run.bat` /
   `run.sh`):
   - Windows (PowerShell, one-time): `setx FPR_MASTER_LIST_DIR "\\server\share\path"`,
     then close and reopen the terminal before launching `run.bat`.
   - macOS/Linux: add `export FPR_MASTER_LIST_DIR="/path/to/shared/folder"` to
     your shell profile (e.g. `~/.zshrc` or `~/.bashrc`), then re-open the
     terminal before running `./run.sh`.
3. Everyone's install now reads and caches the same workbook (still refreshed
   automatically whenever it's edited and saved), so the same name gets the
   same code for everyone.

Because edits are still manual (someone opens the file in Excel and adds a
row), have a single owner or small group make changes to avoid two people
assigning the same `Internal ID` to two different names at the same time — the
data-quality checks below (conflicting/reused IDs) will flag it on the next
load either way. Never paste this file's contents into Claude or any other AI
chat — only the tool's pseudonymized *output* is meant to leave the controlled
environment.
