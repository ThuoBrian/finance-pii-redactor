"""Tests for the Presidio-backed detector adapter.

These tests avoid loading the heavy spaCy model by mocking the AnalyzerEngine
construction. They cover the adapter-specific orchestration: dual-pass merging,
exact-span score preference, and translation to domain detections.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from presidio_analyzer import RecognizerResult

from finance_redactor.config import DEFAULT_SETTINGS
from finance_redactor.domain.entities import DetectionSource
from finance_redactor.infrastructure.detection.presidio_detector import PresidioEngine


@pytest.fixture
def engine() -> PresidioEngine:
    """Return a PresidioEngine whose underlying analyzer is a mock."""
    fake_analyzer = MagicMock()
    fake_nlp_engine = MagicMock()

    with patch(
        "finance_redactor.infrastructure.detection.presidio_detector.NlpEngineProvider"
    ) as provider_cls:
        provider_cls.return_value.create_engine.return_value = fake_nlp_engine
        with patch(
            "finance_redactor.infrastructure.detection.presidio_detector.AnalyzerEngine"
        ) as analyzer_cls:
            analyzer_cls.return_value = fake_analyzer
            return PresidioEngine(DEFAULT_SETTINGS)


def _result(
    entity_type: str = "PERSON",
    start: int = 0,
    end: int = 10,
    score: float = 0.5,
) -> RecognizerResult:
    """Build a minimal RecognizerResult for the mocked analyzer."""
    return RecognizerResult(
        entity_type=entity_type,
        start=start,
        end=end,
        score=score,
    )


def test_higher_score_wins_for_exact_span(engine: PresidioEngine) -> None:
    """When the same span is detected twice, the higher score is kept."""
    engine._analyzer.analyze.return_value = [
        _result(start=0, end=10, score=0.45),
        _result(start=0, end=10, score=0.85),
    ]

    detections = engine.analyze("Mary Smith", ["PERSON"], 0.35)

    assert len(detections) == 1
    assert detections[0].span.start == 0
    assert detections[0].span.end == 10
    assert detections[0].score == 0.85


def test_overlapping_spans_use_leftmost_longest_not_score(
    engine: PresidioEngine,
) -> None:
    """After exact-span dedupe, overlapping spans follow the domain rule."""
    engine._analyzer.analyze.return_value = [
        # Longer, lower-score span.
        _result(start=0, end=10, score=0.40),
        # Shorter, higher-score span fully inside the first.
        _result(start=0, end=5, score=0.90),
    ]

    detections = engine.analyze("Mary Smith", ["PERSON"], 0.35)

    assert len(detections) == 1
    assert detections[0].span.start == 0
    assert detections[0].span.end == 10
    assert detections[0].score == 0.40


def test_master_list_score_is_classified_as_master_list(engine: PresidioEngine) -> None:
    """A detection at the configured custom match score is marked master-list sourced."""
    engine._analyzer.analyze.return_value = [
        _result(start=0, end=10, score=DEFAULT_SETTINGS.custom_match_score)
    ]

    detections = engine.analyze("Mary Smith", ["PERSON"], 0.35)

    assert len(detections) == 1
    assert detections[0].source == DetectionSource.MASTER_LIST


def test_model_score_is_classified_as_model(engine: PresidioEngine) -> None:
    """A detection below or above the custom match score is marked model sourced."""
    engine._analyzer.analyze.return_value = [
        _result(start=0, end=10, score=DEFAULT_SETTINGS.custom_match_score - 0.1)
    ]

    detections = engine.analyze("Mary Smith", ["PERSON"], 0.35)

    assert len(detections) == 1
    assert detections[0].source == DetectionSource.MODEL
