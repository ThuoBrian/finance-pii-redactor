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
- **Name** — the name as it appears in your files. For `Staff`, legacy entries
  sometimes embed the ID inside the name (e.g. `Jane Doe - 22463`). The app
  strips the trailing `- <anything>` and uses the `Internal ID` column as the
  curated ID.
- **Primary Subsidiary** and **Country** — ignored by the app; kept for reference.

**`Names List - Organized.xlsx` contains real names, so it is Confidential and is**
**never committed to git** (it is gitignored). Keep it stored securely.
