"""Tests for PyMuPDF gateway helpers."""

from __future__ import annotations

import fitz

from finance_redactor.infrastructure.documents.pdf_gateway import (
    PyMuPdfDocument,
    _search_variants,
)


def _wrapped_name_pdf_bytes() -> bytes:
    """Build a real one-page PDF where a name is split by a soft-hyphen line break.

    Mirrors what PyMuPDF's ``get_text()`` extracts for a name that wraps across
    two lines in an actual document: ``"Acme Sup-\\nplies ..."``.
    """
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Acme Sup-")
    page.insert_text((72, 120), "plies Inc paid invoice #4521.")
    data = doc.tobytes()
    doc.close()
    return data


def test_redact_page_removes_name_split_across_a_line_break():
    """The raw-text fallback candidate (with its embedded line break) is found by
    real PyMuPDF search, fully removing a name that wraps across two lines, and
    the pseudonym label is written once rather than once per line fragment.
    """
    document = PyMuPdfDocument.open(_wrapped_name_pdf_bytes())
    assert document.page_text(0).startswith("Acme Sup-\nplies")

    document.redact_page(
        0, [(["Acme Supplies", "Acme Sup-\nplies"], "ORG-AUTO-D4D8B")]
    )
    redacted_bytes = document.to_bytes()
    document.close()

    redacted = PyMuPdfDocument.open(redacted_bytes)
    text = redacted.page_text(0)
    redacted.close()

    assert "Acme" not in text
    assert "Sup" not in text
    assert text.count("ORG-AUTO-D4D8B") == 1


def test_search_variants_collapses_whitespace():
    variants = _search_variants("Acme   Supplies")
    assert "Acme Supplies" in variants


def test_search_variants_removes_trailing_punctuation():
    variants = _search_variants("Acme Supplies, Ltd.")
    assert "Acme Supplies, Ltd" in variants


def test_search_variants_swaps_and_and_ampersand():
    variants = _search_variants("Acme & Supplies")
    assert "Acme and Supplies" in variants
    variants = _search_variants("Acme and Supplies")
    assert "Acme & Supplies" in variants


def test_search_variants_strips_org_suffix():
    variants = _search_variants("Acme Supplies Ltd")
    assert any(v == "Acme Supplies" for v in variants)
