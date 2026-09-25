"""Excel pseudonymization use case.

Orchestrates: scan selected columns with a :class:`PiiDetector`, then rebuild a
pseudonymized DataFrame by replacing each detected name with its stable
pseudonym (curated from the master list, or a flagged auto-id). Bank and
payment details get a fixed mask instead and stay out of the crosswalk. Pure
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
    normalize,
)


class RedactExcelService:
    """Scans and pseudonymizes spreadsheet cells."""

    def __init__(
        self,
        detector: PiiDetector,
        master_map: Mapping[tuple[str, str], MasterEntry],
        auto_prefixes: Mapping[str, str],
        fuzzy_threshold: float = 0.84,
        *,
        fixed_masks: Mapping[str, str],
    ) -> None:
        """Wire the detector and the master map / auto-id prefixes.

        ``fixed_masks`` (``Settings.fixed_masks``) maps bank/payment entity
        types to their mask. Required, not defaulted: a masked type that fell
        through to the pseudonymizer would write the raw number into the
        crosswalk.

        ``fuzzy_threshold`` should normally be ``Settings.fuzzy_match_threshold``,
        passed explicitly by the composition root; the default here only covers
        callers (e.g. tests) that don't care about the fuzzy-suggestion feature.
        """
        self._detector = detector
        self._master_map = master_map
        self._auto_prefixes = auto_prefixes
        self._fuzzy_threshold = fuzzy_threshold
        self._fixed_masks = fixed_masks

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
                cells.append((row_idx, col, _cell_text(value)))

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
        exclude: frozenset[str] = frozenset(),
    ) -> tuple[pd.DataFrame, list[Assignment]]:
        """Return a pseudonymized copy of ``df`` plus the name->pseudonym crosswalk.

        A single :class:`Pseudonymizer` spans the whole sheet so a name appearing
        in many cells maps to one consistent pseudonym.

        ``exclude`` is a set of already-normalized terms (see
        ``domain/pseudonyms.normalize``) the operator ticked off in the review
        table as false positives. Matching detections are dropped before
        replacement, so they are neither replaced in the output nor recorded in
        the crosswalk.

        This is the reason ``scan`` and ``redact`` are separate: re-applying
        with a different ``exclude`` set is a pure pass over an existing
        :class:`ExcelScanResult` and never re-runs detection, so changing a
        tick box costs nothing and never reloads the spaCy model.
        """
        pseudonymizer = Pseudonymizer(
            self._master_map, self._auto_prefixes, fuzzy_threshold=self._fuzzy_threshold
        )
        redacted = df.copy()
        # A mask is a string, and pandas refuses to write one into an int or
        # float column (an account-number column read as numbers).
        for col in {cell.column for cell in scan_result.findings} & set(columns):
            if redacted[col].dtype != object:
                redacted[col] = redacted[col].astype(object)
        for cell in scan_result.findings:
            if cell.column not in columns:
                continue
            detections = [
                d for d in cell.detections if normalize(d.text) not in exclude
            ]
            if not detections:
                continue
            redacted.at[cell.row, cell.column] = apply_replacements(
                _cell_text(df.at[cell.row, cell.column]),
                detections,
                lambda d: (
                    self._fixed_masks.get(d.entity_type)
                    or pseudonymizer.assign(d.entity_type, d.text).pseudonym
                ),
            )
        return redacted, pseudonymizer.crosswalk()


def _cell_text(value: object) -> str:
    """Text of a cell as detection sees it; ``scan`` and ``redact`` must agree.

    Empty cells become "" rather than "nan", and a whole-number float (how
    pandas reads an integer column that has a blank cell) drops its ".0", so
    an account number isn't masked as "[ACCOUNT].0".
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)
