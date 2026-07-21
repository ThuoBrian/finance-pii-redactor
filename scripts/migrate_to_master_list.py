"""One-off migration: person.txt + organization.txt -> Names List - Organized.xlsx.

Converts the legacy plain-text name lists into the structured Excel master list,
merging them with any existing workbook.

- person.txt -> sheet ``Staff``. A trailing `` - <digits>`` suffix (e.g.
  ``Aaron Elijah Mutungi - 90863``) is parsed into the ``Internal ID`` column and
  stripped from the name, fixing the latent bug where the recognizer searched for
  the whole string including the ID.
- organization.txt -> sheet ``Vendors`` with a blank ``Internal ID`` (review and
  split Vendor vs Funder, and assign IDs, by hand afterwards).

Names with a blank ``Internal ID`` are still detected; they pseudonymize to a
flagged auto-id until a curated ID is filled in.

Run once from the repo root:

    uv run python scripts/migrate_to_master_list.py

Then delete the two ``.txt`` files. The resulting ``data/Names List - Organized.xlsx``
is gitignored because it contains real names.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_PERSON = _DATA_DIR / "person.txt"
_ORGANIZATION = _DATA_DIR / "organization.txt"
_OUTPUT = _DATA_DIR / "Names List - Organized.xlsx"

# Trailing " - 90863" style staff id.
_ID_SUFFIX = re.compile(r"^(.*?)\s+-\s+(\d+)\s*$")

# Expected columns in the Excel master list.
_COLUMNS = [
    "Category",
    "Internal ID",
    "Name",
    "Primary Subsidiary",
    "Country",
]

_SHEET_MAP = {
    "Staff": "Staff",
    "Vendor": "Vendors",
    "Funder": "Funders",
}


def _read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as handle:
        return [
            line.split("#", 1)[0].strip()
            for line in handle
            if line.split("#", 1)[0].strip()
        ]


def _person_rows() -> list[tuple[str, int | None, str]]:
    rows: list[tuple[str, int | None, str]] = []
    for line in _read_lines(_PERSON):
        if line.lower() == "name":  # stray header artifact in the legacy file
            continue
        match = _ID_SUFFIX.match(line)
        if match:
            rows.append(("Staff", int(match.group(2)), match.group(1).strip()))
        else:
            rows.append(("Staff", None, line))
    return rows


def _organization_rows() -> list[tuple[str, int | None, str]]:
    return [("Vendor", None, line) for line in _read_lines(_ORGANIZATION)]


def _load_existing_sheets() -> dict[str, pd.DataFrame]:
    if not _OUTPUT.exists():
        return {}
    try:
        return pd.read_excel(_OUTPUT, sheet_name=None, engine="openpyxl")
    except FileNotFoundError:
        return {}


def _normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure the dataframe has the expected columns, adding blanks if missing."""
    for col in _COLUMNS:
        if col not in df.columns:
            df[col] = None
    return df[_COLUMNS].copy()


def _merge_rows(
    existing: pd.DataFrame, new_rows: list[tuple[str, int | None, str]]
) -> pd.DataFrame:
    """Append legacy rows to an existing sheet dataframe, deduplicating by name."""
    new_df = pd.DataFrame(
        new_rows,
        columns=["Category", "Internal ID", "Name"],
    )
    new_df["Primary Subsidiary"] = None
    new_df["Country"] = None
    new_df = new_df[_COLUMNS]

    combined = pd.concat([existing, new_df], ignore_index=True)
    # Prefer the row that has an Internal ID when the same (category, name) appears.
    combined = combined.sort_values(
        by=["Category", "Name", "Internal ID"],
        key=lambda col: col.isna() if col.name == "Internal ID" else col,
        ascending=[True, True, True],
    )
    combined = combined.drop_duplicates(subset=["Category", "Name"], keep="first")
    return combined


def main() -> None:
    """Generate or merge into the Excel master list from the legacy text lists."""
    sheets = _load_existing_sheets()
    normalized: dict[str, pd.DataFrame] = {}

    for sheet_name in ["Vendors", "Funders", "Staff"]:
        df = sheets.get(sheet_name)
        if df is None or df.empty:
            df = pd.DataFrame(columns=_COLUMNS)
        normalized[sheet_name] = _normalize_dataframe(df)

    new_staff = _person_rows()
    new_vendors = _organization_rows()

    if new_staff:
        normalized["Staff"] = _merge_rows(normalized["Staff"], new_staff)
    if new_vendors:
        normalized["Vendors"] = _merge_rows(normalized["Vendors"], new_vendors)

    with pd.ExcelWriter(_OUTPUT, engine="openpyxl") as writer:
        for sheet_name, df in normalized.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    total = sum(len(df) for df in normalized.values())
    with_id = sum(int((df["Internal ID"].notna()).sum()) for df in normalized.values())
    by_cat = {category: len(df) for category, df in normalized.items()}
    print(f"Wrote {total} rows to {_OUTPUT}")
    print(f"  with curated id: {with_id}")
    print(f"  needing id/review: {total - with_id}")
    print(f"  by sheet: {by_cat}")


if __name__ == "__main__":
    main()
