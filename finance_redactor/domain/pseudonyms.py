"""Pseudonymization: map detected names to stable IDs.

The core of the tool's shift from redaction (``[PERSON]``) to pseudonymization
(``STF-10010``). A name in the master list always resolves to its curated ID, so
the same person/organization gets the same pseudonym across every cell, page, and
file — preserving the linkage needed for error-checking and fraud monitoring
while removing the real identity.

Framework-free: this is pure domain logic, unit-testable without Presidio,
pandas, or Streamlit.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace

from finance_redactor.domain.entities import CUSTOM_ENTITY_TYPE, PiiDetection
from finance_redactor.domain.fuzzy import closest_match
from finance_redactor.domain.rules import dedupe_overlapping

_WHITESPACE = re.compile(r"\s+")

# Label for one entity within one document, e.g. ``[001]``. Zero-padded to
# three digits so labels sort correctly in the mapping file; widens rather
# than truncating past 999 (``[1000]``).
_LABEL_PAD = 3


def format_label(ordinal: int) -> str:
    """Return the document-local label for the ``ordinal``-th distinct entity."""
    return f"[{ordinal:0{_LABEL_PAD}d}]"


def normalize(name: str) -> str:
    """Normalize a name for lookup: collapse whitespace, strip, casefold.

    Makes master-list matching robust to the case-insensitive recognizer and to
    minor spacing differences between the list and the document text.

    Deliberately does **not** fold accents. This is the *primary* master-list
    key, and folding it would merge genuinely distinct curated rows (``José``
    and ``Jose``) into one, silently mis-attributing an ID. Accent-tolerant
    matching belongs in :func:`fold`, which backs only the secondary,
    ambiguity-checked lookup in :class:`Pseudonymizer`. Keep the two separate.
    """
    return _WHITESPACE.sub(" ", name).strip().casefold()


def fold_diacritics(text: str) -> str:
    """Strip combining accent marks (``José`` -> ``Jose``), one char per input char.

    Each character is Unicode-decomposed (NFKD) on its own and reduced to its
    first non-combining component, falling back to the original character if
    decomposition yields none. This keeps the result the **same length** as
    ``text`` (mirroring :func:`recasing.recase_uppercase`'s length-preserving
    approach) so offsets found on a folded copy map back exactly onto the
    original - needed because many Latin American (and other) names carry
    accents (``José``, ``Muñoz``, ``André``) that a US/ASCII keyboard can't
    easily type, so a user typing the unaccented form into the "words to
    redact" box should still match the accented form in the document, and
    vice versa (e.g. an OCR pass that dropped accents).

    Lives here rather than in ``domain/custom_words.py`` (which imports it)
    so the detection path and the master-list lookup path fold identically.
    They used to differ, which meant a typed ``Jose Garcia`` could match
    ``José García`` in the document and then fail to resolve against a
    ``Jose Garcia`` master row - a silent miss with no error anywhere.
    """
    return "".join(
        next(
            (
                c
                for c in unicodedata.normalize("NFKD", ch)
                if not unicodedata.combining(c)
            ),
            ch,
        )
        for ch in text
    )


def fold(name: str) -> str:
    """Normalize *and* accent-fold, for the secondary name-only lookup."""
    return fold_diacritics(normalize(name))


def _with_display_name(entry: MasterEntry, fallback: str) -> MasterEntry:
    """Return ``entry`` with a non-empty ``display_name``.

    ``display_name`` is optional on :class:`MasterEntry`, so the reviewer hint
    falls back to the matched normalized/folded name rather than showing blank.
    """
    if entry.display_name:
        return entry
    return replace(entry, display_name=fallback)


@dataclass(frozen=True)
class MasterEntry:
    """A curated master-list mapping target for one normalized name.

    ``display_name`` (original casing, e.g. ``"Michael Sample"``) is optional and
    used only for the fuzzy-match reviewer hint (see ``Assignment.suggested_name``);
    it defaults to ``""`` for callers (e.g. existing tests) that don't need it.

    ``internal_id`` is the raw ``Internal ID`` cell (``"17728"``), carried
    separately from ``pseudonym`` (``"VND-17728"``) because the PDF mapping
    file needs the bare ID and splitting it back out of the pseudonym string
    is unsafe - ``"VND-17728"`` and ``"ORG-AUTO-3F9A1"`` have the same shape.
    Both fields describe the same row; change them together.
    """

    pseudonym: str
    category: str
    display_name: str = ""
    internal_id: str | None = None


@dataclass(frozen=True)
class Assignment:
    """The pseudonym assigned to one detected name.

    ``auto`` is True when the name was not found in the master list and a stable
    placeholder ID was generated instead (the UI flags these for review).

    ``suggested_*`` fields are populated only when ``auto`` is True and a
    typo-tolerant fuzzy match found a close curated name: a reviewer hint shown
    in the crosswalk, never applied automatically (see ``domain/fuzzy.py``).

    ``ordinal`` is this entity's position among the distinct entities found in
    one document (1-based), and :attr:`label` renders it as ``[001]``. That
    label is what the PDF flow writes into the document; ``pseudonym`` is
    **operator-facing only** there, because it embeds the master-list
    ``Internal ID`` and putting that in a document is the leak this scheme
    exists to close. Excel and Word still write ``pseudonym`` (see
    ``application/redact_excel.py`` and ``redact_docx.py``).

    ``ambiguous`` is True when a name-only lookup found two or more curated
    rows disagreeing on the ID, so none was applied - the entity is still
    redacted, but carries no ``internal_id`` and is surfaced for review.
    """

    original_name: str
    entity_type: str
    category: str
    pseudonym: str
    auto: bool
    ordinal: int = 0
    internal_id: str | None = None
    ambiguous: bool = False
    suggested_pseudonym: str | None = None
    suggested_name: str | None = None
    suggested_score: float | None = None

    @property
    def label(self) -> str:
        """The document-local label, e.g. ``[001]``."""
        return format_label(self.ordinal)


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
    ) -> None:
        """Wire the curated master map and the auto-id prefix table.

        ``fuzzy_threshold`` (a ``difflib`` similarity ratio, 0-1) gates the
        reviewer-hint suggestion offered on auto-ids; it never changes which
        pseudonym gets assigned (see ``domain/fuzzy.py``).
        """
        self._master_map = master_map
        self._auto_prefixes = auto_prefixes
        self._auto_hash_length = auto_hash_length
        self._fuzzy_threshold = fuzzy_threshold
        self._assignments: dict[tuple[str, str], Assignment] = {}
        self._candidates_by_type: dict[str, list[str]] = defaultdict(list)
        # Name-only index, consulted *only* for CUSTOM detections. Keyed on the
        # accent-folded name so it agrees with how domain/custom_words.py
        # matched in the first place.
        self._by_folded_name: dict[str, list[MasterEntry]] = defaultdict(list)
        for candidate_entity_type, normalized_name in master_map:
            self._candidates_by_type[candidate_entity_type].append(normalized_name)
            entry = master_map[(candidate_entity_type, normalized_name)]
            self._by_folded_name[fold(normalized_name)].append(entry)

    def assign(self, entity_type: str, text: str) -> Assignment:
        """Return the pseudonym for ``text``, generating one if not curated."""
        key = (entity_type, normalize(text))
        existing = self._assignments.get(key)
        if existing is not None:
            return existing

        ordinal = len(self._assignments) + 1
        entry = self._master_map.get(key)
        ambiguous = False
        if entry is None and entity_type == CUSTOM_ENTITY_TYPE:
            entry, ambiguous = self._resolve_by_name(key[1])

        if entry is not None:
            assignment = Assignment(
                original_name=text,
                entity_type=entity_type,
                category=entry.category,
                pseudonym=entry.pseudonym,
                auto=False,
                ordinal=ordinal,
                internal_id=entry.internal_id,
            )
        else:
            suggested_pseudonym = suggested_name = None
            suggested_score: float | None = None
            suggestion = self._closest(entity_type, key[1])
            if suggestion is not None:
                suggested_entry, suggested_score = suggestion
                suggested_pseudonym = suggested_entry.pseudonym
                suggested_name = suggested_entry.display_name
            assignment = Assignment(
                original_name=text,
                entity_type=entity_type,
                category="",
                pseudonym=self._auto_pseudonym(entity_type, key[1]),
                auto=True,
                ordinal=ordinal,
                internal_id=None,
                ambiguous=ambiguous,
                suggested_pseudonym=suggested_pseudonym,
                suggested_name=suggested_name,
                suggested_score=suggested_score,
            )
        self._assignments[key] = assignment
        return assignment

    def _resolve_by_name(self, normalized: str) -> tuple[MasterEntry | None, bool]:
        """Resolve a typed custom word by name alone. Returns (entry, ambiguous).

        A typed "word to redact" arrives as ``entity_type="CUSTOM"``, but the
        master map is keyed ``(PERSON|ORGANIZATION, name)``, so an exact-key
        lookup can never match it. This closes that gap for the PDF flow,
        where typed words are the only way to redact a name at all.

        Accent-folded (see :func:`fold`) so a typed ``Jose Garcia`` resolves
        against a ``José García`` row and vice versa, matching what
        ``domain/custom_words.py`` already does at detection time.

        If two or more curated rows disagree on the ID - the cross-category
        duplicate ``domain/quality.py`` warns about at load time, or two rows
        differing only by accent - this refuses rather than picking one.
        Guessing would write a coin-flip ID into a mapping file that carries
        no name to cross-check it against, and a wrong ID is undetectable
        downstream where an orphan is merely inconvenient.
        """
        candidates = self._by_folded_name.get(fold(normalized), ())
        if not candidates:
            return None, False
        distinct = {(c.internal_id, c.category) for c in candidates}
        if len(distinct) == 1:
            return candidates[0], False
        return None, True

    def _closest(
        self, entity_type: str, normalized: str
    ) -> tuple[MasterEntry, float] | None:
        """Find a typo-tolerant reviewer hint, or None."""
        if entity_type != CUSTOM_ENTITY_TYPE:
            suggestion = closest_match(
                normalized,
                self._candidates_by_type.get(entity_type, ()),
                self._fuzzy_threshold,
            )
            if suggestion is None:
                return None
            matched_normalized, score = suggestion
            matched = self._master_map[(entity_type, matched_normalized)]
            return _with_display_name(matched, matched_normalized), score

        # CUSTOM has no per-type candidate list, so use the name-only index.
        # Without this a typo'd typed word got no hint at all, because
        # _candidates_by_type["CUSTOM"] is always empty.
        suggestion = closest_match(
            fold(normalized), list(self._by_folded_name), self._fuzzy_threshold
        )
        if suggestion is None:
            return None
        matched_folded, score = suggestion
        entries = self._by_folded_name[matched_folded]
        if len({(e.internal_id, e.category) for e in entries}) != 1:
            return None
        return _with_display_name(entries[0], matched_folded), score

    def crosswalk(self) -> list[Assignment]:
        """Return every distinct assignment made so far, in label order.

        Ordered by ``ordinal`` because the mapping file is a lookup table: a
        reader holding ``[007]`` wants to find row 7. Flagged rows stay
        findable via the ``Flagged`` column rather than by being grouped.
        """
        return sorted(self._assignments.values(), key=lambda a: a.ordinal)

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
