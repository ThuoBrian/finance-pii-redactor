"""Tests for PDF text normalization and offset mapping."""

from __future__ import annotations

from finance_redactor.domain.entities import Span
from finance_redactor.infrastructure.detection.pdf_text_normalizer import (
    normalize_pdf_text,
)


def test_empty_text_returns_empty():
    result = normalize_pdf_text("")
    assert result.text == ""
    assert result.raw == ""
    assert result.offset_map == ()


def test_simple_text_unchanged():
    raw = "Acme Supplies"
    result = normalize_pdf_text(raw)
    assert result.text == raw
    assert result.offset_map == tuple(range(len(raw)))


def test_ligatures_expanded():
    raw = "ﬁnance ﬂow"
    result = normalize_pdf_text(raw)
    assert result.text == "finance flow"
    # The whole normalized span maps back to the whole raw span.
    raw_span = result.to_raw_span(Span(0, len(result.text)))
    assert raw[raw_span.start : raw_span.end] == raw
    # Each word individually (include trailing space in normalized span).
    assert (
        raw[result.to_raw_span(Span(0, 8)).start : result.to_raw_span(Span(0, 8)).end]
        == "ﬁnance "
    )
    assert (
        raw[result.to_raw_span(Span(8, 12)).start : result.to_raw_span(Span(8, 12)).end]
        == "ﬂow"
    )


def test_whitespace_collapsed():
    raw = "Acme   Supplies\n\nLtd"
    result = normalize_pdf_text(raw)
    assert result.text == "Acme Supplies Ltd"
    raw_span = result.to_raw_span(Span(0, len(result.text)))
    assert raw[raw_span.start : raw_span.end] == raw


def test_hyphen_break_removed():
    raw = "Acme Sup-\nplies Ltd"
    result = normalize_pdf_text(raw)
    assert result.text == "Acme Supplies Ltd"
    # The normalized span for "Supplies" maps back to "Sup-\nplies" in raw.
    start = result.text.find("Supplies")
    raw_span = result.to_raw_span(Span(start, start + len("Supplies")))
    assert raw[raw_span.start : raw_span.end] == "Sup-\nplies"


def test_hyphen_without_newline_is_kept():
    raw = "Acme Supplies - Ltd"
    result = normalize_pdf_text(raw)
    assert result.text == "Acme Supplies - Ltd"


def test_real_hyphen_between_words_is_kept():
    raw = "well-known company"
    result = normalize_pdf_text(raw)
    assert result.text == "well-known company"


def test_span_translation_round_trip():
    raw = "ﬁrst Acme-\nSupplies last"
    result = normalize_pdf_text(raw)
    assert result.text == "first AcmeSupplies last"
    start = result.text.find("AcmeSupplies")
    end = start + len("AcmeSupplies")
    raw_span = result.to_raw_span(Span(start, end))
    assert raw[raw_span.start : raw_span.end] == "Acme-\nSupplies"


def test_to_raw_span_with_empty_span():
    result = normalize_pdf_text("hello")
    assert result.to_raw_span(Span(0, 0)) == Span(0, 0)


def test_offset_map_length_matches_text():
    raw = "  Acme   Sup-\nplies  "
    result = normalize_pdf_text(raw)
    assert len(result.text) == len(result.offset_map)
