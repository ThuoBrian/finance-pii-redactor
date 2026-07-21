"""PDF read/redact adapter (PyMuPDF).

Implements the :class:`PdfDocument` port. Wraps a ``fitz.Document`` and exposes
only the operations the use case needs: per-page text extraction, applying
(search_text, label) redactions, and rendering to bytes. The redaction-annotation
parameters are unchanged from the original implementation.
"""

from __future__ import annotations

import re
from io import BytesIO

import fitz  # PyMuPDF

_IMAGE_SENTINEL = "__IMAGE__"

# Common legal suffixes and punctuation variants a search might miss.
_ORG_SUFFIX_RE = re.compile(
    r"\s*(?:\b(?:Ltd\.?|Limited|Inc\.?|Incorporated|LLC|PLC|Corp\.?|Corporation|Co\.?|Company)\b)?\s*[.,;]*\s*$",
    re.IGNORECASE,
)


def _search_variants(search_text: str) -> list[str]:
    """Return fallback search strings to try when the exact text is not found."""
    variants: list[str] = []
    collapsed = re.sub(r"\s+", " ", search_text).strip()
    if collapsed != search_text:
        variants.append(collapsed)
    no_trailing_punct = re.sub(r"[.,;]+$", "", search_text).strip()
    if no_trailing_punct != search_text and no_trailing_punct:
        variants.append(no_trailing_punct)
    for old, new in (("&", "and"), ("and", "&")):
        if old in search_text:
            replaced = search_text.replace(old, new)
            if replaced not in variants:
                variants.append(replaced)
    no_suffix = _ORG_SUFFIX_RE.sub("", search_text).strip()
    if no_suffix and no_suffix != search_text:
        variants.append(no_suffix)
    return variants


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
        redactions: list[tuple[str | list[str], str]],
        *,
        blackout: bool = False,
    ) -> None:
        """Apply redactions to one page.

        Each text redaction is ``(search_text, label)`` or
        ``([primary_search, ...fallbacks], label)``. When ``blackout`` is True,
        matched text is covered with a black box instead of labeled. Images are
        always blacked out; they appear in ``redactions`` as
        ``("__IMAGE__", "")``.

        If ``search_text`` is not found exactly, a small set of normalized
        variants is tried before giving up.
        """
        page = self._doc.load_page(page_index)
        for search_item, label in redactions:
            if search_item == _IMAGE_SENTINEL:
                for x0, y0, x1, y1 in self.page_image_rects(page_index):
                    page.add_redact_annot(
                        fitz.Rect(x0, y0, x1, y1),
                        text=None,
                        fill=(0, 0, 0),
                    )
                continue

            candidates: list[str] = []
            if isinstance(search_item, str):
                candidates = [search_item] + _search_variants(search_item)
            else:
                for item in search_item:
                    candidates.append(item)
                    candidates.extend(_search_variants(item))
                # Deduplicate while preserving order.
                seen: set[str] = set()
                candidates = [c for c in candidates if not (c in seen or seen.add(c))]

            rects: list[fitz.Rect] = []
            for candidate in candidates:
                rects = page.search_for(candidate)
                if rects:
                    break
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
