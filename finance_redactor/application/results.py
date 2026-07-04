"""Result DTOs returned by the use cases.

A single, explicit shape for each flow's output, replacing the ad-hoc tuples and
``dict[(row, col)] -> list[RecognizerResult]`` that the old code passed around.
The presentation layer renders these; nothing here depends on a UI framework.
"""

from __future__ import annotations

from dataclasses import dataclass

from finance_redactor.domain.entities import Finding, PiiDetection
from finance_redactor.domain.pseudonyms import Assignment


@dataclass(frozen=True)
class CellFinding:
    """All detections found within one spreadsheet cell."""

    row: int
    column: str
    detections: list[PiiDetection]


@dataclass(frozen=True)
class ExcelScanResult:
    """Outcome of scanning selected spreadsheet columns for PII."""

    findings: list[CellFinding]

    @property
    def cell_count(self) -> int:
        """Number of cells containing at least one detection."""
        return len(self.findings)

    @property
    def entity_count(self) -> int:
        """Total number of individual detections across all cells."""
        return sum(len(cell.detections) for cell in self.findings)

    def cell_keys(self) -> set[tuple[int, str]]:
        """Return the (row, column) keys of every cell that was changed."""
        return {(cell.row, cell.column) for cell in self.findings}


@dataclass(frozen=True)
class PdfRedactionResult:
    """Outcome of pseudonymizing a PDF: bytes, findings, pages, and crosswalk."""

    data: bytes
    findings: list[Finding]
    page_count: int
    crosswalk: list[Assignment]

    @property
    def entity_count(self) -> int:
        """Total number of pseudonymized detections."""
        return len(self.findings)
