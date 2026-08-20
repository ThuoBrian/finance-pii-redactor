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
    source: DetectionSource = DetectionSource.MODEL,
) -> PiiDetection:
    """Build a minimal PiiDetection for rule tests."""
    return PiiDetection(
        entity_type=entity_type,
        span=Span(start, end),
        score=score,
        text="",
        source=source,
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


def test_dedupe_master_list_wins_over_longer_overlapping_model_span() -> None:
    """A curated master-list match must not lose to a longer model guess.

    Regression test for the "Brian Thuo - Kakamega" case: the model tags the
    whole hyphenated phrase as one PERSON entity, which overlaps and outspans
    the exact master-list match on the name alone. The curated match must win
    so the name still resolves to its stable ID instead of a flagged auto-id.
    """
    master_list_hit = _detection(0, 10, score=0.9, source=DetectionSource.MASTER_LIST)
    longer_model_hit = _detection(0, 25, score=0.85, source=DetectionSource.MODEL)
    kept = dedupe_overlapping([longer_model_hit, master_list_hit])
    assert kept == [master_list_hit]


def test_dedupe_master_list_wins_even_when_it_starts_later() -> None:
    """Master-list priority applies regardless of which span starts first."""
    model_hit = _detection(0, 15, score=0.6, source=DetectionSource.MODEL)
    master_list_hit = _detection(5, 15, score=0.9, source=DetectionSource.MASTER_LIST)
    kept = dedupe_overlapping([model_hit, master_list_hit])
    assert kept == [master_list_hit]


def test_dedupe_non_overlapping_master_list_and_model_both_kept() -> None:
    """Master-list priority only affects overlapping detections."""
    master_list_hit = _detection(0, 10, score=0.9, source=DetectionSource.MASTER_LIST)
    model_hit = _detection(20, 30, score=0.6, source=DetectionSource.MODEL)
    kept = dedupe_overlapping([model_hit, master_list_hit])
    assert set(kept) == {master_list_hit, model_hit}


def test_dedupe_custom_word_wins_over_overlapping_model_guess() -> None:
    """An ad-hoc custom word beats an overlapping model guess.

    It's still an explicit, exact match the user typed for this run, just
    not a curated one - stronger than a statistical guess, weaker than a
    curated master-list match (see the next test).
    """
    custom_hit = _detection(0, 10, score=1.0, source=DetectionSource.CUSTOM)
    model_hit = _detection(0, 25, score=0.85, source=DetectionSource.MODEL)
    kept = dedupe_overlapping([model_hit, custom_hit])
    assert kept == [custom_hit]


def test_dedupe_master_list_wins_over_overlapping_custom_word() -> None:
    """A curated master-list match still wins over an overlapping custom word."""
    master_list_hit = _detection(0, 10, score=0.9, source=DetectionSource.MASTER_LIST)
    custom_hit = _detection(0, 25, score=1.0, source=DetectionSource.CUSTOM)
    kept = dedupe_overlapping([custom_hit, master_list_hit])
    assert kept == [master_list_hit]


def test_dedupe_pattern_match_wins_over_overlapping_custom_word() -> None:
    """A pattern match (email/URL) beats an overlapping custom word.

    Both are deterministic, exact matches, but a regex-validated pattern
    match ranks above a same-run typed word (see the PATTERN tier in
    ``_SOURCE_PRIORITY``).
    """
    pattern_hit = _detection(0, 10, score=1.0, source=DetectionSource.PATTERN)
    custom_hit = _detection(0, 25, score=1.0, source=DetectionSource.CUSTOM)
    kept = dedupe_overlapping([custom_hit, pattern_hit])
    assert kept == [pattern_hit]


def test_dedupe_pattern_match_wins_over_overlapping_model_guess() -> None:
    """A pattern match beats an overlapping model guess, regardless of span."""
    pattern_hit = _detection(0, 10, score=1.0, source=DetectionSource.PATTERN)
    model_hit = _detection(0, 25, score=0.85, source=DetectionSource.MODEL)
    kept = dedupe_overlapping([model_hit, pattern_hit])
    assert kept == [pattern_hit]


def test_dedupe_master_list_wins_over_overlapping_pattern_match() -> None:
    """A curated master-list match still wins over an overlapping pattern match."""
    master_list_hit = _detection(0, 10, score=0.9, source=DetectionSource.MASTER_LIST)
    pattern_hit = _detection(0, 25, score=1.0, source=DetectionSource.PATTERN)
    kept = dedupe_overlapping([pattern_hit, master_list_hit])
    assert kept == [master_list_hit]
