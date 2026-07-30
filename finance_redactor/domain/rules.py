"""Pure business rules over domain entities.

Extracted from where they were previously buried (the dedup loop inside
``redact_pdf``, the ``score == 0.9`` checks duplicated across flows) so they are
named, reusable, and unit-testable without any framework.
"""

from __future__ import annotations

from collections.abc import Iterable

from finance_redactor.domain.entities import DetectionSource, PiiDetection, Span


def classify_source(score: float, custom_match_score: float) -> DetectionSource:
    """Classify a detection as coming from the master list or the model.

    A score exactly equal to the master-list match score is attributed to the
    master list (those names are matched by the custom recognizer); everything
    else is attributed to the model.
    """
    return (
        DetectionSource.MASTER_LIST
        if score == custom_match_score
        else DetectionSource.MODEL
    )


def dedupe_overlapping(detections: Iterable[PiiDetection]) -> list[PiiDetection]:
    """Remove overlapping detections.

    A master-list-sourced detection (an exact match against the curated
    vocabulary) always wins over an overlapping model-sourced detection,
    regardless of span length: a curated match is a stronger signal than a
    statistical guess. Without this, a longer spaCy guess that merely happens
    to contain a curated name (e.g. the model tagging ``"Brian Thuo -
    Kakamega"`` as one entity, which contains and outspans the master-list
    match ``"Brian Thuo"``) would win on length alone, and the name would
    resolve to a flagged auto-id instead of its curated one. Within the same
    source, leftmost wins; ties break to the longest span. This is the exact
    algorithm the PDF flow used inline, now isolated and reusable.
    """
    ordered = sorted(
        detections,
        key=lambda d: (
            d.source != DetectionSource.MASTER_LIST,
            d.span.start,
            -d.span.end,
        ),
    )
    kept: list[PiiDetection] = []
    used: list[Span] = []
    for detection in ordered:
        if any(detection.span.overlaps(span) for span in used):
            continue
        used.append(detection.span)
        kept.append(detection)
    return kept
