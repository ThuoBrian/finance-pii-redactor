"""Result DTOs returned by the use cases.

A single, explicit shape for each flow's output, replacing the ad-hoc tuples and
``dict[(row, col)] -> list[RecognizerResult]`` that the old code passed around.
The presentation layer renders these; nothing here depends on a UI framework.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

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
class WorkbookScanResult:
    """Outcome of scanning every selected tab of a workbook.

    ``sheets`` is keyed by the original tab name. ``tab_names`` holds the
    detections found in the tab names themselves (a tab called after a vendor
    or a person is PII too), keyed by the original tab name.
    """

    sheets: dict[str, ExcelScanResult]
    tab_names: dict[str, list[PiiDetection]]

    @property
    def cell_count(self) -> int:
        """Number of cells, across all tabs, containing at least one detection."""
        return sum(result.cell_count for result in self.sheets.values())

    @property
    def entity_count(self) -> int:
        """Total detections across all tabs, including those in tab names."""
        return sum(result.entity_count for result in self.sheets.values()) + sum(
            len(found) for found in self.tab_names.values()
        )


@dataclass(frozen=True)
class RedactedSheet:
    """One redacted tab: its (already redacted) name, data and changed cells."""

    name: str
    data: pd.DataFrame
    highlighted: set[tuple[int, str]]


@dataclass(frozen=True)
class PdfRedactionResult:
    """Outcome of pseudonymizing a PDF: bytes, findings, pages, and crosswalk.

    ``source_bracketed_numbers`` counts ``[12]``-style strings that were
    already in the document before redaction. Labels are written as ``[001]``,
    so in a document with its own bracketed numbering (footnote markers, note
    references, line items) a reader cannot always tell a redaction from
    original content. The tool cannot fix that without changing the label
    format, so it reports it and leaves the judgement to the operator.

    ``removed_links`` counts link targets (URLs, files, other documents)
    deleted from the output; their visible text went through detection.
    """

    data: bytes
    findings: list[Finding]
    page_count: int
    crosswalk: list[Assignment]
    source_bracketed_numbers: int = 0
    removed_links: int = 0

    @property
    def entity_count(self) -> int:
        """Total number of pseudonymized detections."""
        return len(self.findings)


@dataclass(frozen=True)
class DocxRedactionResult:
    """Outcome of pseudonymizing a Word doc: bytes, findings, blocks, crosswalk.

    ``findings`` reuses :class:`Finding`, whose ``page`` field holds the
    paragraph/block ordinal here rather than a PDF page number.
    ``removed_links`` counts hyperlink targets stripped from the output.
    """

    data: bytes
    findings: list[Finding]
    block_count: int
    crosswalk: list[Assignment]
    removed_links: int = 0

    @property
    def entity_count(self) -> int:
        """Total number of pseudonymized detections."""
        return len(self.findings)
