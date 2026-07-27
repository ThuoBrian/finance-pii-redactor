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
