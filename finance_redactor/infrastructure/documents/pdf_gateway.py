"""PDF read/redact adapter (PyMuPDF).

Implements the :class:`PdfDocument` port. Wraps a ``fitz.Document`` and exposes
only the operations the use case needs: per-page text extraction, applying
(search_text, label) redactions, and rendering to bytes. The redaction-annotation
parameters are unchanged from the original implementation.
"""

from __future__ import annotations

from io import BytesIO

import fitz  # PyMuPDF

_IMAGE_SENTINEL = "__IMAGE__"


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

    def page_image_rects(
        self, page_index: int
    ) -> list[tuple[float, float, float, float]]:
        """Return image bounding boxes on one page as (x0, y0, x1, y1) tuples."""
        page = self._doc.load_page(page_index)
        rects: list[tuple[float, float, float, float]] = []
        for _img_index, img in enumerate(page.get_images(full=True), start=1):
            xref = img[0]
            for rect in page.get_image_rects(xref):
                rects.append((rect.x0, rect.y0, rect.x1, rect.y1))
        return rects

    def redact_page(
        self,
        page_index: int,
        redactions: list[tuple[str, str]],
        *,
        blackout: bool = False,
    ) -> None:
        """Apply redactions to one page.

        Each text redaction is ``(search_text, label)``. When ``blackout`` is True,
        matched text is covered with a black box instead of labeled. Images are
        always blacked out; they appear in ``redactions`` as
        ``("__IMAGE__", "")``.
        """
        page = self._doc.load_page(page_index)
        for search_text, label in redactions:
            if search_text == _IMAGE_SENTINEL:
                for x0, y0, x1, y1 in self.page_image_rects(page_index):
                    page.add_redact_annot(
                        fitz.Rect(x0, y0, x1, y1),
                        text=None,
                        fill=(0, 0, 0),
                    )
                continue

            rects = page.search_for(search_text)
            if not rects:
                continue
            for rect in rects:
                page.add_redact_annot(
                    rect,
                    text=None if blackout else label,
                    fontname="helv",
                    fontsize=11,
                    text_color=(0, 0, 0),
                    fill=(0, 0, 0) if blackout else (1, 1, 1),
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
