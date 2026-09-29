"""Tests for the Excel scan use case, focused on the unique-value dedup path.

Framework-free: a fake ``PiiDetector`` stands in for Presidio/spaCy, so these run
without the language model (matching the rest of the suite).
"""

from __future__ import annotations

import pandas as pd

from finance_redactor.application.redact_excel import RedactExcelService
from finance_redactor.config import DEFAULT_SETTINGS
from finance_redactor.domain.entities import DetectionSource, PiiDetection, Span


class CountingDetector:
    """Fake detector: flags the literal ``John`` and records every call."""

    def __init__(self) -> None:
        """Start with an empty call log."""
        self.calls: list[str] = []

    def analyze(
        self, text: str, entities: list[str], threshold: float
    ) -> list[PiiDetection]:
        """Record the call and return a PERSON hit when ``John`` is present."""
        self.calls.append(text)
        idx = text.find("John")
        if idx == -1:
            return []
        return [
            PiiDetection(
                entity_type="PERSON",
                span=Span(idx, idx + 4),
                score=0.99,
                text="John",
                source=DetectionSource.MODEL,
            )
        ]


def _service(detector: CountingDetector) -> RedactExcelService:
    return RedactExcelService(
        detector,
        master_map={},
        auto_prefixes={"PERSON": "PSN"},
        fixed_masks=DEFAULT_SETTINGS.fixed_masks,
    )


def test_scan_analyzes_each_unique_value_once():
    detector = CountingDetector()
    df = pd.DataFrame(
        {"notes": ["John paid", "John paid", "no name", "John paid", "no name"]}
    )

    result = _service(detector).scan(df, ["notes"], ["PERSON"], 0.35)

    # Five rows, two distinct strings -> the detector runs exactly twice.
    assert detector.calls == ["John paid", "no name"]
    # A finding for every row whose value contained a name; none for the rest.
    assert [f.row for f in result.findings] == [0, 1, 3]
    assert result.entity_count == 3


def test_scan_reports_progress_over_unique_values():
    detector = CountingDetector()
    df = pd.DataFrame({"a": ["John", "John", "x"], "b": ["y", "John", "y"]})
    seen: list[tuple[int, int]] = []

    _service(detector).scan(
        df, ["a", "b"], ["PERSON"], 0.35, on_progress=lambda d, t: seen.append((d, t))
    )

    # Distinct values across both columns: "John", "x", "y" -> total 3.
    assert seen == [(1, 3), (2, 3), (3, 3)]


def test_scan_skips_missing_columns_and_scans_across_columns():
    detector = CountingDetector()
    df = pd.DataFrame({"a": ["John"], "b": ["nothing"]})

    result = _service(detector).scan(df, ["a", "b", "missing"], ["PERSON"], 0.35)

    assert [(f.row, f.column) for f in result.findings] == [(0, "a")]


# --- redact(), and the exclusion filter on it --------------------------------
#
# redact() had no test before the deselect control was added; these are the
# first, so they also pin the basic scan -> redact cycle.


def test_redact_replaces_detected_names_in_place():
    """The baseline redact() behaviour these exclusion tests build on."""
    detector = CountingDetector()
    df = pd.DataFrame({"notes": ["John paid", "no name"]})
    service = _service(detector)
    scan = service.scan(df, ["notes"], ["PERSON"], 0.35)

    redacted, crosswalk = service.redact(df, scan, ["notes"])

    assert "John" not in redacted.at[0, "notes"]
    assert redacted.at[1, "notes"] == "no name"
    assert [a.original_name for a in crosswalk] == ["John"]


def test_excluded_term_is_left_alone_by_redact():
    """Unticking a false positive leaves the cell untouched."""
    detector = CountingDetector()
    df = pd.DataFrame({"notes": ["John paid"]})
    service = _service(detector)
    scan = service.scan(df, ["notes"], ["PERSON"], 0.35)

    redacted, crosswalk = service.redact(
        df, scan, ["notes"], exclude=frozenset({"john"})
    )

    assert redacted.at[0, "notes"] == "John paid"
    assert crosswalk == []


def test_reapplying_with_a_different_exclusion_never_rescans():
    """Why scan and redact are separate: a tick change costs no detection.

    If this breaks, changing a tick box in the Excel view starts reloading
    spaCy on every click.
    """
    detector = CountingDetector()
    df = pd.DataFrame({"notes": ["John paid"]})
    service = _service(detector)
    scan = service.scan(df, ["notes"], ["PERSON"], 0.35)
    calls_after_scan = list(detector.calls)

    service.redact(df, scan, ["notes"])
    service.redact(df, scan, ["notes"], exclude=frozenset({"john"}))

    assert detector.calls == calls_after_scan


class _AccountDetector:
    """Fake detector: flags any all-digit cell as a Kenyan bank account."""

    def analyze(
        self, text: str, entities: list[str], threshold: float
    ) -> list[PiiDetection]:
        """Return one KE_BANK_ACCOUNT hit spanning an all-digit ``text``."""
        if not text.isdigit():
            return []
        return [
            PiiDetection(
                entity_type="KE_BANK_ACCOUNT",
                span=Span(0, len(text)),
                score=0.85,
                text=text,
                source=DetectionSource.PATTERN,
            )
        ]


def test_bank_detail_is_masked_and_kept_out_of_the_crosswalk() -> None:
    df = pd.DataFrame({"Account": ["0123456789"]})
    service = _service(_AccountDetector())
    scan = service.scan(df, ["Account"], ["KE_BANK_ACCOUNT"], 0.35)

    redacted, crosswalk = service.redact(df, scan, ["Account"])

    assert redacted.at[0, "Account"] == "[ACCOUNT]"
    assert crosswalk == []


def test_mask_can_be_written_into_an_integer_column() -> None:
    # pandas refuses a string in an int64 column; redact must widen it first.
    df = pd.DataFrame({"Account": [123456789012, 987654321098]})
    service = _service(_AccountDetector())
    scan = service.scan(df, ["Account"], ["KE_BANK_ACCOUNT"], 0.35)

    redacted, _ = service.redact(df, scan, ["Account"])

    assert list(redacted["Account"]) == ["[ACCOUNT]", "[ACCOUNT]"]


def test_float_column_with_a_blank_is_scanned_without_a_trailing_dot_zero() -> None:
    # A blank cell makes pandas read the whole column as float: 1234567890.0.
    df = pd.DataFrame({"Account": [1234567890, None]})
    service = _service(_AccountDetector())
    scan = service.scan(df, ["Account"], ["KE_BANK_ACCOUNT"], 0.35)

    redacted, _ = service.redact(df, scan, ["Account"])

    assert redacted.at[0, "Account"] == "[ACCOUNT]"
    assert scan.cell_count == 1  # the blank is not scanned as "nan"
