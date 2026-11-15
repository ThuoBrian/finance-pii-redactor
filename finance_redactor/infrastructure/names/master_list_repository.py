"""Reads the Excel master list (sheets configured in ``Settings.category_sheets``).

The master list is the single source of truth for both detection and
pseudonymization. From one workbook this repository derives:

- the per-entity-type name lists that drive the custom recognizer, and
- the ``(entity_type, normalized_name) -> MasterEntry`` map the pseudonymizer
  uses to resolve curated IDs.

Format: one sheet per category, with columns ``Category``, ``Internal ID``,
``Name``, ``Primary Subsidiary``, ``Country``. ``Internal ID`` may be blank
(the name is still detected, but pseudonymizes to a flagged auto-id). A missing
file yields empty results; so does a damaged, password-protected or locked one,
with the reason surfaced through ``quality_report``. Parsing is cached per instance and refreshed when the
file modification time changes.

Staff names imported from legacy sources sometimes embed the ID inside the
``Name`` column (``Jane Doe - 10001``). Those numeric suffixes are stripped and
the ``Internal ID`` column is always used as the curated ID. Any other
`` - ...`` suffix (``Acme - Kenya``) is kept as part of the name, and the part
before the dash is matched as well (see ``MasterRow.short_name``).
"""

from __future__ import annotations

import re
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from finance_redactor.domain.aliases import aliases
from finance_redactor.domain.common_words import COMMON_ENGLISH_WORDS
from finance_redactor.domain.pseudonyms import MasterEntry, normalize
from finance_redactor.domain.quality import (
    SEVERITY_INFO,
    SEVERITY_WARNING,
    QualityIssue,
    cap_examples,
)

_WHITESPACE = re.compile(r"\s+")
# The one sanctioned legacy format: a trailing numeric ID, "Jane Doe - 10001"
# (what scripts/migrate_to_master_list.py parsed out of person.txt). Stripped
# silently. Anything else after a spaced dash ("Acme - Kenya") is part of the
# name and is kept; see MasterRow.short_name.
_LEGACY_ID_SUFFIX = re.compile(r"\s+-\s+\d+\s*$")
_SPACED_DASH = re.compile(r"\s+-\s+")


@dataclass(frozen=True)
class MasterRow:
    """A parsed, validated master-list row mapped to its entity type.

    ``internal_id`` is the raw ``Internal ID`` cell (``"17728"``) and
    ``pseudonym`` is the display form built from it (``"VND-17728"``). Both are
    None together when the row has no curated id. They are kept as two fields
    rather than one derived from the other because the quality checks and the
    UI key off ``pseudonym`` while the PDF mapping file needs the bare id;
    recovering the id by splitting the pseudonym is unsafe, since
    ``"VND-17728"`` and ``"ORG-AUTO-3F9A1C07"`` have the same shape. Change them
    together.


    ``short_name`` is the part before a spaced dash when the name has one
    that isn't a legacy numeric ID (``"Acme"`` for ``"Acme - Kenya"``). It is
    detected and resolved alongside ``name`` rather than replacing it: these
    names used to be cut to the short form, so a document that writes only
    ``Acme`` must keep matching (dropping it would loosen detection), while
    the full form must now match too. Over-redaction is the cheaper mistake.
    """

    category: str
    name: str
    entity_type: str
    pseudonym: str | None  # None when the row has no curated id
    internal_id: str | None = None  # the raw Internal ID cell behind it
    short_name: str | None = None  # part before " - ", matched as well


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
        # Filled by _parse alongside _rows: rows dropped because their
        # Category cell doesn't match their sheet, as (sheet, name) pairs.
        self._skipped: list[tuple[str, str]] = []
        # Set by _parse when the file exists but can't be read; the list then
        # loads 0 names, the same degraded state as a missing file.
        self._load_error: str | None = None

    def rows(self) -> list[MasterRow]:
        """Return the parsed rows for known categories (cached by mtime)."""
        mtime = self._file_mtime()
        if self._rows is None or self._cached_mtime != mtime:
            self._rows = self._parse()
            self._cached_mtime = mtime
        return self._rows

    def fingerprint(self) -> str:
        """Identify which version of the master list this is, for the PDF mapping.

        The PDF mapping file carries Internal IDs and no names, so there is
        nothing in it to notice a stale decode against: if a row is edited or
        an ID reused, an old mapping quietly resolves to the wrong name. This
        is not a new risk - ``STF-10010`` already depended on the list's
        current contents the same way - but removing the name removed the
        informal cross-check, so record which list a mapping was made from.

        Format: ``<filename>@<mtime, ISO 8601 UTC>/<row count>``. Empty string
        when the file is missing. It makes a stale decode *detectable*, not
        impossible; whoever decodes has to compare it against the list they hold.
        """
        mtime = self._file_mtime()
        if mtime is None:
            return ""
        stamp = (
            datetime.fromtimestamp(mtime, tz=UTC)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
        return f"{self._path.name}@{stamp}/{len(self.rows())}"

    def names_by_entity(self) -> dict[str, list[str]]:
        """Return detection name lists grouped by entity type.

        Includes rows without a curated id — those names are still detected and
        fall through to the pseudonymizer's auto-id path.
        """
        grouped: dict[str, list[str]] = {}
        for row in self.rows():
            names = grouped.setdefault(row.entity_type, [])
            names.append(row.name)
            if row.short_name:
                names.append(row.short_name)
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
            # The list comprehension above already guarantees this, but the
            # type checker can't see through a filtered list's element type -
            # assert it explicitly (also a real safety net if that filter is
            # ever weakened by a future edit).
            assert row.pseudonym is not None
            key = (row.entity_type, normalize(row.name))
            entry = MasterEntry(
                pseudonym=row.pseudonym,
                category=row.category,
                display_name=row.name,
                internal_id=row.internal_id,
            )
            existing = mapping.get(key)
            if existing is None or existing.pseudonym == entry.pseudonym:
                mapping[key] = entry

        # A short form ("Acme" from "Acme - Kenya") is only resolved when every
        # row sharing it agrees on the ID; "Acme - Kenya" and "Acme - Uganda"
        # with different IDs leave a bare "Acme" to a flagged auto-id rather
        # than a coin-flip curated one. It is still detected either way.
        short_ids: dict[tuple[str, str], set[str]] = {}
        for row in curated:
            if row.short_name:
                key = (row.entity_type, normalize(row.short_name))
                short_ids.setdefault(key, set()).add(row.pseudonym or "")

        for row in curated:
            assert row.pseudonym is not None
            entry = MasterEntry(
                pseudonym=row.pseudonym,
                category=row.category,
                display_name=row.name,
                internal_id=row.internal_id,
            )
            variants = list(aliases(row.name))
            if row.short_name:
                short_key = (row.entity_type, normalize(row.short_name))
                if len(short_ids[short_key]) == 1:
                    variants.extend(aliases(row.short_name))
            for alias in variants:
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

        Each check is emitted only when it has occurrences:

        - **skipped rows** — a row whose Category cell doesn't match its sheet
          (blank, missing column, different wording) is not loaded, so the
          name is never detected. Rows are never loaded on a guess; this only
          makes the drop visible.
        - **cross-category duplicate names** — the same name under multiple
          categories maps to inconsistent prefixes (and, for categories sharing an
          entity type like Vendor/Funder, one silently clobbers the other).
        - **conflicting IDs** — the same name within one category has multiple
          Internal IDs; only one is used, the rest are ignored.
        - **blank IDs** — a name with no Internal ID is detected but pseudonymizes
          to a flagged auto-id (advisory, not an error: this is supported behavior).
        - **duplicate IDs** — one Internal ID reused by different names within a
          category, so distinct names share one pseudonym.
        - **ambiguous common-word names** (advisory) — a single-token name that is
          also an ordinary English word (e.g. a funder literally named ``Across``)
          matches every plain-English occurrence of that word, not just the
          entity. Not an error in the data — the name may be genuinely correct —
          but worth a human look.
        """
        rows = self.rows()
        issues: list[QualityIssue] = []
        limit = self._EXAMPLE_LIMIT

        if self._load_error:
            issues.append(
                QualityIssue(
                    kind="unreadable_workbook",
                    severity=SEVERITY_WARNING,
                    title="The master list could not be opened",
                    detail=(
                        f"{self._load_error} No names are loaded, so only "
                        "names the language model spots are redacted."
                    ),
                    examples=[f"`{self._path.name}`"],
                    total=1,
                )
            )

        # Rows dropped at parse time. Listed first: these names are not
        # loaded at all, so nothing will detect them.
        if self._skipped:
            sheets = sorted({sheet for sheet, _ in self._skipped})
            items = [f"`{name}` (sheet {sheet})" for sheet, name in self._skipped]
            examples, total = cap_examples(items, limit)
            issues.append(
                QualityIssue(
                    kind="category_mismatch",
                    severity=SEVERITY_WARNING,
                    title=(
                        f"{len(self._skipped)} row(s) skipped because their "
                        "Category cell doesn't match"
                    ),
                    detail=(
                        "These names are not loaded and will not be detected. "
                        "Set each row's Category to its sheet's category "
                        f"(sheets: {', '.join(sheets)}), or add a Category "
                        "column if the sheet has none."
                    ),
                    examples=examples,
                    total=total,
                )
            )

        # Names with a non-ID " - " suffix: kept whole, short form matched too.
        dashed = [row for row in rows if row.short_name]
        if dashed:
            items = [
                f"`{row.name}` also matches `{row.short_name}` ({row.category})"
                for row in dashed
            ]
            examples, total = cap_examples(items, limit)
            issues.append(
                QualityIssue(
                    kind="dash_in_name",
                    severity=SEVERITY_INFO,
                    title=f"{len(dashed)} name(s) contain ' - '",
                    detail=(
                        "The full name is matched, and so is the part before "
                        "' - ' on its own. If that short part is an ordinary "
                        "word, it will be redacted wherever it appears; if the "
                        "dash marks an old ID, put the ID in Internal ID instead."
                    ),
                    examples=examples,
                    total=total,
                )
            )

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

        # (e) Single-token name that is also an ordinary English word (advisory).
        ambiguous: dict[str, list[str]] = {}
        for row in rows:
            for name in (row.name, row.short_name):
                if not name or " " in name.strip():
                    continue
                if name.strip().lower() in COMMON_ENGLISH_WORDS:
                    ambiguous.setdefault(row.category, []).append(name)
        ambiguous_total = sum(len(v) for v in ambiguous.values())
        if ambiguous_total:
            items = [
                f"`{name}` ({cat})"
                for cat, names in ambiguous.items()
                for name in names
            ]
            examples, total = cap_examples(items, limit)
            issues.append(
                QualityIssue(
                    kind="ambiguous_common_word",
                    severity=SEVERITY_INFO,
                    title=(
                        f"{ambiguous_total} name(s) are also ordinary English words"
                    ),
                    detail=(
                        "Every plain-English occurrence of the word will be "
                        "detected, not just the entity. Confirm this is intended "
                        "or make the name more distinctive."
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
        self._skipped = []
        self._load_error = None
        try:
            workbook = pd.read_excel(self._path, sheet_name=None, engine="openpyxl")
        except FileNotFoundError:
            return []
        except zipfile.BadZipFile:
            # openpyxl raises this for a truncated or non-xlsx file, and for a
            # password-protected one (Excel wraps those in an OLE container).
            self._load_error = (
                "It isn't a readable .xlsx file: it may be damaged, "
                "password-protected, or another format renamed to .xlsx."
            )
            return []
        except PermissionError:
            self._load_error = (
                "Access was denied. Close it in Excel (or wait for Box to "
                "finish syncing) and Refresh."
            )
            return []
        except (ValueError, OSError, KeyError):
            # Never echo the exception text: it can quote workbook content.
            self._load_error = "The workbook couldn't be read."
            return []

        rows: list[MasterRow] = []
        for category, sheet_name in self._category_sheets.items():
            if category not in self._categories:
                continue
            sheet_df = workbook.get(sheet_name)
            if sheet_df is None or sheet_df.empty:
                continue
            rows.extend(self._parse_sheet(category, sheet_name, sheet_df))
        return rows

    def _parse_sheet(
        self, expected_category: str, sheet_name: str, sheet_df: pd.DataFrame
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
                # Load the row only if its Category cell matches the sheet; a
                # blank cell, a missing column or a wording difference lands
                # here. Never silently: quality_report() lists every one,
                # since a name that isn't loaded is never detected.
                self._skipped.append((sheet_name, name))
                continue
            pseudonym = f"{prefix}-{id_value}" if id_value else None
            head = _SPACED_DASH.split(name, maxsplit=1)[0].strip()
            rows.append(
                MasterRow(
                    category,
                    name,
                    entity_type,
                    pseudonym,
                    internal_id=id_value,
                    short_name=head if head and head != name else None,
                )
            )
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
        name = _LEGACY_ID_SUFFIX.sub("", name)
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
