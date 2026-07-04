"""Unit tests for the framework-free pseudonymization logic."""

from __future__ import annotations

from finance_redactor.domain.entities import DetectionSource, PiiDetection, Span
from finance_redactor.domain.pseudonyms import (
    MasterEntry,
    Pseudonymizer,
    apply_replacements,
    normalize,
)

_AUTO_PREFIXES = {"PERSON": "PSN", "ORGANIZATION": "ORG"}


def _detection(start: int, end: int, text: str, entity: str = "PERSON") -> PiiDetection:
    return PiiDetection(
        entity_type=entity,
        span=Span(start, end),
        score=0.9,
        text=text,
        source=DetectionSource.MASTER_LIST,
    )


def test_master_hit_returns_curated_id():
    master = {("PERSON", normalize("Brian Thuo")): MasterEntry("STF-91345", "Staff")}
    p = Pseudonymizer(master, _AUTO_PREFIXES)

    assignment = p.assign("PERSON", "brian  thuo")  # case/space insensitive

    assert assignment.pseudonym == "STF-91345"
    assert assignment.category == "Staff"
    assert assignment.auto is False


def test_unknown_name_gets_stable_auto_id():
    a = Pseudonymizer({}, _AUTO_PREFIXES).assign("PERSON", "Jane Doe")
    b = Pseudonymizer({}, _AUTO_PREFIXES).assign("PERSON", "JANE   doe")

    assert a.auto is True
    assert a.pseudonym.startswith("PSN-AUTO-")
    # Deterministic across instances and insensitive to case/whitespace.
    assert a.pseudonym == b.pseudonym


def test_auto_prefix_follows_entity_type():
    p = Pseudonymizer({}, _AUTO_PREFIXES)
    assert p.assign("ORGANIZATION", "Acme Co").pseudonym.startswith("ORG-AUTO-")


def test_repeated_name_is_consistent_and_recorded_once():
    master = {("PERSON", normalize("Brian Thuo")): MasterEntry("STF-91345", "Staff")}
    p = Pseudonymizer(master, _AUTO_PREFIXES)

    first = p.assign("PERSON", "Brian Thuo")
    second = p.assign("PERSON", "brian thuo")

    assert first.pseudonym == second.pseudonym
    assert len(p.crosswalk()) == 1


def test_apply_replacements_handles_multiple_and_overlap():
    text = "Brian Thuo paid Safaricom"
    detections = [
        _detection(0, 10, "Brian Thuo"),
        _detection(16, 25, "Safaricom", entity="ORGANIZATION"),
        # Overlapping shorter span that should be dropped by dedupe.
        _detection(0, 5, "Brian"),
    ]
    master = {
        ("PERSON", normalize("Brian Thuo")): MasterEntry("STF-91345", "Staff"),
        ("ORGANIZATION", normalize("Safaricom")): MasterEntry("VND-1045", "Vendor"),
    }
    p = Pseudonymizer(master, _AUTO_PREFIXES)

    result = apply_replacements(
        text, detections, lambda d: p.assign(d.entity_type, d.text).pseudonym
    )

    assert result == "STF-91345 paid VND-1045"


def test_apply_replacements_preserves_offsets_right_to_left():
    text = "aaa NAME bbb NAME ccc"
    detections = [_detection(4, 8, "NAME"), _detection(13, 17, "NAME")]
    p = Pseudonymizer({}, _AUTO_PREFIXES)

    result = apply_replacements(
        text, detections, lambda d: p.assign(d.entity_type, d.text).pseudonym
    )

    # Both occurrences of the same name collapse to one pseudonym.
    pseudonym = p.assign("PERSON", "NAME").pseudonym
    assert result == f"aaa {pseudonym} bbb {pseudonym} ccc"
