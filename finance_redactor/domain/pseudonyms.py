"""Pseudonymization: map detected names to stable IDs.

The core of the tool's shift from redaction (``[PERSON]``) to pseudonymization
(``STF-91345``). A name in the master list always resolves to its curated ID, so
the same person/organization gets the same pseudonym across every cell, page, and
file — preserving the linkage needed for error-checking and fraud monitoring
while removing the real identity.

Framework-free: this is pure domain logic, unit-testable without Presidio,
pandas, or Streamlit.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from finance_redactor.domain.entities import PiiDetection
from finance_redactor.domain.fuzzy import closest_match
from finance_redactor.domain.rules import dedupe_overlapping

_WHITESPACE = re.compile(r"\s+")


def normalize(name: str) -> str:
    """Normalize a name for lookup: collapse whitespace, strip, casefold.

    Makes master-list matching robust to the case-insensitive recognizer and to
    minor spacing differences between the list and the document text.
    """
    return _WHITESPACE.sub(" ", name).strip().casefold()


@dataclass(frozen=True)
class MasterEntry:
    """A curated master-list mapping target for one normalized name.

    ``display_name`` (original casing, e.g. ``"Michael Mugo"``) is optional and
    used only for the fuzzy-match reviewer hint (see ``Assignment.suggested_name``);
    it defaults to ``""`` for callers (e.g. existing tests) that don't need it.
    """

    pseudonym: str
    category: str
    display_name: str = ""


@dataclass(frozen=True)
class Assignment:
    """The pseudonym assigned to one detected name.

    ``auto`` is True when the name was not found in the master list and a stable
    placeholder ID was generated instead (the UI flags these for review).

    ``suggested_*`` fields are populated only when ``auto`` is True and a
    typo-tolerant fuzzy match found a close curated name: a reviewer hint shown
    in the crosswalk, never applied automatically (see ``domain/fuzzy.py``).
    ``suggested_category`` is surfaced separately from ``suggested_name`` so a
    reviewer can see when the suggestion comes from a *different* category than
    the one they were expecting (e.g. a Vendor's closest match turns out to be a
    Funder) — the candidate pool is scoped by ``entity_type`` only, since
    Vendor/Funder both detect as ORGANIZATION and the flagged name's own
    category is, by definition, not yet known.
    """

    original_name: str
    entity_type: str
    category: str
    pseudonym: str
    auto: bool
    suggested_pseudonym: str | None = None
    suggested_name: str | None = None
    suggested_score: float | None = None
    suggested_category: str | None = None


def build_candidate_index(
    master_map: Mapping[tuple[str, str], MasterEntry],
) -> dict[str, list[str]]:
    """Group ``master_map``'s normalized names by entity type for fuzzy matching.

    This is the pool :func:`~finance_redactor.domain.fuzzy.closest_match` scans
    per flagged auto-id. Building it is a full pass over every curated name and
    alias variant (tens of thousands of entries against the real master list),
    so callers that process many files against the same master list (the
    composition root) should build this once per master-list load and reuse it
    across ``Pseudonymizer`` instances rather than letting each instance rebuild
    it from scratch (see ``docs/GOTCHA.md``).
    """
    candidates_by_type: dict[str, list[str]] = defaultdict(list)
    for candidate_entity_type, normalized_name in master_map:
        candidates_by_type[candidate_entity_type].append(normalized_name)
    return candidates_by_type


class Pseudonymizer:
    """Assigns stable pseudonyms to detected names, recording a crosswalk.

    Construct one per file/run: it caches assignments so repeated names within
    the run return the identical pseudonym, and exposes the accumulated
    name-to-pseudonym crosswalk via :meth:`crosswalk`.
    """

    def __init__(
        self,
        master_map: Mapping[tuple[str, str], MasterEntry],
        auto_prefixes: Mapping[str, str],
        auto_hash_length: int = 5,
        fuzzy_threshold: float = 0.84,
        candidates_by_type: Mapping[str, list[str]] | None = None,
    ) -> None:
        """Wire the curated master map and the auto-id prefix table.

        ``fuzzy_threshold`` (a ``difflib`` similarity ratio, 0-1) gates the
        reviewer-hint suggestion offered on auto-ids; it never changes which
        pseudonym gets assigned (see ``domain/fuzzy.py``).

        ``candidates_by_type`` is the fuzzy-match candidate index normally built
        once per master-list load by :func:`build_candidate_index` and passed in
        by the composition root, so repeated runs against an unchanged master
        list don't repeat that pass (see ``docs/GOTCHA.md``). When omitted (e.g.
        in tests that construct a ``Pseudonymizer`` directly), it is derived from
        ``master_map`` here instead.
        """
        self._master_map = master_map
        self._auto_prefixes = auto_prefixes
        self._auto_hash_length = auto_hash_length
        self._fuzzy_threshold = fuzzy_threshold
        self._assignments: dict[tuple[str, str], Assignment] = {}
        self._candidates_by_type = (
            candidates_by_type
            if candidates_by_type is not None
            else build_candidate_index(master_map)
        )

    def assign(self, entity_type: str, text: str) -> Assignment:
        """Return the pseudonym for ``text``, generating one if not curated."""
        key = (entity_type, normalize(text))
        existing = self._assignments.get(key)
        if existing is not None:
            return existing

        entry = self._master_map.get(key)
        if entry is not None:
            assignment = Assignment(
                original_name=text,
                entity_type=entity_type,
                category=entry.category,
                pseudonym=entry.pseudonym,
                auto=False,
            )
        else:
            suggested_pseudonym = suggested_name = suggested_category = None
            suggested_score: float | None = None
            suggestion = closest_match(
                key[1],
                self._candidates_by_type.get(entity_type, ()),
                self._fuzzy_threshold,
            )
            if suggestion is not None:
                matched_normalized, suggested_score = suggestion
                matched_entry = self._master_map[(entity_type, matched_normalized)]
                suggested_pseudonym = matched_entry.pseudonym
                suggested_name = matched_entry.display_name or matched_normalized
                # Surfaced separately (not folded into suggested_name) so a
                # reviewer can immediately see when the candidate pool - shared
                # across categories with the same entity_type, e.g. Vendor and
                # Funder both detect as ORGANIZATION - matched a name from a
                # category other than the one they expected.
                suggested_category = matched_entry.category
            assignment = Assignment(
                original_name=text,
                entity_type=entity_type,
                category="",
                pseudonym=self._auto_pseudonym(entity_type, key[1]),
                auto=True,
                suggested_pseudonym=suggested_pseudonym,
                suggested_name=suggested_name,
                suggested_score=suggested_score,
                suggested_category=suggested_category,
            )
        self._assignments[key] = assignment
        return assignment

    def crosswalk(self) -> list[Assignment]:
        """Return every distinct assignment made so far (curated first, then auto)."""
        return sorted(
            self._assignments.values(),
            key=lambda a: (a.auto, a.pseudonym),
        )

    def _auto_pseudonym(self, entity_type: str, normalized: str) -> str:
        prefix = self._auto_prefixes.get(entity_type) or entity_type[:3].upper()
        digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()
        return f"{prefix}-AUTO-{digest[: self._auto_hash_length].upper()}"


def apply_replacements(
    text: str,
    detections: Iterable[PiiDetection],
    resolve: Callable[[PiiDetection], str],
) -> str:
    """Replace each detected span in ``text`` with ``resolve(detection)``.

    Overlapping detections are first resolved with :func:`dedupe_overlapping`
    (leftmost/longest wins), then replacements are applied right-to-left so each
    edit leaves the offsets of not-yet-applied spans intact.
    """
    kept = dedupe_overlapping(detections)
    for detection in sorted(kept, key=lambda d: d.span.start, reverse=True):
        replacement = resolve(detection)
        text = text[: detection.span.start] + replacement + text[detection.span.end :]
    return text
