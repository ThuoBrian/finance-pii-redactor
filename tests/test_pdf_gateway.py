"""Tests for PyMuPDF gateway helpers."""

from __future__ import annotations

from finance_redactor.infrastructure.documents.pdf_gateway import _search_variants


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
