"""Reads the Excel master list (sheets configured in ``Settings.category_sheets``).

The master list is the single source of truth for both detection and
pseudonymization. From one workbook this repository derives:

- the per-entity-type name lists that drive the custom recognizer, and
- the ``(entity_type, normalized_name) -> MasterEntry`` map the pseudonymizer
  uses to resolve curated IDs.

Format: one sheet per category, with columns ``Category``, ``Internal ID``,
``Name``, ``Primary Subsidiary``, ``Country``. ``Internal ID`` may be blank
(the name is still detected, but pseudonymizes to a flagged auto-id). A missing
file yields empty results. Parsing is cached per instance and refreshed when the
file modification time changes.

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

from finance_redactor.domain.aliases import aliases
from finance_redactor.domain.pseudonyms import MasterEntry, normalize
from finance_redactor.domain.quality import (
    SEVERITY_INFO,
    SEVERITY_WARNING,
    QualityIssue,
    cap_examples,
)

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

    def __init__(
        self,
        path: Path,
        categories: Mapping[str, tuple[str, str]],
        category_sheets: Mapping[str, str] | None = None,
    ) -> None:
        """Store the file path and the category -> (prefix, entity_type) map.

        ``category_sheets`` maps each category to the Excel sheet name that
        contains it. When omitted, the sheet name is assumed to be the same as
        the category name.
        """
        self._path = path
        self._categories = categories
        self._category_sheets = category_sheets or {
            category: category for category in categories
        }
        self._rows: list[MasterRow] | None = None
        self._cached_mtime: float | None = None

    def rows(self) -> list[MasterRow]:
        """Return the parsed rows for known categories (cached by mtime)."""
        mtime = self._file_mtime()
        if self._rows is None or self._cached_mtime != mtime:
            self._rows = self._parse()
            self._cached_mtime = mtime
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
        flagged auto-ids. Each row registers its canonical name plus every alias
        variant (org-suffix equivalents, ``&``/``and`` swaps) so a document surface
        form that differs from the workbook still resolves to the curated ID.

        Two passes keep curated entries authoritative: every row's canonical name is
        registered first (first row wins an exact-name collision), then alias keys fill
        only still-empty slots. An alias can therefore never clobber another row's
        canonical name — e.g. an ``Acme Ltd`` row's ``acme limited`` alias will not
        shadow a separate ``Acme Limited`` row's own ID.
        """
        curated = [row for row in self.rows() if row.pseudonym is not None]

        mapping: dict[tuple[str, str], MasterEntry] = {}
        for row in curated:
            key = (row.entity_type, normalize(row.name))
            entry = MasterEntry(pseudonym=row.pseudonym, category=row.category)
            existing = mapping.get(key)
            if existing is None or existing.pseudonym == entry.pseudonym:
                mapping[key] = entry

        for row in curated:
            entry = MasterEntry(pseudonym=row.pseudonym, category=row.category)
            for alias in aliases(row.name):
                key = (row.entity_type, normalize(alias))
                if key not in mapping:
                    mapping[key] = entry
        return mapping

    def counts_by_category(self) -> dict[str, int]:
        """Return the number of loaded rows per category, for the UI."""
        counts: dict[str, int] = {}
        for row in self.rows():
            counts[row.category] = counts.get(row.category, 0) + 1
        return counts

    def duplicate_names(self) -> dict[str, list[str]]:
        """Return names that appear under more than one category.

        The returned dictionary maps each duplicated normalized name to the
        sorted list of categories it appears in. Duplicates can cause detection
        conflicts because the pseudonymizer keeps only one entry per name.
        """
        by_name: dict[str, set[str]] = {}
        for row in self.rows():
            key = normalize(row.name)
            by_name.setdefault(key, set()).add(row.category)
        return {
            name: sorted(categories)
            for name, categories in by_name.items()
            if len(categories) > 1
        }

    _EXAMPLE_LIMIT = 5

    def quality_report(self) -> list[QualityIssue]:
        """Detect and return actionable data-quality findings in the master list.

        Four checks, each emitted only when it has occurrences:

        - **cross-category duplicate names** — the same name under multiple
          categories maps to inconsistent prefixes (and, for categories sharing an
          entity type like Vendor/Funder, one silently clobbers the other).
        - **conflicting IDs** — the same name within one category has multiple
          Internal IDs; only one is used, the rest are ignored.
        - **blank IDs** — a name with no Internal ID is detected but pseudonymizes
          to a flagged auto-id (advisory, not an error: this is supported behavior).
        - **duplicate IDs** — one Internal ID reused by different names within a
          category, so distinct names share one pseudonym.
        """
        rows = self.rows()
        issues: list[QualityIssue] = []
        limit = self._EXAMPLE_LIMIT

        # (a) Cross-category duplicate names.
        cross = self.duplicate_names()
        if cross:
            items = [
                f"`{name}` appears in: {', '.join(categories)}"
                for name, categories in cross.items()
            ]
            examples, total = cap_examples(items, limit)
            issues.append(
                QualityIssue(
                    kind="cross_category_duplicate",
                    severity=SEVERITY_WARNING,
                    title=f"{len(cross)} name(s) appear under multiple categories",
                    detail=(
                        "This can cause conflicting pseudonyms. Keep each name in a "
                        "single category."
                    ),
                    examples=examples,
                    total=total,
                )
            )

        # (b) Same name, same category, different Internal IDs.
        by_cat_name: dict[tuple[str, str], set[str]] = {}
        for row in rows:
            if row.pseudonym is None:
                continue
            by_cat_name.setdefault((row.category, normalize(row.name)), set()).add(
                row.pseudonym
            )
        conflicts = {
            key: sorted(ids) for key, ids in by_cat_name.items() if len(ids) > 1
        }
        if conflicts:
            items = [
                f"`{name}` ({cat}) has IDs: {', '.join(ids)}"
                for (cat, name), ids in conflicts.items()
            ]
            examples, total = cap_examples(items, limit)
            issues.append(
                QualityIssue(
                    kind="conflicting_ids",
                    severity=SEVERITY_WARNING,
                    title=f"{len(conflicts)} name(s) have multiple Internal IDs",
                    detail=(
                        "Only one ID is used per name; the others are ignored. Merge "
                        "the rows or pick a single ID."
                    ),
                    examples=examples,
                    total=total,
                )
            )

        # (c) Blank Internal IDs (advisory).
        blanks_by_cat: dict[str, list[str]] = {}
        for row in rows:
            if row.pseudonym is None:
                blanks_by_cat.setdefault(row.category, []).append(row.name)
        blank_total = sum(len(v) for v in blanks_by_cat.values())
        if blank_total:
            items = [
                f"`{name}` ({cat})"
                for cat, names in blanks_by_cat.items()
                for name in names
            ]
            examples, total = cap_examples(items, limit)
            issues.append(
                QualityIssue(
                    kind="blank_ids",
                    severity=SEVERITY_INFO,
                    title=f"{blank_total} name(s) have no Internal ID",
                    detail=(
                        "They are detected but receive a flagged auto-generated ID. "
                        "Add an Internal ID to give each a stable curated ID."
                    ),
                    examples=examples,
                    total=total,
                )
            )

        # (d) One Internal ID reused by different names within a category.
        by_cat_id: dict[tuple[str, str], set[str]] = {}
        for row in rows:
            if row.pseudonym is None:
                continue
            by_cat_id.setdefault((row.category, row.pseudonym), set()).add(row.name)
        dup_ids = {
            key: sorted(names) for key, names in by_cat_id.items() if len(names) > 1
        }
        if dup_ids:
            items = [
                f"ID `{pid}` ({cat}) used by: {', '.join(names)}"
                for (cat, pid), names in dup_ids.items()
            ]
            examples, total = cap_examples(items, limit)
            issues.append(
                QualityIssue(
                    kind="duplicate_ids",
                    severity=SEVERITY_WARNING,
                    title=f"{len(dup_ids)} Internal ID(s) reused by multiple names",
                    detail=(
                        "Different names will share one pseudonym. Give each name a "
                        "unique Internal ID."
                    ),
                    examples=examples,
                    total=total,
                )
            )

        return issues

    def _file_mtime(self) -> float | None:
        try:
            return self._path.stat().st_mtime
        except (FileNotFoundError, OSError):
            return None

    def _parse(self) -> list[MasterRow]:
        try:
            workbook = pd.read_excel(self._path, sheet_name=None, engine="openpyxl")
        except FileNotFoundError:
            return []

        rows: list[MasterRow] = []
        for category, sheet_name in self._category_sheets.items():
            if category not in self._categories:
                continue
            sheet_df = workbook.get(sheet_name)
            if sheet_df is None or sheet_df.empty:
                continue
            rows.extend(self._parse_sheet(category, sheet_df))
        return rows

    def _parse_sheet(
        self, expected_category: str, sheet_df: pd.DataFrame
    ) -> list[MasterRow]:
        if "Name" not in sheet_df.columns:
            return []

        prefix, entity_type = self._categories[expected_category]
        rows: list[MasterRow] = []
        for _, raw in sheet_df.iterrows():
            category = self._clean_str(raw.get("Category"))
            name = self._clean_name(raw.get("Name"))
            id_value = self._clean_id(raw.get("Internal ID"))
            if not name:
                continue
            if category != expected_category:
                # Allow the row only if its Category cell matches the sheet.
                continue
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
