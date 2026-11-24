"""Pull all readable text out of a document, for the leak check.

Used on both the generated input (to prove every gold value is really there)
and the redacted output (to see whether it still is). PDF text goes through
the app's own normalizer so a hyphen-split name reads as one word, and any
page holding an image is also read with OCR when an engine is given.
"""

from __future__ import annotations

from collections.abc import Callable
from io import BytesIO

import fitz
from docx import Document
from openpyxl import load_workbook

from finance_redactor.domain.pdf_text_normalizer import normalize_pdf_text

OcrRead = Callable[[bytes], str]  # page PNG -> text

_OCR_DPI = 200


def text_of(file_type: str, data: bytes, ocr: OcrRead | None = None) -> str:
    """Return every piece of text a reader of the file could see."""
    if file_type == "xlsx":
        return _xlsx(data)
    if file_type == "docx":
        return _docx(data)
    return _pdf(data, ocr)


def _xlsx(data: bytes) -> str:
    workbook = load_workbook(BytesIO(data))
    parts: list[str] = []
    for sheet in workbook.worksheets:
        parts.append(sheet.title)
        for row in sheet.iter_rows(values_only=True):
            parts += [str(value) for value in row if value is not None]
    return "\n".join(parts)


def _docx(data: bytes) -> str:
    document = Document(BytesIO(data))
    parts = [p.text for p in document.paragraphs]
    for table in document.tables:
        parts += [cell.text for row in table.rows for cell in row.cells]
    for section in document.sections:
        parts += [p.text for p in section.header.paragraphs]
        parts += [p.text for p in section.footer.paragraphs]
    return "\n".join(parts)


def _pdf(data: bytes, ocr: OcrRead | None) -> str:
    parts: list[str] = []
    with fitz.open(stream=data, filetype="pdf") as document:
        for page in document:
            text = page.get_text()
            # A rebuilt scan keeps a text layer of labels only; the names
            # that might have survived are in the picture, so read it too.
            if ocr is not None and page.get_images():
                text += "\n" + ocr(page.get_pixmap(dpi=_OCR_DPI).tobytes("png"))
            parts.append(normalize_pdf_text(text).text)
    return "\n".join(parts)
