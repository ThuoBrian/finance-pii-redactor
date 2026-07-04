"""Application layer: use cases and the ports they depend on.

Use cases orchestrate domain rules and abstract ``ports`` (Protocols). They
never import a concrete framework, so they can be exercised with fakes and are
unaffected by swapping Presidio, PyMuPDF, or the storage backend.
"""

from finance_redactor.application.redact_excel import RedactExcelService
from finance_redactor.application.redact_pdf import RedactPdfService
from finance_redactor.application.results import (
    CellFinding,
    ExcelScanResult,
    PdfRedactionResult,
)

__all__ = [
    "RedactExcelService",
    "RedactPdfService",
    "ExcelScanResult",
    "CellFinding",
    "PdfRedactionResult",
]
