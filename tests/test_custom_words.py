"""Tests for the ad-hoc "words to redact" matcher.

Pure domain logic, independent of Presidio/spaCy - runs without the language
model, matching the rest of the domain-layer test suite.
"""

from __future__ import annotations

from finance_redactor.domain.custom_words import find_custom_words
from finance_redactor.domain.entities import DetectionSource, Span


def test_finds_an_exact_case_insensitive_match() -> None:
    detections = find_custom_words(
        "Paid to JOHN SMITH for consulting.", ["John Smith"], 1.0
    )

    assert len(detections) == 1
    detection = detections[0]
    assert detection.text == "JOHN SMITH"
    assert detection.entity_type == "CUSTOM"
    assert detection.source == DetectionSource.CUSTOM
    assert detection.score == 1.0
    assert detection.span == Span(8, 18)


def test_does_not_match_inside_a_longer_word() -> None:
    detections = find_custom_words(
        "The category report is due. Bring your cat.", ["cat"], 1.0
    )

    assert len(detections) == 1
    assert detections[0].text == "cat"


def test_matches_a_multi_word_phrase_with_flexible_whitespace() -> None:
    text = "Reference: Project   Nightingale is confidential."

    detections = find_custom_words(text, ["Project Nightingale"], 1.0)

    assert len(detections) == 1
    assert detections[0].text == "Project   Nightingale"


def test_blank_and_whitespace_only_lines_are_skipped() -> None:
    detections = find_custom_words("Some text here.", ["", "   ", "\t"], 1.0)

    assert detections == []


def test_finds_every_occurrence_of_a_word() -> None:
    detections = find_custom_words("Alpha said hi. Later, Alpha left.", ["Alpha"], 1.0)

    assert len(detections) == 2
    assert [d.span for d in detections] == [Span(0, 5), Span(22, 27)]


def test_multiple_distinct_words_are_all_found() -> None:
    detections = find_custom_words(
        "Case 4471-B involves Project Zeta.", ["Case 4471-B", "Project Zeta"], 1.0
    )

    texts = {d.text for d in detections}
    assert texts == {"Case 4471-B", "Project Zeta"}
