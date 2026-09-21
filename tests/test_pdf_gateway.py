"""Tests for PyMuPDF gateway helpers."""

from __future__ import annotations

import fitz
import pytest

from finance_redactor.domain.errors import EncryptedPdfError
from finance_redactor.infrastructure.documents.pdf_gateway import (
    PyMuPdfDocument,
    _search_variants,
    _tighten_to_line,
)


def _wrapped_name_pdf_bytes() -> bytes:
    r"""Build a real one-page PDF where a name is split by a soft-hyphen line break.

    Mirrors what PyMuPDF's ``get_text()`` extracts for a name that wraps across
    two lines in an actual document: ``"Acme Sup-\nplies ..."``.
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

    document.redact_page(0, [(["Acme Supplies", "Acme Sup-\nplies"], "ORG-AUTO-D4D8B")])
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


def _tightly_spaced_two_line_pdf_bytes(line_gap: float, name: str) -> bytes:
    """Build a real one-page PDF with two lines ``line_gap`` points apart.

    ``page.search_for()``'s rect height comes from font ascent/descent
    metrics, not the document's actual line spacing - a small enough
    ``line_gap`` reproduces a redaction rect taller than the real gap between
    lines (see ``_tighten_to_line``).
    """
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Approved by manager for payment processing.")
    page.insert_text((72, 100 + line_gap), f"Paid to {name} for consulting services.")
    data = doc.tobytes()
    doc.close()
    return data


def test_redact_page_does_not_delete_text_from_the_line_above():
    """A tightly single-spaced line above the redacted name must survive.

    Reproduces a bug where page.search_for()'s font-metrics-derived rect was
    taller than the real single-spaced line gap, so covering it as-is caused
    apply_redactions() to also remove glyphs from the unrelated line above.
    """
    document = PyMuPdfDocument.open(
        _tightly_spaced_two_line_pdf_bytes(11, "John Smith")
    )

    document.redact_page(0, [("John Smith", "STF-91345")], blackout=True)
    redacted_bytes = document.to_bytes()
    document.close()

    redacted = PyMuPdfDocument.open(redacted_bytes)
    text = redacted.page_text(0)
    redacted.close()

    assert "Approved by manager for payment processing." in text
    assert "John" not in text
    assert "Smith" not in text


def test_tighten_to_line_shrinks_symmetrically():
    rect = fitz.Rect(10, 100, 50, 115)
    tightened = _tighten_to_line(rect, ratio=0.2)

    assert tightened.x0 == rect.x0
    assert tightened.x1 == rect.x1
    assert tightened.y0 == rect.y0 + 3
    assert tightened.y1 == rect.y1 - 3


def _encrypted_pdf_bytes(*, user_pw: str | None) -> bytes:
    """Build a one-page encrypted PDF carrying obviously-synthetic contact text.

    ``user_pw=None`` produces the owner-password-only case: restricted
    permissions, but no password needed to open it. Passing a user password
    produces the "Acrobat prompts before showing anything" case.
    """
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Contact jane.test@example.org about invoice #4521.")
    data = doc.tobytes(
        encryption=fitz.PDF_ENCRYPT_AES_256,
        owner_pw="owner-test-pw",
        user_pw=user_pw,
        permissions=int(fitz.PDF_PERM_ACCESSIBILITY | fitz.PDF_PERM_PRINT),
    )
    doc.close()
    return data


def test_open_rejects_a_password_protected_pdf():
    """A user (open) password is refused up front rather than surfacing later as
    PyMuPDF's bare ValueError on the first page read.
    """
    data = _encrypted_pdf_bytes(user_pw="user-test-pw")

    with pytest.raises(EncryptedPdfError):
        PyMuPdfDocument.open(data)


def test_encrypted_pdf_error_carries_no_document_content():
    """The error must not echo the document's text into a traceback."""
    data = _encrypted_pdf_bytes(user_pw="user-test-pw")

    with pytest.raises(EncryptedPdfError) as excinfo:
        PyMuPdfDocument.open(data)

    assert str(excinfo.value) == ""


def test_open_accepts_an_owner_password_only_pdf():
    """Restricted permissions without an open password still redact normally -
    the needs_pass check must not reject this far more common case.
    """
    document = PyMuPdfDocument.open(_encrypted_pdf_bytes(user_pw=None))

    assert document.page_count == 1
    assert "jane.test@example.org" in document.page_text(0)

    document.redact_page(0, [("jane.test@example.org", "EML-AUTO-1A2B3")])
    redacted_bytes = document.to_bytes()
    document.close()

    redacted = PyMuPdfDocument.open(redacted_bytes)
    text = redacted.page_text(0)
    redacted.close()

    assert "jane.test" not in text
    assert "example.org" not in text
    assert "EML-AUTO-1A2B3" in text
    # The redacted copy is what gets downloaded, so the address must be gone
    # from the raw bytes too, not merely covered in the rendered page.
    assert b"jane.test@example.org" not in redacted_bytes
