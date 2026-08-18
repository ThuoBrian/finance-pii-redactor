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

from finance_redactor.domain.entities import PiiDetection, Span


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

    def write(
        self,
        df: pd.DataFrame,
        highlighted_cells: set[tuple[int, str]],
        crosswalk_df: pd.DataFrame,
    ) -> bytes:
        """Serialize ``df`` to xlsx, highlighting the given (row, column) cells.

        ``crosswalk_df`` is written as a second, unhighlighted "Crosswalk"
        sheet alongside the redacted data.
        """
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
        redactions: list[tuple[str | list[str], str]],
        *,
        blackout: bool = False,
    ) -> None:
        """Apply redactions to one page.

        Each text redaction is ``(search_text, label)`` or
        ``([primary_search, ...fallbacks], label)``. When ``blackout`` is True,
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


@runtime_checkable
class WordDocument(Protocol):
    """A mutable, open Word (.docx) document being pseudonymized block by block.

    A "block" is one paragraph - covering the document body, table cells
    (including nested tables), and headers/footers - enumerated once in a
    stable order by the gateway.
    """

    @property
    def block_count(self) -> int:
        """Total number of paragraph blocks."""
        ...

    def block_text(self, block_index: int) -> str:
        """Return the flattened text (all runs concatenated) of one block."""
        ...

    def replace_block_text(
        self, block_index: int, replacements: list[tuple[Span, str]]
    ) -> None:
        """Replace each ``Span`` (offsets into ``block_text(block_index)``) with
        its paired pseudonym, editing the underlying runs in place so
        unaffected text keeps its original formatting.
        """
        ...

    def to_bytes(self) -> bytes:
        """Render the pseudonymized document to bytes."""
        ...

    def close(self) -> None:
        """Release underlying resources."""
        ...


class WordDocumentFactory(Protocol):
    """Opens a :class:`WordDocument` from a file-like source."""

    def __call__(self, source: object) -> WordDocument:
        """Open and return a Word document."""
        ...
