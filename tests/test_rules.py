"""Tests for pure domain rules.

These rules operate on framework-free entities and are independent of Presidio,
pandas, or Streamlit.
"""

from __future__ import annotations

from finance_redactor.domain.entities import DetectionSource, PiiDetection, Span
from finance_redactor.domain.rules import classify_source, dedupe_overlapping


def _detection(
    start: int,
    end: int,
    entity_type: str = "PERSON",
    score: float = 0.5,
) -> PiiDetection:
    """Build a minimal PiiDetection for rule tests."""
    return PiiDetection(
        entity_type=entity_type,
        span=Span(start, end),
        score=score,
        text="",
        source=DetectionSource.MODEL,
    )


def test_classify_source_master_list_exact_score() -> None:
    """A detection at the configured custom match score is master-list sourced."""
    assert classify_source(0.9, custom_match_score=0.9) == DetectionSource.MASTER_LIST


def test_classify_source_model_when_score_differs() -> None:
    """Any score not exactly equal to the custom match score is model sourced."""
    assert classify_source(0.89, custom_match_score=0.9) == DetectionSource.MODEL
    assert classify_source(0.91, custom_match_score=0.9) == DetectionSource.MODEL


def test_dedupe_keeps_non_overlapping_detections() -> None:
    """Detections that do not overlap are all retained."""
    detections = [
        _detection(0, 4),
        _detection(10, 14),
        _detection(20, 24),
    ]
    kept = dedupe_overlapping(detections)
    assert len(kept) == 3


def test_dedupe_keeps_leftmost_longest_for_overlaps() -> None:
    """When spans overlap, the leftmost detection wins; ties go to the longest."""
    detections = [
        # Starts first and is longest.
        _detection(0, 10, score=0.40),
        # Same start, shorter.
        _detection(0, 5, score=0.90),
        # Starts later, overlaps.
        _detection(8, 15, score=0.80),
    ]
    kept = dedupe_overlapping(detections)
    spans = [d.span for d in kept]
    assert spans == [Span(0, 10)]


def test_dedupe_tie_on_start_prefers_longest_span() -> None:
    """Two detections starting at the same position keep the longer one."""
    detections = [
        _detection(0, 10),
        _detection(0, 6),
    ]
    kept = dedupe_overlapping(detections)
    assert len(kept) == 1
    assert kept[0].span == Span(0, 10)
