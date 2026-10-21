"""Tests for joining OCR lines and mapping a detected name back to the page."""

from __future__ import annotations

from finance_redactor.domain.entities import Span
from finance_redactor.domain.ocr import OcrLine, join_lines, span_boxes

LINES = [
    OcrLine("Payment voucher", (100.0, 50.0, 250.0, 70.0), 0.99),
    OcrLine("Paid to Jane Doe today", (100.0, 80.0, 320.0, 100.0), 0.97),
]


def test_join_lines_keeps_where_each_line_starts() -> None:
    ocr = join_lines(LINES)

    assert ocr.text == "Payment voucher\nPaid to Jane Doe today"
    assert ocr.starts == (0, 16)
    assert ocr.text[ocr.starts[1] :].startswith("Paid")


def test_a_name_maps_to_a_padded_slice_of_its_line() -> None:
    ocr = join_lines(LINES)
    start = ocr.text.index("Jane Doe")

    (box,) = span_boxes(ocr, LINES, Span(start, start + len("Jane Doe")))

    # "Paid to Jane Doe today": 22 chars over 220 px, so 10 px each;
    # "Jane Doe" is chars 8-16, padded 1.5 chars each side -> 6.5 to 17.5
    # chars, i.e. 165 to 275 px.
    assert box == (165.0, 80.0, 275.0, 100.0)


def test_padding_never_goes_past_the_line_box() -> None:
    ocr = join_lines(LINES)

    (box,) = span_boxes(ocr, LINES, Span(0, len("Payment")))

    assert box[0] == 100.0  # clamped at the line's left edge


def test_a_span_across_two_lines_gives_a_box_on_each() -> None:
    ocr = join_lines(LINES)
    start = ocr.text.index("voucher")
    end = ocr.text.index("Paid") + len("Paid")

    boxes = span_boxes(ocr, LINES, Span(start, end))

    assert len(boxes) == 2
    assert boxes[0][1] == 50.0 and boxes[1][1] == 80.0
