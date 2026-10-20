"""Tests for the review-table hints: made-up terms only."""

from __future__ import annotations

import pytest

from finance_redactor.domain.entities import DetectionSource
from finance_redactor.domain.review_hints import (
    ALL_CAPS,
    ONE_WORD_ORGANIZATION,
    ORDINARY_WORD,
    review_hint,
)

MODEL = DetectionSource.MODEL


@pytest.mark.parametrize(
    ("text", "entity_type", "expected"),
    [
        ("Across", "ORGANIZATION", ORDINARY_WORD),
        ("the", "PERSON", ORDINARY_WORD),
        ("TOTAL AMOUNT", "ORGANIZATION", ALL_CAPS),
        ("USD", "ORGANIZATION", ALL_CAPS),
        ("Salaries", "ORGANIZATION", ONE_WORD_ORGANIZATION),
        ("Jane Doe", "PERSON", ""),
        ("Acme Supplies", "ORGANIZATION", ""),
        ("Jane", "PERSON", ""),
    ],
)
def test_model_guesses_get_a_hint_only_when_there_is_a_reason(
    text: str, entity_type: str, expected: str
) -> None:
    assert review_hint(text, entity_type, MODEL) == expected


@pytest.mark.parametrize(
    "source",
    [DetectionSource.MASTER_LIST, DetectionSource.CUSTOM, DetectionSource.PATTERN],
)
def test_deliberate_or_rule_based_detections_are_never_hinted(
    source: DetectionSource,
) -> None:
    """Curated names and typed words were put there on purpose."""
    assert review_hint("Across", "ORGANIZATION", source) == ""
    assert review_hint("USD", "ORGANIZATION", source) == ""
