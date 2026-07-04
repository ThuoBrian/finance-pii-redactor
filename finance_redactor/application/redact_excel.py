"""Excel pseudonymization use case.

Orchestrates: scan selected columns with a :class:`PiiDetector`, then rebuild a
pseudonymized DataFrame by replacing each detected name with its stable
pseudonym (curated from the master list, or a flagged auto-id). Pure
orchestration - no pandas I/O (that lives in the Excel gateway) and no Streamlit.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

import pandas as pd

from finance_redactor.application.ports import PiiDetector
from finance_redactor.application.results import CellFinding, ExcelScanResult
from finance_redactor.domain.entities import PiiDetection
from finance_redactor.domain.pseudonyms import (
    Assignment,
    MasterEntry,
    Pseudonymizer,
    apply_replacements,
)


class RedactExcelService:
    """Scans and pseudonymizes spreadsheet cells."""

    def __init__(
        self,
        detector: PiiDetector,
        master_map: Mapping[tuple[str, str], MasterEntry],
        auto_prefixes: Mapping[str, str],
    ) -> None:
        """Wire the detector and the master map / auto-id prefixes."""
        self._detector = detector
        self._master_map = master_map
        self._auto_prefixes = auto_prefixes

    def scan(
        self,
        df: pd.DataFrame,
        columns: list[str],
        entities: list[str],
        threshold: float,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> ExcelScanResult:
        """Detect PII across the selected columns, keyed by cell.

        Each *distinct* cell value is analyzed only once and the result reused for
        every cell holding that value (identical text yields identical spans), so
        the detector runs O(unique values) times rather than O(rows x columns) —
        a large saving on spreadsheets where names repeat across many rows.

        ``on_progress`` (if given) is called as ``(done, total)`` after each unique
        value is analyzed, letting the caller drive a progress bar without this
        layer depending on any UI framework.
        """
        cells: list[tuple[int, str, str]] = []  # (row, column, cell text)
        for col in columns:
            if col not in df.columns:
                continue
            for row_idx, value in enumerate(df[col]):
                cells.append((row_idx, col, str(value) if value is not None else ""))

        unique_texts = list(dict.fromkeys(text for _, _, text in cells))
        total = len(unique_texts)
        cache: dict[str, list[PiiDetection]] = {}
        for done, text in enumerate(unique_texts, start=1):
            cache[text] = self._detector.analyze(text, entities, threshold)
            if on_progress is not None:
                on_progress(done, total)

        findings = [
            CellFinding(row_idx, col, cache[text])
            for row_idx, col, text in cells
            if cache[text]
        ]
        return ExcelScanResult(findings)

    def redact(
        self,
        df: pd.DataFrame,
        scan_result: ExcelScanResult,
        columns: list[str],
    ) -> tuple[pd.DataFrame, list[Assignment]]:
        """Return a pseudonymized copy of ``df`` plus the name->pseudonym crosswalk.

        A single :class:`Pseudonymizer` spans the whole sheet so a name appearing
        in many cells maps to one consistent pseudonym.
        """
        pseudonymizer = Pseudonymizer(self._master_map, self._auto_prefixes)
        redacted = df.copy()
        for cell in scan_result.findings:
            if cell.column not in columns:
                continue
            redacted.at[cell.row, cell.column] = apply_replacements(
                str(df.at[cell.row, cell.column]),
                cell.detections,
                lambda d: pseudonymizer.assign(d.entity_type, d.text).pseudonym,
            )
        return redacted, pseudonymizer.crosswalk()
