r"""Normalize text extracted from PDFs to improve master-list matching.

PyMuPDF's ``get_text()`` can return artifacts that break exact string matching:

- typographic ligatures (``ﬁ`` / ``ﬂ``)
- soft line-break hyphenation (``Sup-\nplies``)
- irregular whitespace, non-breaking spaces, and stray newlines

This module produces a cleaned copy of the text plus an offset map so that a
detection found in the cleaned text can be translated back to a span in the
original extracted text.
"""

from __future__ import annotations

from dataclasses import dataclass

from finance_redactor.domain.entities import Span

# Common typographic ligatures and their ASCII expansions.
_LIGATURES: dict[str, str] = {
    "ﬀ": "ff",
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
    "ﬅ": "ft",
    "ﬆ": "st",
}


@dataclass(frozen=True)
class NormalizedText:
    """Cleaned text extracted from a PDF and a map back to original offsets.

    ``offset_map`` has the same length as ``text``. ``offset_map[i]`` is the
    index in ``raw`` that produced character ``text[i]``. This makes it
    possible to translate a span in ``text`` back into a span in ``raw``.
    """

    text: str
    raw: str
    offset_map: tuple[int, ...]

    def to_raw_span(self, span: Span) -> Span:
        """Convert a span in ``text`` to the corresponding span in ``raw``."""
        if not self.offset_map or span.end <= span.start:
            return span
        start = self.offset_map[span.start]
        end = self.offset_map[span.end - 1] + 1
        return Span(start, end)


def normalize_pdf_text(raw: str, *, keep_newlines: bool = False) -> NormalizedText:
    """Return a whitespace-normalized, ligature-expanded copy of ``raw``.

    The returned ``text`` is suitable for name detection; ``to_raw_span`` can
    translate detection spans back to ``raw`` for replacement in the PDF.

    ``keep_newlines`` collapses a whitespace run that holds a line break to a
    newline rather than a space. OCR text needs this: its lines are table
    rows and separate fields as often as wrapped sentences, and the language
    model misses more bare names once they run together on one line. A
    hyphenated line break is still joined either way.
    """
    if not raw:
        return NormalizedText("", raw, ())

    # Step 1: expand ligatures. Each output character carries the raw offset
    # of the input character it came from.
    expanded: list[tuple[str, int]] = []
    for offset, ch in enumerate(raw):
        replacement = _LIGATURES.get(ch)
        if replacement is None:
            expanded.append((ch, offset))
        else:
            for expanded_ch in replacement:
                expanded.append((expanded_ch, offset))

    # Step 2: remove soft-hyphen line breaks. We scan for "-" followed by a
    # newline and optional whitespace, where the next non-space character is a
    # letter or digit (i.e. the word continues). Both the hyphen and the
    # whitespace are dropped.
    dehyphenated: list[tuple[str, int]] = []
    i = 0
    n = len(expanded)
    while i < n:
        ch, offset = expanded[i]
        if ch == "-":
            j = i + 1
            # Collect whitespace including the newline.
            while j < n and expanded[j][0].isspace():
                j += 1
            if (
                j > i + 1
                and any(expanded[k][0] == "\n" for k in range(i + 1, j))
                and j < n
                and expanded[j][0].isalnum()
            ):
                # Next non-space char is a letter/digit: this is a hyphen break.
                i = j
                continue
        dehyphenated.append((ch, offset))
        i += 1

    # Step 3: collapse whitespace runs to a single space (or to a newline,
    # with ``keep_newlines``, when the run holds one).
    normalized: list[tuple[str, int]] = []
    in_whitespace = False
    ws_offset = 0
    ws_char = " "
    for ch, offset in dehyphenated:
        if ch.isspace():
            if not in_whitespace:
                in_whitespace = True
                ws_offset = offset
                ws_char = " "
            if keep_newlines and ch == "\n":
                ws_char = "\n"
            continue
        if in_whitespace:
            normalized.append((ws_char, ws_offset))
            in_whitespace = False
        normalized.append((ch, offset))
    if in_whitespace:
        normalized.append((ws_char, ws_offset))

    # Step 4: strip leading/trailing whitespace while preserving offset map.
    while normalized and normalized[0][0] in " \n":
        normalized.pop(0)
    while normalized and normalized[-1][0] in " \n":
        normalized.pop()

    text = "".join(ch for ch, _ in normalized)
    offset_map = tuple(offset for _, offset in normalized)
    return NormalizedText(text, raw, offset_map)
