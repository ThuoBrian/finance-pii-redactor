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


def test_unaccented_typed_word_matches_accented_text() -> None:
    """A US/ASCII keyboard can't easily type accents - typing the plain form
    (``Jose Garcia``) must still find the accented spelling in the document.
    """
    detections = find_custom_words(
        "Signed by José García on file.", ["Jose Garcia"], 1.0
    )

    assert len(detections) == 1
    # The original, accented spelling is preserved in the reported detection.
    assert detections[0].text == "José García"


def test_accented_typed_word_matches_unaccented_text() -> None:
    """The reverse direction also matches - e.g. an OCR pass that dropped accents."""
    detections = find_custom_words(
        "Signed by Jose Garcia on file.", ["José García"], 1.0
    )

    assert len(detections) == 1
    assert detections[0].text == "Jose Garcia"


def test_accent_insensitive_matching_still_respects_word_boundaries() -> None:
    detections = find_custom_words("Muñoznik signed the form.", ["Munoz"], 1.0)

    assert detections == []
