"""Abstract ports (interfaces) the use cases depend on.

These ``Protocol`` classes invert the dependency between the application and the
infrastructure: use cases are written against these contracts, and concrete
adapters in ``infrastructure`` satisfy them structurally (no inheritance
required). This is what removes the old direct coupling from UI/logic to
Presidio, openpyxl, and PyMuPDF.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import pandas as pd

from finance_redactor.domain.entities import PiiDetection


@runtime_checkable
class PiiDetector(Protocol):
    """Detects PII in a single text string."""

    def analyze(
        self, text: str, entities: list[str], threshold: float
    ) -> list[PiiDetection]:
        """Return all detections in ``text`` for the requested entity types."""
        ...


@runtime_checkable
class ExcelGateway(Protocol):
    """Reads and writes Excel workbooks."""

    def read(self, source: object) -> pd.DataFrame:
        """Load a workbook into a DataFrame."""
        ...

    def text_columns(self, df: pd.DataFrame) -> list[str]:
        """Return the columns worth scanning (free-text) for default selection."""
        ...

    def write(self, df: pd.DataFrame, highlighted_cells: set[tuple[int, str]]) -> bytes:
        """Serialize ``df`` to xlsx, highlighting the given (row, column) cells."""
        ...


@runtime_checkable
class PdfDocument(Protocol):
    """A mutable, open PDF being redacted page by page."""

    @property
    def page_count(self) -> int:
        """Total number of pages."""
        ...

    def page_text(self, page_index: int) -> str:
        """Extract the selectable text of one page."""
        ...

    def page_image_rects(
        self, page_index: int
    ) -> list[tuple[float, float, float, float]]:
        """Return image bounding boxes on one page as (x0, y0, x1, y1) tuples."""
        ...

    def redact_page(
        self,
        page_index: int,
        redactions: list[tuple[str, str]],
        *,
        blackout: bool = False,
    ) -> None:
        """Apply redactions to one page.

        Each text redaction is ``(search_text, label)``. When ``blackout`` is True,
        matched text is covered with a black box instead of labeled; images are
        always blacked out when present in ``redactions`` as ``("__IMAGE__", "")``.
        """
        ...

    def to_bytes(self) -> bytes:
        """Render the redacted document to bytes."""
        ...

    def close(self) -> None:
        """Release underlying resources."""
        ...


class PdfDocumentFactory(Protocol):
    """Opens a :class:`PdfDocument` from a file-like source."""

    def __call__(self, source: object) -> PdfDocument:
        """Open and return a PDF document."""
        ...
