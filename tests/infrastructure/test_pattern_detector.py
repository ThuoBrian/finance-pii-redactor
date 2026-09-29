"""Tests for the spaCy-free email/URL detector used by the PDF flow.

The whole point of ``PatternDetector`` is to detect emails/URLs without ever
loading the heavy ``en_core_web_lg`` spaCy model - these tests prove that
directly (by construction) rather than assuming it, since a subtle Presidio
default-substitution behavior can silently reintroduce the very model load
this detector exists to avoid (see the module docstring on
``pattern_detector.py`` for how that was diagnosed).
"""

from __future__ import annotations

import sys

from finance_redactor.domain.entities import DetectionSource
from finance_redactor.infrastructure.detection.custom_recognizer import (
    build_custom_recognizers,
)
from finance_redactor.infrastructure.detection.pattern_detector import (
    PatternDetector,
)


def test_construction_never_loads_the_spacy_model() -> None:
    """Building the detector must not pull ``en_core_web_lg`` into memory.

    Regression guard for the bug where ``AnalyzerEngine(nlp_engine=None)``
    treats ``None`` as "not provided" and silently builds and loads its own
    default (spaCy-backed) engine instead.
    """
    PatternDetector()
    assert not any("en_core_web_lg" in name for name in sys.modules)


def test_detects_email_address() -> None:
    """A plain email address is detected with a high score."""
    detector = PatternDetector()
    text = "Please contact jane.doe@example.com for the invoice."
    results = detector.analyze(text, ["EMAIL_ADDRESS", "URL"], threshold=0.4)

    assert len(results) == 1
    assert results[0].entity_type == "EMAIL_ADDRESS"
    assert results[0].text == "jane.doe@example.com"
    assert results[0].source == DetectionSource.PATTERN


def test_detects_url() -> None:
    """A plain website URL is detected."""
    detector = PatternDetector()
    text = "See https://example.org/report for details."
    results = detector.analyze(text, ["EMAIL_ADDRESS", "URL"], threshold=0.4)

    assert len(results) == 1
    assert results[0].entity_type == "URL"
    assert results[0].text == "https://example.org/report"
    assert results[0].source == DetectionSource.PATTERN


def test_email_and_surrounding_url_like_text_do_not_double_count() -> None:
    """An email's domain isn't also reported as a separate, overlapping URL."""
    detector = PatternDetector()
    text = "Reach jane.doe@example.com anytime."
    results = detector.analyze(text, ["EMAIL_ADDRESS", "URL"], threshold=0.4)

    assert len(results) == 1
    assert results[0].text == "jane.doe@example.com"


def test_empty_text_returns_no_detections() -> None:
    """Blank/whitespace-only text is a cheap no-op, not an analyzer call."""
    detector = PatternDetector()
    assert detector.analyze("   ", ["EMAIL_ADDRESS", "URL"], threshold=0.4) == []


def test_no_match_returns_empty_list() -> None:
    """Ordinary text with no email or URL yields no detections."""
    detector = PatternDetector()
    text = "Invoice number 4471 was paid in full."
    assert detector.analyze(text, ["EMAIL_ADDRESS", "URL"], threshold=0.4) == []


def test_entities_filter_is_respected() -> None:
    """Requesting only EMAIL_ADDRESS suppresses a URL match in the same text."""
    detector = PatternDetector()
    text = "Email jane@example.com or visit https://example.org"
    results = detector.analyze(text, ["EMAIL_ADDRESS"], threshold=0.4)

    assert [r.entity_type for r in results] == ["EMAIL_ADDRESS"]


# --- Curated master-list names -----------------------------------------------
#
# Added after a PDF containing a name that *was* on the master list came back
# with only its email addresses redacted. Excluding spaCy was meant to keep
# statistical guessing out of the PDF flow, not to drop exact matching against
# the curated list.

_ALL = ["EMAIL_ADDRESS", "URL", "PERSON", "ORGANIZATION"]


def _curated_detector() -> PatternDetector:
    return PatternDetector(
        "en",
        master_list_recognizers=build_custom_recognizers(
            ["Jane Doe"], ["Care Organisation"], 0.9
        ),
    )


def test_detects_a_curated_person_without_it_being_typed_in() -> None:
    """A master-list name is found with nothing in the words-to-redact box."""
    detections = _curated_detector().analyze("Paid to Jane Doe today.", _ALL, 0.4)

    found = {(d.entity_type, d.text) for d in detections}
    assert ("PERSON", "Jane Doe") in found


def test_detects_a_curated_organization_alongside_an_email() -> None:
    detections = _curated_detector().analyze(
        "Care Organisation, billing@example.org", _ALL, 0.4
    )

    found = {(d.entity_type, d.text) for d in detections}
    assert ("ORGANIZATION", "Care Organisation") in found
    assert ("EMAIL_ADDRESS", "billing@example.org") in found


def test_curated_hits_are_attributed_to_the_master_list() -> None:
    """The source drives overlap priority in ``dedupe_overlapping``.

    Attributed by entity type rather than by score: only the master-list
    recognizer can emit PERSON/ORGANIZATION from this registry, so a score
    comparison (which PresidioEngine needs, because spaCy emits these too)
    would be a needless coincidence to rely on here.
    """
    detections = _curated_detector().analyze(
        "Jane Doe at billing@example.org", _ALL, 0.4
    )

    by_type = {d.entity_type: d.source for d in detections}
    assert by_type["PERSON"] is DetectionSource.MASTER_LIST
    assert by_type["EMAIL_ADDRESS"] is DetectionSource.PATTERN


def test_a_name_not_on_the_master_list_is_still_not_detected() -> None:
    """SpaCy stays out, so an uncurated name needs the words box.

    This is the boundary of the change: deterministic matching only. If this
    ever starts passing, statistical guessing has crept into the PDF flow.
    """
    detections = _curated_detector().analyze("Paid to Someone Uncurated.", _ALL, 0.4)

    assert detections == []


def test_without_recognizers_it_stays_an_email_url_detector() -> None:
    """The default construction is unchanged, which is what most callers want."""
    detections = PatternDetector("en").analyze("Paid to Jane Doe today.", _ALL, 0.4)

    assert detections == []
