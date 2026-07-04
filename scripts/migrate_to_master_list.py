"""One-off migration: person.txt + organization.txt -> master_list.csv.

Converts the legacy plain-text name lists into the structured master list.

- person.txt -> category ``Staff``. A trailing `` - <digits>`` suffix (e.g.
  ``Aaron Elijah Mutungi - 90863``) is parsed into a separate ``id`` column and
  stripped from the name, fixing the latent bug where the recognizer searched for
  the whole string including the ID.
- organization.txt -> category ``Vendor`` with a blank ``id`` (review and split
  Vendor vs Funder, and assign IDs, by hand afterwards).

Names with a blank ``id`` are still detected; they pseudonymize to a flagged
auto-id until a curated ID is filled in.

Run once from the repo root:  ``uv run python scripts/migrate_to_master_list.py``
Then delete the two .txt files and commit ``master_list.csv``.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
_PERSON = _DATA_DIR / "person.txt"
_ORGANIZATION = _DATA_DIR / "organization.txt"
_OUTPUT = _DATA_DIR / "master_list.csv"

# Trailing " - 90863" style staff id.
_ID_SUFFIX = re.compile(r"^(.*?)\s+-\s+(\d+)\s*$")


def _read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as handle:
        return [
            line.split("#", 1)[0].strip()
            for line in handle
            if line.split("#", 1)[0].strip()
        ]


def _person_rows() -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for line in _read_lines(_PERSON):
        if line.lower() == "name":  # stray header artifact in the legacy file
            continue
        match = _ID_SUFFIX.match(line)
        if match:
            rows.append(("Staff", match.group(1).strip(), match.group(2)))
        else:
            rows.append(("Staff", line, ""))
    return rows


def _organization_rows() -> list[tuple[str, str, str]]:
    return [("Vendor", line, "") for line in _read_lines(_ORGANIZATION)]


def _dedupe(rows: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    """Drop duplicate (category, name); prefer the variant that carries an id."""
    best: dict[tuple[str, str], tuple[str, str, str]] = {}
    for category, name, id_value in rows:
        key = (category, name.casefold())
        existing = best.get(key)
        if existing is None or (not existing[2] and id_value):
            best[key] = (category, name, id_value)
    return list(best.values())


def main() -> None:
    """Generate master_list.csv from the legacy text lists."""
    rows = _dedupe(_person_rows() + _organization_rows())

    with open(_OUTPUT, "w", encoding="utf-8", newline="") as handle:
        handle.write(
            "# Master list (single source of truth for detection + pseudonymization).\n"
        )
        handle.write(
            "# Columns: category, name, id. category is one of Staff, Vendor, Funder.\n"
        )
        handle.write(
            "# id is optional; blank-id names are detected but get a flagged auto-id.\n"
        )
        writer = csv.writer(handle)
        writer.writerow(["category", "name", "id"])
        writer.writerows(rows)

    with_id = sum(1 for _, _, id_value in rows if id_value)
    by_cat: dict[str, int] = {}
    for category, _, _ in rows:
        by_cat[category] = by_cat.get(category, 0) + 1
    print(f"Wrote {len(rows)} rows to {_OUTPUT}")
    print(f"  with curated id: {with_id}")
    print(f"  needing id/review: {len(rows) - with_id}")
    print(f"  by category: {by_cat}")


if __name__ == "__main__":
    main()
