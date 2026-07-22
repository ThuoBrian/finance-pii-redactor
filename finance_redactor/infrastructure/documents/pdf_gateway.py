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

from finance_redactor.domain.entities import IMAGE_REDACTION_SENTINEL

# Common legal suffixes and punctuation variants a search might miss.
_ORG_SUFFIX_RE = re.compile(
    r"\s*(?:\b(?:Ltd\.?|Limited|Inc\.?|Incorporated|LLC|PLC|Corp\.?|Corporation|Co\.?|Company)\b)?\s*[.,;]*\s*$",
    re.IGNORECASE,
)
# Matches "and" as a whole word only, so names that merely contain "and" as a
# substring (e.g. "Thailand Corp") aren't corrupted by the & <-> and swap below.
_AND_WORD_RE = re.compile(r"\band\b", re.IGNORECASE)


def _search_variants(search_text: str) -> list[str]:
    """Return fallback search strings to try when the exact text is not found."""
    variants: list[str] = []
    collapsed = re.sub(r"\s+", " ", search_text).strip()
    if collapsed != search_text:
        variants.append(collapsed)
    no_trailing_punct = re.sub(r"[.,;]+$", "", search_text).strip()
    if no_trailing_punct != search_text and no_trailing_punct:
        variants.append(no_trailing_punct)
    if "&" in search_text:
        replaced = search_text.replace("&", "and")
        if replaced not in variants:
            variants.append(replaced)
    if _AND_WORD_RE.search(search_text):
        replaced = _AND_WORD_RE.sub("&", search_text)
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
        # Reused across every search_for call below: apply_redactions() is only
        # called once at the end of this method, so the page's text layout can't
        # change mid-loop, and building one snapshot avoids PyMuPDF re-parsing
        # the page for every candidate of every detection.
        textpage = page.get_textpage()
        for search_item, label in redactions:
            if search_item == IMAGE_REDACTION_SENTINEL:
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
            matched_candidate = ""
            for candidate in candidates:
                rects = page.search_for(candidate, textpage=textpage)
                if rects:
                    matched_candidate = candidate
                    break
            if not rects:
                continue
            # A candidate containing a line break (e.g. the dehyphenated raw-text
            # fallback) matches one logical occurrence that PyMuPDF reports as one
            # rect per line it spans. Label only the first rect so the pseudonym
            # isn't stamped once per line fragment; every rect still gets covered.
            spans_multiple_lines = "\n" in matched_candidate
            for index, rect in enumerate(rects):
                show_label = not blackout and (index == 0 or not spans_multiple_lines)
                page.add_redact_annot(
                    rect,
                    text=label if show_label else None,
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
