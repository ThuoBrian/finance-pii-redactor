"""Text read from a scanned page, and where on the page each part of it sits.

An OCR engine returns lines: the text it read, a box around it in the pixels
of the rendered page, and how sure it is. Detection works on one string, so
the lines are joined with newlines and the start of each line is kept. A
detected name is then mapped back to a box by slicing its line's box in
proportion to the characters, padded on both sides: the slice is an estimate
(letters are not all the same width), and a name cut short would leave part
of it readable, so the padding errs towards covering too much.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from finance_redactor.domain.entities import Span

Box = tuple[float, float, float, float]  # x0, y0, x1, y1 in rendered-page pixels

# Characters of padding on each side of a name's estimated slice of its line.
_PAD_CHARS = 1.5
# Lines are joined with a newline. The language model can run a name into the
# next line ("Jane Doe" then "Signature:" comes out as one name), and a blank
# line does not stop it; only a full stop does, which would also split a name
# that wraps onto the next line. Running on only over-redacts; splitting could
# leave half a name showing. So the run-on is kept on purpose.
_LINE_SEPARATOR = "\n"


@dataclass(frozen=True)
class OcrLine:
    """One line an OCR engine read: its text, its box, and its confidence (0-1)."""

    text: str
    box: Box
    score: float


@dataclass(frozen=True)
class OcrText:
    """The lines joined with newlines, plus where each line starts in ``text``."""

    text: str
    starts: tuple[int, ...]


def join_lines(lines: Sequence[OcrLine]) -> OcrText:
    """Join ``lines`` into one string for detection, remembering each start."""
    starts: list[int] = []
    offset = 0
    for line in lines:
        starts.append(offset)
        offset += len(line.text) + len(_LINE_SEPARATOR)
    return OcrText(_LINE_SEPARATOR.join(line.text for line in lines), tuple(starts))


def span_boxes(ocr: OcrText, lines: Sequence[OcrLine], span: Span) -> list[Box]:
    """Return a box for each line ``span`` touches, covering that part of the line.

    The slice is proportional to character positions and padded by
    ``_PAD_CHARS`` on each side, never past the line's own box.
    """
    boxes: list[Box] = []
    for start, line in zip(ocr.starts, lines, strict=True):
        end = start + len(line.text)
        lo, hi = max(span.start, start), min(span.end, end)
        if lo >= hi:
            continue
        x0, y0, x1, y1 = line.box
        width = (x1 - x0) / max(len(line.text), 1)
        left = x0 + (lo - start - _PAD_CHARS) * width
        right = x0 + (hi - start + _PAD_CHARS) * width
        boxes.append((max(x0, left), y0, min(x1, right), y1))
    return boxes
