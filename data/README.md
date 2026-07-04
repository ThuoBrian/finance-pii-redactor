# Data folder

Put your **master list** here as **`master_list.csv`**. This is the one file you
edit to control which names get which ID codes. After editing it, restart the app.

The file has three columns:

```csv
category,name,id
Staff,Jane Doe,91345
Vendor,Example Supplies Ltd,1045
Funder,Example Foundation,7745
```

- **category** — one of `Staff`, `Vendor`, or `Funder`.
- **name** — the exact name as it appears in your files.
- **id** — the number you assign. The app builds the code as `<prefix>-<id>`
  (Staff `91345` → `STF-91345`, Vendor → `VND-…`, Funder → `FND-…`). Leave `id`
  blank to still detect the name but give it a flagged auto-code for now.
- Lines starting with `#` and blank lines are ignored.

**`master_list.csv` contains real names, so it is Confidential and is never
committed to git** (it is gitignored). Keep it stored securely.
