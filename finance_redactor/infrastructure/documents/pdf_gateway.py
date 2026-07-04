"""PDF read/redact adapter (PyMuPDF).

Implements the :class:`PdfDocument` port. Wraps a ``fitz.Document`` and exposes
only the operations the use case needs: per-page text extraction, applying
(search_text, label) redactions, and rendering to bytes. The redaction-annotation
parameters are unchanged from the original implementation.
"""

from __future__ import annotations

from io import BytesIO

import fitz  # PyMuPDF


class PyMuPdfDocument:
    """A single open PDF being redacted in place."""

    def __init__(self, doc: fitz.Document) -> None:
        """Wrap an already-open PyMuPDF document."""
        self._doc = doc

    @classmethod
    def open(cls, source: object) -> PyMuPdfDocument:
        """Open a PDF from bytes or a readable file-like object."""
        data = source.read() if hasattr(source, "read") else source
        return cls(fitz.open(stream=data, filetype="pdf"))

    @property
    def page_count(self) -> int:
        """Total number of pages in the document."""
        return len(self._doc)

    def page_text(self, page_index: int) -> str:
        """Extract the selectable text of one page."""
        return self._doc.load_page(page_index).get_text()

    def redact_page(self, page_index: int, redactions: list[tuple[str, str]]) -> None:
        """Search for each text and overlay its label, then apply redactions.

        Texts that cannot be located on the page are skipped (the caller still
        reports them as findings). Redactions are applied once per page.
        """
        page = self._doc.load_page(page_index)
        for search_text, label in redactions:
            rects = page.search_for(search_text)
            if not rects:
                continue
            for rect in rects:
                page.add_redact_annot(
                    rect,
                    text=label,
                    fontname="helv",
                    fontsize=11,
                    text_color=(0, 0, 0),
                    fill=(1, 1, 1),
                )
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

    def to_bytes(self) -> bytes:
        """Render the redacted document to bytes."""
        output = BytesIO()
        self._doc.save(output, garbage=3, deflate=True)
        return output.getvalue()

    def close(self) -> None:
        """Close the underlying document."""
        self._doc.close()
