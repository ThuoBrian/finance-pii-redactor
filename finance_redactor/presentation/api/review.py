"""Review payloads shared by every format.

The list order, the "why it was found" wording and the term keys come from
``presenters.review_terms``, so every format reviews the same way.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict

from fastapi import HTTPException

from finance_redactor.config import Settings
from finance_redactor.domain.entities import Finding
from finance_redactor.domain.pseudonyms import Assignment
from finance_redactor.presentation.presenters import (
    ENTITY_HELP,
    SOURCE_FILTERS,
    THRESHOLD_HELP,
    crosswalk_dataframe,
    entity_label,
    model_guess_count,
    review_summary,
    review_terms,
    term_key,
)
from finance_redactor.presentation.schemas import (
    EntityOut,
    MappingRowOut,
    ReviewRowOut,
    SourceFilterOut,
    TextOccurrenceOut,
    ThresholdOut,
)

# Typed words: generous limits that still stop a pasted document.
MAX_WORDS = 500
MAX_WORD_LENGTH = 200


def threshold_options(settings: Settings) -> ThresholdOut:
    """Return the confidence slider: capped where bank details stop being masked."""
    return ThresholdOut(
        default=settings.default_threshold,
        min=0.1,
        max=settings.max_threshold,
        step=0.05,
        help=THRESHOLD_HELP,
    )


def entity_options(settings: Settings) -> tuple[list[EntityOut], str]:
    """Return the kinds of information the user can hide, and their help text."""
    return [
        EntityOut(code=code, label=entity_label(code))
        for code in settings.supported_entities
    ], ENTITY_HELP


def checked_detection(
    settings: Settings, entities: Sequence[str], threshold: float
) -> list[str]:
    """Validate detection settings; return the entities, de-duplicated."""
    if not 0.1 <= threshold <= settings.max_threshold:
        # Above the cap, bank and payment details would stop being masked.
        raise HTTPException(422, "Confidence threshold is out of range.")
    chosen = list(dict.fromkeys(entities))
    if not chosen or set(chosen) - set(settings.supported_entities):
        raise HTTPException(422, "Choose at least one kind of information to hide.")
    return chosen


def checked_words(words: Sequence[str]) -> list[str]:
    """Return the typed words, stripped and without blanks, in order."""
    cleaned = [w.strip() for w in words if w.strip()]
    if len(cleaned) > MAX_WORDS or any(len(w) > MAX_WORD_LENGTH for w in cleaned):
        raise HTTPException(
            422,
            f"Add at most {MAX_WORDS} words or phrases, each up to "
            f"{MAX_WORD_LENGTH} characters.",
        )
    return list(dict.fromkeys(cleaned))


def text_occurrences(findings: list[Finding]) -> list[TextOccurrenceOut]:
    """Return every occurrence for a page- or paragraph-based format (1-based)."""
    return [
        TextOccurrenceOut(
            location=f.page + 1,
            key=term_key(f.detected_text),
            term=f.detected_text,
            kind=entity_label(f.entity_type),
        )
        for f in findings
    ]


def review_parts(
    findings: Sequence[Finding],
) -> tuple[list[ReviewRowOut], str, list[SourceFilterOut], bool]:
    """Return ``(rows, summary line, filter chips, no model guesses at all)``.

    Rows are one per distinct term, likeliest mistakes first. Built in one
    pass over the findings.
    """
    terms = review_terms(findings)
    rows = [ReviewRowOut(**asdict(t)) for t in terms]
    if not terms:
        return rows, "", [], True
    filters = [
        SourceFilterOut(
            label=label,
            source=source,
            count=sum(1 for t in terms if t.source == source),
        )
        for label, source in SOURCE_FILTERS.items()
    ]
    return (
        rows,
        review_summary(terms),
        [f for f in filters if f.count],
        model_guess_count(terms) == 0,
    )


def mapping_rows(crosswalk: list[Assignment]) -> list[MappingRowOut]:
    """Return the name -> code mapping for the screen, with readable kinds."""
    table = crosswalk_dataframe(crosswalk)
    return [
        MappingRowOut(
            original_name=str(row["Original name"]),
            kind=entity_label(str(row["Entity type"])),
            pseudonym=str(row["Pseudonym"]),
            flagged=row["Flagged"] == "yes",
            possible_match=str(row["Possible match"]),
        )
        for row in table.to_dict("records")
    ]


def crosswalk_csv(stem: str, crosswalk: list[Assignment]) -> tuple[bytes, str, str]:
    """Return the Excel/Word crosswalk CSV (real names, Confidential).

    404 when nothing was replaced: there is no mapping to give.
    """
    if not crosswalk:
        raise HTTPException(404, "No names were replaced, so there is no mapping.")
    csv = crosswalk_dataframe(crosswalk).to_csv(index=False)
    return csv.encode("utf-8"), f"{stem}_crosswalk.csv", "text/csv"


def checked_exclusions(
    requested: Sequence[str], findings: Sequence[Finding]
) -> frozenset[str]:
    """Return the requested keys, refusing any term this scan did not find.

    A key that matches nothing would do nothing, so it most likely means the
    client is out of step with the server; failing loudly beats a silent
    no-op on a redaction choice.
    """
    known = {term_key(f.detected_text) for f in findings}
    unknown = set(requested) - known
    if unknown:
        raise HTTPException(
            409, "The review is out of date. Reload the page and review again."
        )
    return frozenset(requested)
