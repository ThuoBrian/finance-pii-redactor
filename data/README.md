# Data folder

`Names List - Organized.xlsx` is the **master list** — the one file that
controls which names get which ID codes. **For this team, it lives in one
shared Box folder — never in this local `data/` folder.** See
[Sharing one master list across a team](#sharing-one-master-list-across-a-team)
below for the required, one-time setup that points your install at it.

Once your install is pointed at the shared copy: edit it in place in Box,
save and close the file, then refresh the page in your browser — no need to
restart the app; it picks up the change automatically.

`Names List - Organized.xlsx` contains real names, so it is **Confidential**
and is never committed to git (this local `data/` folder is gitignored).
Keep it stored securely in Box — this is exactly why the app doesn't ship it
and won't put a copy in this repo for you.

## Sharing one master list across a team

This team does not keep a per-install master list. Every teammate's install
must point at the **same shared Box folder**, so the same name always gets
the same code for everyone — never save or leave a copy of
`Names List - Organized.xlsx` in this local `data/` folder. If neither the
in-app setting nor the `FPR_MASTER_LIST_DIR` environment variable below is
ever set, the app silently falls back to reading whatever is in this local
folder instead of the shared list (typically nothing, so names load as
zero) — that fallback exists for standalone installs outside this team, not
for us.

**Easiest way (recommended):** just launch the app. If it can't find a
master list, it automatically shows a **"Set up your shared master list"**
dialog right in the browser — paste in your local path to the shared Box
folder there and it takes effect immediately, no terminal or restart needed.
The steps below are the manual, environment-variable alternative (useful for
a scripted/IT-managed deployment across many machines, or if you'd rather not
use the dialog); the in-app setting takes precedence over the environment
variable if both end up set.

1. Confirm the shared workbook is in your team's designated Box Drive folder
   (ask your list owner if you don't have the path) — **never** a
   generally-shared or public folder, and never inside this git repo. In Box
   Drive, right-click the folder and choose **Make Available Offline**, so
   the app keeps working without depending on an active connection every
   time it reads the file.
2. Set the `FPR_MASTER_LIST_DIR` environment variable to *your own* local
   path to that shared folder (Box mounts it at a different literal path on
   each machine — the same cloud folder, but not necessarily the same
   literal path string on every computer), then restart the app (`run.bat` /
   `run.sh`):
   - Windows (PowerShell, one-time): `setx FPR_MASTER_LIST_DIR "C:\Users\<you>\Box\path\to\folder"`,
     then close and reopen the terminal before launching `run.bat`.
   - macOS/Linux: add `export FPR_MASTER_LIST_DIR="/path/to/shared/folder"` to
     your shell profile (e.g. `~/.zshrc` or `~/.bashrc`), then re-open the
     terminal before running `./run.sh`.
3. Refresh the app in the browser and check the master-list summary in
   **Advanced settings** — the row counts should match what everyone else on
   the team sees. If it shows zero names, double-check the path and the
   exact filename (see below) before assuming the shared list is empty.

Once set up this way, everyone's install reads and caches the same workbook
(still refreshed automatically whenever it's edited and saved), so the same
name gets the same code for everyone.

### Keep the filename exactly as-is

The app looks for the file by its **exact name**, `Names List - Organized.xlsx`
— the folder can move (that's what `FPR_MASTER_LIST_DIR` is for), but the
filename itself is not configurable. Get it wrong and the app doesn't error,
it just silently loads zero names, so this matters more than it looks like it
should:

- **Never rename it or add a version to the filename** — no
  `Names List - Organized (2).xlsx`, `... FINAL.xlsx`, or `... 2026-08-07.xlsx`.
  Anything other than the exact name is invisible to the app.
- **Edit in place** (open, edit, `Ctrl+S`, close) — don't "Save As" under a
  different name, or the app keeps reading the old, now-stale file.
- **Watch for sync-conflict copies.** If two people edit at nearly the same
  time, Box (and SharePoint/OneDrive) can create a renamed "conflicted copy"
  alongside the original, silently splitting the edits across two files. This
  is the other reason (besides `Internal ID` collisions) to have a single
  owner or small group make changes, one at a time — see below.
- **Want version history?** Use Box's own **Version History** on the file
  instead of naming a new version yourself — it gives you a real audit trail
  without ever touching the name the app depends on.
- Keep the exact casing and spacing (`Names List - Organized.xlsx`, not
  `Names List-Organized.xlsx` or `names list - organized.xlsx`) — cloud-synced
  storage can be pickier about this than a local drive.

## File format

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
- **Ambiguous common word** (info, not an error) — a name is a single word
  that's also an ordinary English word (e.g. a funder named `Across`). Every
  plain-English occurrence of that word will be detected, not just the
  entity — confirm this is intended or make the name more distinctive.

Exact duplicate rows (same name and same ID) are benign and are not flagged.

Because edits are still manual (someone opens the file in Excel and adds a
row), have a single owner or small group make changes to avoid two people
assigning the same `Internal ID` to two different names at the same time — the
data-quality checks above (conflicting/reused IDs) will flag it on the next
load either way. Never paste this file's contents into Claude or any other AI
chat — only the tool's pseudonymized *output* is meant to leave the controlled
environment.
