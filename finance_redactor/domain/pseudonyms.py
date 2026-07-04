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
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from finance_redactor.domain.entities import PiiDetection
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
    """A curated master-list mapping target for one normalized name."""

    pseudonym: str
    category: str


@dataclass(frozen=True)
class Assignment:
    """The pseudonym assigned to one detected name.

    ``auto`` is True when the name was not found in the master list and a stable
    placeholder ID was generated instead (the UI flags these for review).
    """

    original_name: str
    entity_type: str
    category: str
    pseudonym: str
    auto: bool


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
    ) -> None:
        """Wire the curated master map and the auto-id prefix table."""
        self._master_map = master_map
        self._auto_prefixes = auto_prefixes
        self._auto_hash_length = auto_hash_length
        self._assignments: dict[tuple[str, str], Assignment] = {}

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
            assignment = Assignment(
                original_name=text,
                entity_type=entity_type,
                category="",
                pseudonym=self._auto_pseudonym(entity_type, key[1]),
                auto=True,
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
