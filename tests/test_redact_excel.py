"""Tests for the Excel scan use case, focused on the unique-value dedup path.

Framework-free: a fake ``PiiDetector`` stands in for Presidio/spaCy, so these run
without the language model (matching the rest of the suite).
"""

from __future__ import annotations

import pandas as pd

from finance_redactor.application.redact_excel import RedactExcelService
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
    return RedactExcelService(detector, master_map={}, auto_prefixes={"PERSON": "PSN"})


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
