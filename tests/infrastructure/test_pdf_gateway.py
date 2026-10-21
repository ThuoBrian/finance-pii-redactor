"""Tests for PyMuPDF gateway helpers."""

from __future__ import annotations

import fitz
import pytest

from finance_redactor.domain.entities import IMAGE_REDACTION_SENTINEL
from finance_redactor.domain.errors import EncryptedPdfError, UnreadableFileError
from finance_redactor.infrastructure.documents.pdf_gateway import (
    PyMuPdfDocument,
    _drop_embedded_hits,
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

    document.redact_page(0, [("John Smith", "STF-10010")], blackout=True)
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


def test_open_rejects_a_file_that_is_not_really_a_pdf():
    """A corrupted or wrongly-renamed file surfaces as the shared error type,
    not PyMuPDF's own ``FileDataError``.
    """
    with pytest.raises(UnreadableFileError):
        PyMuPdfDocument.open(b"not a pdf file at all")


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


def test_remove_external_links_keeps_internal_page_jumps():
    doc = fitz.open()
    doc.new_page()
    doc.new_page()
    first = doc[0]
    first.insert_text((72, 100), "Contact Jane Doe")
    first.insert_link(
        {
            "kind": fitz.LINK_URI,
            "from": fitz.Rect(72, 90, 200, 105),
            "uri": "mailto:jane.doe@example.org",
        }
    )
    first.insert_link(
        {"kind": fitz.LINK_GOTO, "from": fitz.Rect(72, 120, 200, 135), "page": 1}
    )
    data = doc.tobytes()
    doc.close()

    document = PyMuPdfDocument.open(data)
    assert document.remove_external_links() == 1
    output = document.to_bytes()
    document.close()

    reopened = fitz.open(stream=output, filetype="pdf")
    assert [link["kind"] for link in reopened[0].get_links()] == [fitz.LINK_GOTO]
    assert b"mailto:" not in output
    # The visible text is untouched; detection decides what happens to it.
    assert "Jane Doe" in reopened[0].get_text()
    reopened.close()


def test_to_bytes_strips_document_properties_and_xmp():
    """Author, title and XMP survive text redaction untouched, so to_bytes drops them."""
    doc = fitz.open()
    doc.new_page().insert_text((72, 100), "Paid to Jane Doe")
    doc.set_metadata(
        {
            "author": "Pat Example",
            "title": "Payroll Review",
            "subject": "Subject Line",
            "keywords": "k1, k2",
            "creator": "Example Writer",
            "producer": "Example PDF Tool",
        }
    )
    doc.set_xml_metadata("<x:xmpmeta xmlns:x='adobe:ns:meta/'>Pat Example</x:xmpmeta>")
    data = doc.tobytes()
    doc.close()
    assert b"Pat Example" in data  # the fixture really carries it

    document = PyMuPdfDocument.open(data)
    document.redact_page(0, [(["Jane Doe"], "[001]")])
    out = document.to_bytes()
    document.close()

    reopened = fitz.open(stream=out, filetype="pdf")
    metadata = reopened.metadata
    reopened.close()
    assert all(
        not metadata[key]
        for key in ("author", "title", "subject", "keywords", "creator", "producer")
    )
    for leaked in (b"Pat Example", b"Payroll Review", b"Example PDF Tool", b"xmpmeta"):
        assert leaked not in out


def _text_pdf_bytes(*lines: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    for i, line in enumerate(lines):
        page.insert_text((72, 100 + 20 * i), line)
    data = doc.tobytes()
    doc.close()
    return data


def _redacted_text(data: bytes, redactions: list) -> str:
    document = PyMuPdfDocument.open(data)
    document.redact_page(0, redactions)
    redacted = PyMuPdfDocument.open(document.to_bytes())
    document.close()
    text = redacted.page_text(0)
    redacted.close()
    return text


def test_redact_page_leaves_a_short_word_alone_inside_longer_words():
    """Detection is whole-word, so the locate step must be too: redacting the
    word "IPA" must not black out the same letters inside "principal".
    """
    data = _text_pdf_bytes(
        "IPA approved the principal participant list.",
        "Also (IPA) and IPA's and IPA-funded work, municipal.",
    )

    text = _redacted_text(data, [(["IPA"], "[001]")])

    assert "principal" in text
    assert "participant" in text
    assert "municipal" in text
    assert text.count("[001]") == 4  # IPA, (IPA), IPA's, IPA-funded
    assert "IPA " not in text.replace("[001]", "")


def test_drop_embedded_hits_keeps_every_hit_when_they_cannot_be_lined_up():
    """Fail safe: if the hit count and the text-occurrence count differ, nothing
    is dropped - a stray extra redaction beats a name left showing.
    """
    rects = [fitz.Rect(0, 0, 1, 1), fitz.Rect(2, 0, 3, 1)]

    # 3 occurrences in the text but only 2 hits: cannot be matched up.
    assert _drop_embedded_hits(rects, "IPA and principal and IPA", "IPA") == rects

    assert _drop_embedded_hits(rects, "IPA", "IPA") == rects  # 1 occurrence, 2 hits


def test_drop_embedded_hits_ignores_a_non_word_edge():
    """A candidate that ends in punctuation is not "inside" a word because of it."""
    rects = [fitz.Rect(0, 0, 1, 1)]

    assert _drop_embedded_hits(rects, "Acme Ltd.x", "Acme Ltd.") == rects
    assert _drop_embedded_hits(rects, "xIPA", "IPA") == []


_INK = (10, 20, 30)  # a made-up "signature" stroke colour, easy to look for


def _signature_pdf_bytes() -> bytes:
    """One page: a line of text and a made-up signature image (an ink stroke)."""
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 60, 20), False)
    pix.clear_with(255)
    for x in range(60):
        pix.set_pixel(x, 10, _INK)
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 80), "Signed by Jane Doe:")
    page.insert_image(fitz.Rect(72, 90, 272, 160), stream=pix.tobytes("png"))
    data = doc.tobytes()
    doc.close()
    return data


def _ink_survives(pdf_bytes: bytes) -> bool:
    """Return True if any image left in the PDF still holds the signature stroke."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        for img in doc[0].get_images(full=True):
            pix = fitz.Pixmap(doc.extract_image(img[0])["image"])
            if pix.width > 30 and pix.height > 10 and pix.pixel(30, 10)[:3] == _INK:
                return True
        return False
    finally:
        doc.close()


def test_blacked_out_image_cannot_be_pulled_back_out_of_the_pdf():
    """A black box drawn over an image is not redaction: the image must go too."""
    data = _signature_pdf_bytes()
    assert _ink_survives(data)  # the fixture really holds the signature

    document = PyMuPdfDocument.open(data)
    document.redact_page(0, [(IMAGE_REDACTION_SENTINEL, "")], blackout=True)
    out = document.to_bytes()
    document.close()

    assert not _ink_survives(out)


def test_text_redaction_still_works_on_a_page_with_an_image():
    data = _signature_pdf_bytes()

    document = PyMuPdfDocument.open(data)
    document.redact_page(0, [(["Jane Doe"], "[001]"), (IMAGE_REDACTION_SENTINEL, "")])
    out = document.to_bytes()
    document.close()

    reopened = PyMuPdfDocument.open(out)
    text = reopened.page_text(0)
    reopened.close()
    assert "Jane Doe" not in text
    assert "[001]" in text
    assert not _ink_survives(out)


def _scan_pdf_bytes() -> bytes:
    """Build a made-up "scan": one picture of text plus a signature scribble."""
    import numpy as np

    text_page = fitz.open()
    page = text_page.new_page()
    page.insert_text((72, 100), "Payment voucher", fontsize=12)
    page.insert_text((72, 130), "Paid to Jane Doe for field work.", fontsize=12)
    pix = page.get_pixmap(dpi=200, colorspace=fitz.csRGB, alpha=False)
    image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    image = image.copy()
    for i in range(400):  # the "signature": a dark diagonal stroke lower down
        image[900 + i // 8 : 904 + i // 8, 300 + i] = 20
    picture = fitz.Pixmap(fitz.csRGB, pix.width, pix.height, image.tobytes(), False)
    scan = fitz.open()
    scan.new_page().insert_image(
        fitz.Rect(0, 0, 595, 842), stream=picture.tobytes("png")
    )
    data = scan.tobytes()
    text_page.close()
    scan.close()
    return data


def _only_image(pdf_bytes: bytes):
    import numpy as np

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    (img,) = doc[0].get_images(full=True)
    pix = fitz.Pixmap(doc.extract_image(img[0])["image"])
    if pix.n != 3:
        pix = fitz.Pixmap(fitz.csRGB, pix)
    text = doc[0].get_text()
    doc.close()
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(
        pix.height, pix.width, 3
    ), text


_KEEP = [(190, 240, 1000, 380)]  # the two printed lines, in 200 dpi pixels
_NAME = (300, 325, 470, 375)  # where "Jane Doe" is taken to be
# Points on the made-up signature stroke (row, column), in 200 dpi pixels.
_STROKE = [(901 + i // 8, 300 + i) for i in range(0, 400, 25)]


def _stroke_values(image) -> set[int]:
    return {int(image[row, col, 0]) for row, col in _STROKE}


def test_rebuilt_scan_keeps_read_text_labels_names_and_blacks_out_the_rest():
    document = PyMuPdfDocument.open(_scan_pdf_bytes())
    document.rebuild_scanned_page(
        0,
        200,
        keep=_KEEP,
        names=[(_NAME, "[001]")],
        blackout_names=False,
        blackout_other_ink=True,
    )
    image, text = _only_image(document.to_bytes())
    document.close()

    assert (image[325:375, 300:470] == 255).all()  # the name is gone from the picture
    assert "[001]" in text  # and the label is written in its place
    assert _stroke_values(image) == {0}  # the signature is blacked out
    # ...as one solid box, so its shape does not show through.
    assert (image[905:945, 330:680] == 0).all()
    assert (image[240:320, 190:1000] < 100).any()  # the kept text is still there


def test_rebuilt_scan_leaves_other_ink_when_image_blackout_is_off():
    document = PyMuPdfDocument.open(_scan_pdf_bytes())
    document.rebuild_scanned_page(
        0,
        200,
        keep=_KEEP,
        names=[(_NAME, "[001]")],
        blackout_names=False,
        blackout_other_ink=False,
    )
    image, _ = _only_image(document.to_bytes())
    document.close()

    assert (image[325:375, 300:470] == 255).all()
    assert _stroke_values(image) == {20}  # untouched: the original stroke


def test_rebuilt_scan_in_blackout_style_blacks_the_name_without_a_label():
    document = PyMuPdfDocument.open(_scan_pdf_bytes())
    document.rebuild_scanned_page(
        0,
        200,
        keep=_KEEP,
        names=[(_NAME, "[001]")],
        blackout_names=True,
        blackout_other_ink=True,
    )
    image, text = _only_image(document.to_bytes())
    document.close()

    assert (image[325:375, 300:470] == 0).all()
    assert "[001]" not in text
