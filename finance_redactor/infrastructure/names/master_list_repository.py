"""Reads the CSV master list (category, name, id).

The master list is the single source of truth for both detection and
pseudonymization. From one file this repository derives:

- the per-entity-type name lists that drive the custom recognizer, and
- the ``(entity_type, normalized_name) -> MasterEntry`` map the pseudonymizer
  uses to resolve curated IDs.

Format: a header row ``category,name,id``; one entity per row. ``id`` may be left
blank (the name is still detected, but pseudonymizes to a flagged auto-id). Blank
lines and rows whose first cell starts with ``#`` are ignored. A missing file
yields empty results. Parsing is done once and cached per instance.
"""

from __future__ import annotations

import csv
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from finance_redactor.domain.pseudonyms import MasterEntry, normalize


@dataclass(frozen=True)
class MasterRow:
    """One parsed, validated master-list row mapped to its entity type."""

    category: str
    name: str
    entity_type: str
    pseudonym: str | None  # None when the row has no curated id


class MasterListRepository:
    """Loads and indexes the CSV master list."""

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
            with open(self._path, encoding="utf-8-sig", newline="") as handle:
                return self._parse_handle(handle)
        except FileNotFoundError:
            return []

    def _parse_handle(self, handle) -> list[MasterRow]:
        rows: list[MasterRow] = []
        reader = csv.DictReader(self._normalize_lines(handle))
        if reader.fieldnames is None:
            return rows
        for raw in reader:
            category = (raw.get("category") or "").strip()
            name = (raw.get("name") or "").strip()
            id_value = (raw.get("id") or "").strip()
            if not name:
                continue
            resolved = self._categories.get(category)
            if resolved is None:
                # Unknown/blank category: cannot determine entity type, skip.
                continue
            prefix, entity_type = resolved
            pseudonym = f"{prefix}-{id_value}" if id_value else None
            rows.append(MasterRow(category, name, entity_type, pseudonym))
        return rows

    @staticmethod
    def _normalize_lines(handle):
        # Drop comment and blank lines before the CSV reader sees them.
        for line in handle:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            yield line
