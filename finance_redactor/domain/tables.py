"""Table columns in a PDF, and turning a chosen column into detections.

A finance PDF often holds a table where a whole column is sensitive: a payee,
an account number, a phone number. Detection finds the names it recognizes,
but a cell it misses would stay visible. So the user picks columns by header,
and every cell in a picked column is redacted like a typed word: matched on
the page with :func:`find_custom_words`, labelled, and resolved against the
master list by name.

Two sources feed this. Text-layer pages get their tables from the PDF gateway
(PyMuPDF's table finder). Scanned pages have only the lines OCR read, so
:func:`columns_from_lines` groups those lines into rows and columns by where
they sit on the page. It is a heuristic and errs towards finding a table: a
table found where there is none only adds a choice the user can ignore.

A cell's value is matched across the whole page, so the same value outside
the table is redacted too, with the same label. Over-redaction on purpose.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace

from finance_redactor.domain.custom_words import find_custom_words
from finance_redactor.domain.entities import DetectionSource, PiiDetection
from finance_redactor.domain.ocr import OcrLine
from finance_redactor.domain.pseudonyms import normalize

# A table needs a header row and at least this many rows under it.
_MIN_BODY_ROWS = 2
# Two lines are on the same row when their vertical overlap is at least this
# share of the shorter line's height.
_ROW_OVERLAP = 0.5

# Headers that usually hold a name, an account or a contact detail. Their
# columns start ticked; everything else is the user's choice.
_SUGGESTED_HEADER = re.compile(
    r"\b(?:names?|payees?|beneficiar(?:y|ies)|vendors?|suppliers?|recipients?"
    r"|paid\s+to|staff|employees?|customers?|clients?|contacts?|accounts?"
    r"|acct|a/c|phones?|mobile|tel|m-?pesa|e-?mails?|id|signatures?|signed)\b"
)


@dataclass(frozen=True)
class TableColumn:
    """One column of one table: its header and the text of each cell under it."""

    header: str
    cells: tuple[str, ...]


def header_or_default(header: str | None, index: int) -> str:
    """Return ``header`` stripped, or ``Column N`` (1-based) when it is blank."""
    text = (header or "").strip()
    return text or f"Column {index + 1}"


def column_key(header: str) -> str:
    """Return the key a column is chosen by: same header, same key, any page."""
    return normalize(header)


def suggested_columns(keys: Iterable[str]) -> frozenset[str]:
    """Return the keys whose header looks like a name, account or contact."""
    return frozenset(key for key in keys if _SUGGESTED_HEADER.search(key))


def column_detections(
    text: str,
    columns: Sequence[TableColumn],
    chosen: frozenset[str],
    score: float,
) -> list[PiiDetection]:
    """Find every cell value of the ``chosen`` columns in ``text``.

    Each match is a ``CUSTOM`` detection (so the master list resolves it by
    name) with source ``TABLE_COLUMN``. A cell that wraps onto several lines
    is matched whole first; if the page text does not hold it whole (a
    hyphen at the wrap, say) each of its lines is matched on its own. The
    header itself is never redacted.
    """
    if not chosen:
        return []
    values: dict[str, None] = {}
    for column in columns:
        if column_key(column.header) not in chosen:
            continue
        for cell in column.cells:
            if cell.strip():
                values.setdefault(cell, None)
    detections: list[PiiDetection] = []
    for value in values:
        found = find_custom_words(text, [value], score)
        if not found:
            found = find_custom_words(text, value.splitlines(), score)
        detections.extend(
            replace(detection, source=DetectionSource.TABLE_COLUMN)
            for detection in found
        )
    return detections


def columns_from_lines(lines: Sequence[OcrLine]) -> list[TableColumn]:
    """Group OCR lines into tables and return their columns.

    Lines are grouped into rows by vertical overlap. A table is a run of rows
    with two or more lines each (one-line rows inside a run, such as a cell
    that wrapped, are allowed when a fuller row follows), with a header row
    and at least ``_MIN_BODY_ROWS`` rows under it. The columns are taken from
    the run's fullest row, and every other line joins the column it overlaps
    most, so a line that straddles two columns still lands in one of them
    whole. Plain paragraphs, one line per row, never form a table.
    """
    tables: list[TableColumn] = []
    for run in _table_runs(_rows(lines)):
        tables.extend(_run_columns(run))
    return tables


def _rows(lines: Sequence[OcrLine]) -> list[list[OcrLine]]:
    """Group ``lines`` into rows, top to bottom, each sorted left to right."""
    rows: list[list[OcrLine]] = []
    for line in sorted(lines, key=lambda item: (item.box[1], item.box[0])):
        if rows and _same_row(rows[-1][0], line):
            rows[-1].append(line)
        else:
            rows.append([line])
    return [sorted(row, key=lambda item: item.box[0]) for row in rows]


def _same_row(first: OcrLine, line: OcrLine) -> bool:
    top = max(first.box[1], line.box[1])
    bottom = min(first.box[3], line.box[3])
    shorter = min(first.box[3] - first.box[1], line.box[3] - line.box[1])
    return shorter > 0 and (bottom - top) >= _ROW_OVERLAP * shorter


def _table_runs(rows: list[list[OcrLine]]) -> list[list[list[OcrLine]]]:
    """Split ``rows`` into runs that look like tables."""
    runs: list[list[list[OcrLine]]] = []
    current: list[list[OcrLine]] = []
    for index, row in enumerate(rows):
        following = rows[index + 1] if index + 1 < len(rows) else []
        if len(row) >= 2 or (current and len(row) == 1 and len(following) >= 2):
            current.append(row)
            continue
        runs.append(current)
        current = []
    runs.append(current)
    return [run for run in runs if len(run) >= 1 + _MIN_BODY_ROWS]


def _run_columns(run: list[list[OcrLine]]) -> list[TableColumn]:
    """Return the columns of one run; its first row is the header."""
    bands = [(line.box[0], line.box[2]) for line in max(run, key=len)]
    headers: list[list[str]] = [[] for _ in bands]
    cells: list[list[str]] = [[] for _ in bands]
    for row_index, row in enumerate(run):
        for line in row:
            band = _nearest_band(line, bands)
            (headers if row_index == 0 else cells)[band].append(line.text)
    return [
        TableColumn(header_or_default(" ".join(head), index), tuple(body))
        for index, (head, body) in enumerate(zip(headers, cells, strict=True))
        if body
    ]


def _nearest_band(line: OcrLine, bands: list[tuple[float, float]]) -> int:
    """Return the band ``line`` overlaps most, or the closest if it overlaps none."""
    x0, x1 = line.box[0], line.box[2]

    def overlap(band: tuple[float, float]) -> float:
        return min(x1, band[1]) - max(x0, band[0])

    best = max(range(len(bands)), key=lambda i: overlap(bands[i]))
    if overlap(bands[best]) > 0:
        return best
    centre = (x0 + x1) / 2
    return min(range(len(bands)), key=lambda i: abs(sum(bands[i]) / 2 - centre))
