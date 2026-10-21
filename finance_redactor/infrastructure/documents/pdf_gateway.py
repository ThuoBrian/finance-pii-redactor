"""PDF read/redact adapter (PyMuPDF).

Implements the :class:`PdfDocument` port. Wraps a ``fitz.Document`` and exposes
only the operations the use case needs: per-page text extraction, applying
(search_text, label) redactions, and rendering to bytes. The redaction-annotation
parameters are unchanged from the original implementation.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from io import BytesIO

import fitz  # PyMuPDF
import numpy as np

from finance_redactor.domain.entities import IMAGE_REDACTION_SENTINEL
from finance_redactor.domain.errors import EncryptedPdfError, UnreadableFileError
from finance_redactor.domain.ocr import Box

_EXTERNAL_LINK_KINDS = frozenset({fitz.LINK_URI, fitz.LINK_LAUNCH, fitz.LINK_GOTOR})

# Common legal suffixes and punctuation variants a search might miss.
_ORG_SUFFIX_RE = re.compile(
    r"\s*(?:\b(?:Ltd\.?|Limited|Inc\.?|Incorporated|LLC|PLC|Corp\.?|Corporation|Co\.?|Company)\b)?\s*[.,;]*\s*$",
    re.IGNORECASE,
)
# Matches "and" as a whole word only, so names that merely contain "and" as a
# substring (e.g. "Thailand Corp") aren't corrupted by the & <-> and swap below.
_AND_WORD_RE = re.compile(r"\band\b", re.IGNORECASE)

# page.search_for() returns a rect whose height comes from the font's
# ascent/descent metrics, not the document's actual (often tighter) line
# spacing. In a single-spaced or tightly-set PDF, that metrics-derived box can
# be taller than the real gap between lines, so redacting it as-is can bleed
# into the line above (or below): apply_redactions() removes any glyph whose
# box touches the redaction rect, not just glyphs strictly inside the matched
# text. Shrinking the rect symmetrically top/bottom removes that metrics
# padding. Verified empirically against single-spaced fixtures down to ~90% of
# the font's natural line height: the matched text itself is still fully
# redacted even at inset ratios far larger than this one, since real glyph ink
# (including descenders) sits well inside the metrics box.
_LINE_VERTICAL_INSET_RATIO = 0.18


def _tighten_to_line(
    rect: fitz.Rect, ratio: float = _LINE_VERTICAL_INSET_RATIO
) -> fitz.Rect:
    """Inset a text-search rect vertically to avoid bleeding into adjacent lines."""
    height = rect.y1 - rect.y0
    inset = height * ratio
    return fitz.Rect(rect.x0, rect.y0 + inset, rect.x1, rect.y1 - inset)


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


def _drop_embedded_hits(
    rects: list[fitz.Rect], page_text: str, candidate: str
) -> list[fitz.Rect]:
    """Drop search hits that are only a fragment of a longer word.

    ``page.search_for`` is a plain substring search, so redacting "IPA" would
    also cover the letters inside "principal". Detection is already
    whole-word; this applies the same rule to the hits. Each hit is lined up
    with the same-numbered occurrence of ``candidate`` in ``page_text``, and
    dropped when a word character sits right against a word-character edge of
    the match. If the two counts differ (the match wraps a line, the layout is
    unusual) the hits can't be lined up, so every one is kept: a stray extra
    redaction is better than a name left showing.
    """
    word_edges = (
        candidate[:1].isalnum() or candidate[:1] == "_",
        (candidate[-1:].isalnum() or candidate[-1:] == "_"),
    )
    embedded: list[bool] = []
    for match in re.finditer(re.escape(candidate), page_text, re.IGNORECASE):
        before = page_text[match.start() - 1 : match.start()]
        after = page_text[match.end() : match.end() + 1]
        embedded.append(
            (word_edges[0] and _is_word_char(before))
            or (word_edges[1] and _is_word_char(after))
        )
    if len(embedded) != len(rects):
        return rects
    return [
        rect
        for rect, is_embedded in zip(rects, embedded, strict=True)
        if not is_embedded
    ]


def _is_word_char(char: str) -> bool:
    return bool(char) and (char.isalnum() or char == "_")


# Rebuilding a scanned page: a pixel darker than this (0 black, 255 white) is
# ink. Kept well above typical scan shadows' darkness but loose enough to catch
# a light pen stroke; erring dark-side only adds black, never removes it.
_INK_LEVEL = 190
# Ink is tracked in square cells of this many pixels (1 mm at 200 dpi).
_INK_CELL = 8
# Marks closer than this many cells (3 mm) belong together: the strokes of one
# signature, a stamp and its text.
_MERGE_CELLS = 3
# A group of marks is blacked out as its whole bounding box, so its shape (the
# thing that makes a signature identifiable) does not show. A group covering
# more than this share of the page is usually the ruled lines of a form; it is
# blacked out mark by mark instead, so the form's text stays readable.
_MAX_BOX_SHARE = 0.2


def _box_slices(box: Box, height: int, width: int) -> tuple[slice, slice]:
    """Return the (rows, cols) array slices for ``box``, clipped to the image."""
    x0, y0, x1, y1 = box
    return (
        slice(max(0, int(y0)), min(height, int(np.ceil(y1)))),
        slice(max(0, int(x0)), min(width, int(np.ceil(x1)))),
    )


def _grow(cells: np.ndarray, steps: int) -> np.ndarray:
    """Return ``cells`` grown by ``steps`` cells in every direction."""
    grown = cells.copy()
    for _ in range(steps):
        step = grown.copy()
        step[1:, :] |= grown[:-1, :]
        step[:-1, :] |= grown[1:, :]
        step[:, 1:] |= grown[:, :-1]
        step[:, :-1] |= grown[:, 1:]
        grown = step
    return grown


def _groups(cells: np.ndarray) -> list[list[tuple[int, int]]]:
    """Return the 4-connected groups of set cells (cell grids are small)."""
    seen = np.zeros_like(cells)
    rows, cols = cells.shape
    groups = []
    for start in zip(*np.nonzero(cells), strict=True):
        if seen[start]:
            continue
        seen[start] = True
        stack, members = [start], []
        while stack:
            r, c = stack.pop()
            members.append((int(r), int(c)))
            for nr, nc in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
                if (
                    0 <= nr < rows
                    and 0 <= nc < cols
                    and cells[nr, nc]
                    and not seen[nr, nc]
                ):
                    seen[nr, nc] = True
                    stack.append((nr, nc))
        groups.append(members)
    return groups


def _ink_outside(gray: np.ndarray, keep: Sequence[Box]) -> np.ndarray:
    """Return the pixels to black out: every mark outside ``keep``, shape hidden.

    Marks are grouped (``_MERGE_CELLS``) and each group is covered by its whole
    bounding box, unless the box would cover more than ``_MAX_BOX_SHARE`` of
    the page (a form's ruled lines), in which case only the group's own cells
    are covered. Kept text inside a box is put back by the caller.
    """
    height, width = gray.shape
    ink = gray < _INK_LEVEL
    for box in keep:
        ink[_box_slices(box, height, width)] = False
    cell = _INK_CELL
    rows, cols = -(-height // cell), -(-width // cell)
    padded = np.zeros((rows * cell, cols * cell), dtype=bool)
    padded[:height, :width] = ink
    cells: np.ndarray = np.asarray(
        padded.reshape(rows, cell, cols, cell).any(axis=(1, 3))
    )
    out = np.zeros_like(cells)
    for members in _groups(_grow(cells, _MERGE_CELLS)):
        rs = [r for r, _ in members]
        cs = [c for _, c in members]
        r0, r1, c0, c1 = min(rs), max(rs) + 1, min(cs), max(cs) + 1
        if (r1 - r0) * (c1 - c0) <= _MAX_BOX_SHARE * cells.size:
            out[r0:r1, c0:c1] = True
        else:
            out[tuple(np.array(members).T)] = True
    return np.repeat(np.repeat(out, cell, axis=0), cell, axis=1)[:height, :width]


class PyMuPdfDocument:
    """A single open PDF being redacted in place."""

    def __init__(self, doc: fitz.Document) -> None:
        """Wrap an already-open PyMuPDF document."""
        self._doc = doc

    @classmethod
    def open(cls, source: object) -> PyMuPdfDocument:
        """Open a PDF from bytes or a readable file-like object.

        Raises :class:`EncryptedPdfError` when the PDF carries a user (open)
        password. This has to be an explicit check: ``fitz.open`` accepts such
        a document without complaint and even reports a correct
        ``page_count``, then raises a bare ``ValueError("document closed or
        encrypted")`` on the first page access - which surfaces to the user as
        a raw traceback rather than something actionable.

        A PDF with only an *owner* password (restricted printing/copying but
        no password needed to view) reports ``needs_pass == 0``, so it opens
        and redacts normally. Note that the redacted copy is written
        unencrypted, dropping those restrictions.

        Raises :class:`UnreadableFileError` for a corrupted PDF or one
        renamed to ``.pdf`` without really being one - PyMuPDF raises its own
        ``FileDataError`` for that, which is reraised as the shared type so
        the presentation layer has one error to catch across all three
        formats.
        """
        data = source.read() if hasattr(source, "read") else source
        try:
            doc = fitz.open(stream=data, filetype="pdf")
        except fitz.FileDataError as e:
            raise UnreadableFileError from e
        if doc.needs_pass:
            doc.close()
            raise EncryptedPdfError
        return cls(doc)

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
        ``("__IMAGE__", "")``. Image pixels under any redaction are removed
        from the file, not just covered.

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
                # Deduplicate while preserving order. Relies on set.add()
                # always returning None (falsy), so `or` always evaluates and
                # runs the add - a deliberate idiom, not a bug.
                seen: set[str] = set()
                candidates = [
                    c
                    for c in candidates
                    if not (c in seen or seen.add(c))  # type: ignore[func-returns-value]
                ]

            rects: list[fitz.Rect] = []
            matched_candidate = ""
            for candidate in candidates:
                rects = page.search_for(candidate, textpage=textpage)
                if rects:
                    matched_candidate = candidate
                    break
            if not rects:
                continue
            rects = _drop_embedded_hits(
                rects, textpage.extractText(), matched_candidate
            )
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
                    _tighten_to_line(rect),
                    text=label if show_label else None,
                    fontname="helv",
                    fontsize=11,
                    text_color=(0, 0, 0),
                    fill=(0, 0, 0) if blackout else (1, 1, 1),
                )
        # PIXELS, not NONE: NONE only draws the black box over an image and
        # leaves the image itself in the file, where anyone can extract it
        # (a "blacked-out" signature came back intact). PIXELS blanks the
        # pixels under every redaction, and an image wholly covered is dropped.
        try:
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS)
        except Exception:  # noqa: BLE001 - any failure must not leave the image
            # If an unusual image format defeats pixel editing, remove every
            # image a redaction touches instead. Over-redaction, never a leak.
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_REMOVE)

    def remove_external_links(self) -> int:
        """Delete every link that leaves the document; return how many.

        URLs, file launches and links into other PDFs go, since the target can
        name a person (``mailto:``) or a private path. Jumps to another page of
        this same document stay. The visible text is left for detection.
        """
        removed = 0
        for page in self._doc:
            for link in page.get_links():
                if link["kind"] in _EXTERNAL_LINK_KINDS:
                    page.delete_link(link)
                    removed += 1
        return removed

    def render_page(self, page_index: int, dpi: int) -> bytes:
        """Render one page to a PNG at ``dpi`` (for OCR)."""
        return self._doc.load_page(page_index).get_pixmap(dpi=dpi).tobytes("png")

    def rebuild_scanned_page(
        self,
        page_index: int,
        dpi: int,
        *,
        keep: Sequence[Box],
        names: Sequence[tuple[Box, str]],
        blackout_names: bool,
        blackout_other_ink: bool,
    ) -> None:
        """Replace a scanned page with a cleaned picture of itself.

        The page is rendered at ``dpi``, edited as pixels, and put back as a
        single new image after everything on the page has been removed, so no
        hidden layer of the original survives. Labels are drawn as real text
        on top. Boxes are in the rendered page's pixels.
        """
        page = self._doc.load_page(page_index)
        pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csRGB, alpha=False)
        height, width = pix.height, pix.width
        image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(height, width, 3)
        original = image
        image = image.copy()
        if blackout_other_ink:
            image[_ink_outside(image.mean(axis=2), keep)] = 0
            # A blacked-out box can overlap printed text the OCR read with
            # confidence (a signature across a line); put that text back.
            for box in keep:
                rows, cols = _box_slices(box, height, width)
                image[rows, cols] = original[rows, cols]
        for box, _label in names:
            image[_box_slices(box, height, width)] = 0 if blackout_names else 255
        cleaned = fitz.Pixmap(fitz.csRGB, width, height, image.tobytes(), False)

        page.add_redact_annot(page.rect, fill=(1, 1, 1))
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_REMOVE)
        page.insert_image(page.rect, stream=cleaned.tobytes("png"))
        if not blackout_names:
            scale = 72 / dpi
            for (x0, y0, x1, y1), label in names:
                height_pt = (y1 - y0) * scale
                page.insert_text(
                    (x0 * scale + 1, y1 * scale - height_pt * 0.2),
                    label,
                    fontname="helv",
                    fontsize=max(6.0, min(11.0, height_pt * 0.75)),
                    color=(0, 0, 0),
                )

    def to_bytes(self) -> bytes:
        """Render the redacted document to bytes, without the original's metadata.

        The Info dictionary (author, title, subject, keywords, creator,
        producer, dates) and the XMP packet are removed first: they can name
        the author or the document and survive text redaction untouched.
        """
        self._doc.set_metadata({})
        self._doc.del_xml_metadata()
        output = BytesIO()
        self._doc.save(output, garbage=3, deflate=True)
        return output.getvalue()

    def close(self) -> None:
        """Close the underlying document."""
        self._doc.close()
