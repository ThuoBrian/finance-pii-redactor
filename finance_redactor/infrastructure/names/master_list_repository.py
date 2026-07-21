"""Reads the Excel master list (sheets: Vendors, Funders, Staff).

The master list is the single source of truth for both detection and
pseudonymization. From one workbook this repository derives:

- the per-entity-type name lists that drive the custom recognizer, and
- the ``(entity_type, normalized_name) -> MasterEntry`` map the pseudonymizer
  uses to resolve curated IDs.

Format: one sheet per category, with columns ``Category``, ``Internal ID``,
``Name``, ``Primary Subsidiary``, ``Country``. ``Internal ID`` may be blank
(the name is still detected, but pseudonymizes to a flagged auto-id). A missing
file yields empty results. Parsing is done once and cached per instance.

Staff names imported from legacy sources sometimes embed the ID inside the
``Name`` column (``Isaac Henry - 22463``). Those suffixes are stripped and the
``Internal ID`` column is always used as the curated ID.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from finance_redactor.domain.pseudonyms import MasterEntry, normalize

_WHITESPACE = re.compile(r"\s+")
# Strip a trailing legacy ID suffix such as "Isaac Henry - 22463".
_LEGACY_SUFFIX = re.compile(r"\s+-\s+.*$")


@dataclass(frozen=True)
class MasterRow:
    """A parsed, validated master-list row mapped to its entity type."""

    category: str
    name: str
    entity_type: str
    pseudonym: str | None  # None when the row has no curated id


class MasterListRepository:
    """Loads and indexes the Excel master list."""

    def __init__(self, path: Path, categories: Mapping[str, tuple[str, str]]) -> None:
        """Store the file path and the category -> (prefix, entity_type) map."""
        self._path = path
        self._categories = categories
        self._rows: list[MasterRow] | None = None

    def rows(self) -> list[MasterRow]:
        """Return the parsed rows for known categories (cached)."""
        if self._rows is None:
            self._rows = self._parse()
        return self._rows

    def names_by_entity(self) -> dict[str, list[str]]:
        """Return detection name lists grouped by entity type.

        Includes rows without a curated id — those names are still detected and
        fall through to the pseudonymizer's auto-id path.
        """
        grouped: dict[str, list[str]] = {}
        for row in self.rows():
            grouped.setdefault(row.entity_type, []).append(row.name)
        return grouped

    def master_map(self) -> dict[tuple[str, str], MasterEntry]:
        """Return the curated lookup used by the pseudonymizer.

        Only rows with a non-blank id are included; the rest pseudonymize as
        flagged auto-ids.
        """
        mapping: dict[tuple[str, str], MasterEntry] = {}
        for row in self.rows():
            if row.pseudonym is None:
                continue
            mapping[(row.entity_type, normalize(row.name))] = MasterEntry(
                pseudonym=row.pseudonym, category=row.category
            )
        return mapping

    def counts_by_category(self) -> dict[str, int]:
        """Return the number of loaded rows per category, for the UI."""
        counts: dict[str, int] = {}
        for row in self.rows():
            counts[row.category] = counts.get(row.category, 0) + 1
        return counts

    def _parse(self) -> list[MasterRow]:
        try:
            sheets = pd.read_excel(self._path, sheet_name=None, engine="openpyxl")
        except FileNotFoundError:
            return []

        rows: list[MasterRow] = []
        for sheet_df in sheets.values():
            rows.extend(self._parse_sheet(sheet_df))
        return rows

    def _parse_sheet(self, sheet_df: pd.DataFrame) -> list[MasterRow]:
        if sheet_df.empty:
            return []
        if "Category" not in sheet_df.columns or "Name" not in sheet_df.columns:
            return []

        rows: list[MasterRow] = []
        for _, raw in sheet_df.iterrows():
            category = self._clean_str(raw.get("Category"))
            name = self._clean_name(raw.get("Name"))
            id_value = self._clean_id(raw.get("Internal ID"))
            if not name:
                continue
            resolved = self._categories.get(category)
            if resolved is None:
                continue
            prefix, entity_type = resolved
            pseudonym = f"{prefix}-{id_value}" if id_value else None
            rows.append(MasterRow(category, name, entity_type, pseudonym))
        return rows

    @staticmethod
    def _clean_str(value: object) -> str:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return ""
        return str(value).strip()

    @staticmethod
    def _clean_name(value: object) -> str:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return ""
        name = str(value).strip()
        name = _LEGACY_SUFFIX.sub("", name)
        name = _WHITESPACE.sub(" ", name).strip()
        return name

    @staticmethod
    def _clean_id(value: object) -> str | None:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        if isinstance(value, float):
            if value.is_integer():
                return str(int(value))
            return str(value)
        cleaned = str(value).strip()
        if not cleaned:
            return None
        return cleaned
