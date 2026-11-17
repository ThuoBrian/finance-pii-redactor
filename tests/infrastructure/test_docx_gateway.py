"""Tests for the python-docx gateway.

Uses real ``python-docx`` objects (no mocks) to build fixture documents, the
same style as ``test_pdf_gateway.py`` for PyMuPDF.
"""

from __future__ import annotations

import re
from io import BytesIO

import pytest
from docx import Document
from docx.enum.section import WD_SECTION

from finance_redactor.domain.entities import Span
from finance_redactor.domain.errors import UnreadableFileError
from finance_redactor.infrastructure.documents.docx_gateway import PythonDocxDocument


def _build_docx(builder) -> bytes:
    """Build a .docx via ``builder(document)`` and return its bytes."""
    document = Document()
    builder(document)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_open_rejects_a_file_that_is_not_really_a_docx():
    """A corrupted or wrongly-renamed file surfaces as the shared error type,
    not python-docx's own ``BadZipFile``/``KeyError``.
    """
    with pytest.raises(UnreadableFileError):
        PythonDocxDocument.open(b"not a docx file at all")


def test_blocks_cover_body_table_and_header_paragraphs():
    def build(document):
        document.add_paragraph("A memo about John Doe.")
        table = document.add_table(rows=1, cols=1)
        table.cell(0, 0).text = "Vendor: Acme Supplies"
        document.sections[0].header.paragraphs[0].text = "Confidential memo"

    gateway = PythonDocxDocument.open(_build_docx(build))
    texts = [gateway.block_text(i) for i in range(gateway.block_count)]

    assert "A memo about John Doe." in texts
    assert "Vendor: Acme Supplies" in texts
    assert "Confidential memo" in texts


def test_linked_headers_are_not_scanned_twice():
    def build(document):
        document.add_paragraph("body one")
        document.add_section(WD_SECTION.NEW_PAGE)
        document.add_paragraph("body two")
        document.sections[0].header.paragraphs[0].text = "Shared header"

    gateway = PythonDocxDocument.open(_build_docx(build))
    texts = [gateway.block_text(i) for i in range(gateway.block_count)]

    assert texts.count("Shared header") == 1


def test_replace_block_text_confined_to_one_run():
    def build(document):
        document.add_paragraph("Hello World and more text")

    gateway = PythonDocxDocument.open(_build_docx(build))
    text = gateway.block_text(0)
    start = text.index("World")

    gateway.replace_block_text(0, [(Span(start, start + len("World")), "STF-1")])

    assert gateway.block_text(0) == "Hello STF-1 and more text"


def test_replace_block_text_preserves_formatting_outside_the_span():
    def build(document):
        paragraph = document.add_paragraph("Hello ")
        bold_run = paragraph.add_run("World")
        bold_run.bold = True
        paragraph.add_run(" and more text")

    gateway = PythonDocxDocument.open(_build_docx(build))
    text = gateway.block_text(0)
    start = text.index("World")

    # Span crosses from the plain prefix run into the bold "World" run.
    gateway.replace_block_text(0, [(Span(start - 2, start + len("World")), "PSN-2")])

    runs = gateway._paragraphs[0].runs
    assert runs[-1].text == " and more text"
    assert runs[-1].bold is None
    assert "PSN-2" in "".join(r.text for r in runs)


def test_replace_block_text_handles_multiple_spans_in_one_call():
    def build(document):
        document.add_paragraph("John paid Mary today")

    gateway = PythonDocxDocument.open(_build_docx(build))
    text = gateway.block_text(0)
    john = text.index("John")
    mary = text.index("Mary")

    gateway.replace_block_text(
        0,
        [
            (Span(john, john + 4), "STF-1"),
            (Span(mary, mary + 4), "STF-2"),
        ],
    )

    assert gateway.block_text(0) == "STF-1 paid STF-2 today"


def test_to_bytes_round_trips_replacements():
    def build(document):
        document.add_paragraph("Invoice for John Doe")

    gateway = PythonDocxDocument.open(_build_docx(build))
    text = gateway.block_text(0)
    start = text.index("John Doe")
    gateway.replace_block_text(0, [(Span(start, start + len("John Doe")), "STF-99")])

    reopened = PythonDocxDocument.open(gateway.to_bytes())
    assert "STF-99" in reopened.block_text(0)
    assert "John" not in reopened.block_text(0)


# --- Hyperlinks ---------------------------------------------------------------

_TARGET = "mailto:jane.doe@example.org"


def _add_hyperlink(paragraph, text: str, target: str = _TARGET) -> None:
    """Append a real external ``<w:hyperlink>`` (python-docx has no API for it)."""
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    r_id = paragraph.part.relate_to(target, RT.HYPERLINK, is_external=True)
    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), r_id)
    run = OxmlElement("w:r")
    text_el = OxmlElement("w:t")
    text_el.text = text
    run.append(text_el)
    link.append(run)
    paragraph._p.append(link)


def _add_field_run(paragraph, *, fld_char: str | None = None, instr: str | None = None):
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    run = OxmlElement("w:r")
    if fld_char:
        element = OxmlElement("w:fldChar")
        element.set(qn("w:fldCharType"), fld_char)
        run.append(element)
    if instr:
        element = OxmlElement("w:instrText")
        element.text = instr
        run.append(element)
    paragraph._p.append(run)


def test_hyperlink_text_is_scanned_and_its_target_is_removed():
    """Regression: ``paragraph.runs`` skipped link runs, so the text leaked too."""

    def build(document):
        paragraph = document.add_paragraph("Contact ")
        _add_hyperlink(paragraph, "Jane Doe")

    gateway = PythonDocxDocument.open(_build_docx(build))

    assert gateway.block_text(0) == "Contact Jane Doe"
    assert gateway.remove_external_links() == 1
    gateway.replace_block_text(0, [(Span(8, 16), "STF-10010")])
    output = gateway.to_bytes()
    assert b"mailto:" not in output
    reopened = Document(BytesIO(output))
    assert reopened.paragraphs[0].text == "Contact STF-10010"
    assert all("hyperlink" not in rel.reltype for rel in reopened.part.rels.values())


def test_hyperlink_in_a_header_is_removed():
    def build(document):
        _add_hyperlink(document.sections[0].header.paragraphs[0], "Jane Doe")

    gateway = PythonDocxDocument.open(_build_docx(build))

    assert gateway.remove_external_links() == 1
    assert "Jane Doe" in [gateway.block_text(i) for i in range(gateway.block_count)]
    assert b"mailto:" not in gateway.to_bytes()


def test_hyperlink_field_code_is_removed_and_its_result_kept():
    def build(document):
        paragraph = document.add_paragraph("See ")
        _add_field_run(paragraph, fld_char="begin")
        _add_field_run(paragraph, instr=f' HYPERLINK "{_TARGET}" ')
        _add_field_run(paragraph, fld_char="separate")
        paragraph.add_run("Jane Doe")
        _add_field_run(paragraph, fld_char="end")

    gateway = PythonDocxDocument.open(_build_docx(build))

    assert gateway.remove_external_links() == 1
    assert gateway.block_text(0) == "See Jane Doe"
    output = gateway.to_bytes()
    assert b"mailto:" not in output
    assert b"fldChar" not in output


def test_simple_hyperlink_field_is_unwrapped():
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    def build(document):
        paragraph = document.add_paragraph("See ")
        field = OxmlElement("w:fldSimple")
        field.set(qn("w:instr"), f' HYPERLINK "{_TARGET}" ')
        run = OxmlElement("w:r")
        text_el = OxmlElement("w:t")
        text_el.text = "Jane Doe"
        run.append(text_el)
        field.append(run)
        paragraph._p.append(field)

    gateway = PythonDocxDocument.open(_build_docx(build))

    assert gateway.remove_external_links() == 1
    assert gateway.block_text(0) == "See Jane Doe"
    assert b"mailto:" not in gateway.to_bytes()


def test_document_without_links_reports_zero():
    gateway = PythonDocxDocument.open(
        _build_docx(lambda d: d.add_paragraph("No links here."))
    )
    assert gateway.remove_external_links() == 0


def test_to_bytes_strips_document_properties_and_author_parts():
    """Core properties are blanked and app props/thumbnail parts dropped; text stays."""

    def build(document):
        document.add_paragraph("Paid to Jane Doe")
        core = document.core_properties
        core.author = "Pat Example"
        core.last_modified_by = "Sam Example"
        core.title = "Payroll Review"
        core.comments = "internal note"
        core.keywords = "k1"

    source = _build_docx(build)
    assert b"Pat Example" in _all_zip_text(source)  # the fixture really carries it
    gateway = PythonDocxDocument.open(source)
    out = gateway.to_bytes()
    gateway.close()

    reopened = Document(BytesIO(out))
    core = reopened.core_properties
    assert core.author == ""
    assert core.last_modified_by == ""
    assert core.title == ""
    assert core.comments == ""
    assert core.keywords == ""
    assert core.created.year == 1970
    rel_types = {
        rel.reltype.rsplit("/", 1)[-1] for rel in reopened.part.package.rels.values()
    }
    assert not rel_types & {"extended-properties", "custom-properties", "thumbnail"}
    assert any(p.text == "Paid to Jane Doe" for p in reopened.paragraphs)
    for leaked in (b"Pat Example", b"Sam Example", b"Payroll Review", b"internal note"):
        assert leaked not in _all_zip_text(out)


def _all_zip_text(data: bytes) -> bytes:
    import zipfile

    with zipfile.ZipFile(BytesIO(data)) as archive:
        return b"".join(archive.read(name) for name in archive.namelist())


# --- Hidden surfaces: every part of the output is checked ---------------------

_NAME = "Jane Testperson"


def _redact_token(gateway: PythonDocxDocument, token: str) -> int:
    """Replace every occurrence of ``token`` in every block, as the use case would.

    Returns how many blocks contained it, so a test can prove the scan saw it.
    """
    hits = 0
    for index in range(gateway.block_count):
        text = gateway.block_text(index)
        spans = []
        start = text.find(token)
        while start != -1:
            spans.append((Span(start, start + len(token)), "STF-1"))
            start = text.find(token, start + 1)
        if spans:
            hits += 1
            gateway.replace_block_text(index, spans)
    return hits


def _zip_parts(data: bytes) -> dict[str, bytes]:
    import zipfile

    with zipfile.ZipFile(BytesIO(data)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _assert_gone(data: bytes, *tokens: str) -> None:
    """Fail naming the part (never the value) if a token survives anywhere."""
    for name, blob in _zip_parts(data).items():
        for number, token in enumerate(tokens):
            assert token.encode() not in blob, f"token #{number} survives in {name}"


@pytest.mark.parametrize(
    "attr",
    ["first_page_header", "even_page_header", "first_page_footer", "even_page_footer"],
)
def test_first_and_even_page_headers_and_footers_are_redacted(attr):
    def build(document):
        document.add_paragraph("Body text")
        section = document.sections[0]
        section.different_first_page_header_footer = True
        document.settings.odd_and_even_pages_header_footer = True
        getattr(section, attr).paragraphs[0].text = f"Prepared by {_NAME}"

    source = _build_docx(build)
    assert _NAME.encode() in _all_zip_text(source)  # the fixture really carries it
    gateway = PythonDocxDocument.open(source)

    assert _redact_token(gateway, _NAME) == 1
    _assert_gone(gateway.to_bytes(), _NAME)


def test_unused_headers_and_footers_are_not_added_to_the_output():
    gateway = PythonDocxDocument.open(_build_docx(lambda d: d.add_paragraph("x")))
    parts = _zip_parts(gateway.to_bytes())
    assert not [name for name in parts if "header" in name or "footer" in name]


# --- Tracked changes, comments, footnotes and endnotes -------------------------

_AUTHOR = "Pat Reviewer"
_REV = f'w:id="9" w:author="{_AUTHOR}" w:date="2026-01-01T00:00:00Z"'


def _xml(fragment: str):
    from docx.oxml import parse_xml
    from docx.oxml.ns import nsdecls

    # Declare the namespace on the fragment's root element, after its tag name.
    return parse_xml(re.sub(r"^(<[\w:]+)", rf"\1 {nsdecls('w')}", fragment))


def _open_and_redact(build) -> bytes:
    source = _build_docx(build)
    assert _NAME.encode() in _all_zip_text(source)  # the fixture really carries it
    gateway = PythonDocxDocument.open(source)
    _redact_token(gateway, _NAME)
    return gateway.to_bytes()


def test_tracked_insertion_is_scanned_and_accepted():
    def build(document):
        paragraph = document.add_paragraph("Paid to ")
        paragraph._p.append(
            _xml(f"<w:ins {_REV}><w:r><w:t>{_NAME}</w:t></w:r></w:ins>")
        )

    gateway = PythonDocxDocument.open(_build_docx(build))
    assert gateway.block_text(0) == f"Paid to {_NAME}"
    assert _redact_token(gateway, _NAME) == 1
    output = gateway.to_bytes()

    _assert_gone(output, _NAME, _AUTHOR, "w:author", "<w:ins ")
    assert Document(BytesIO(output)).paragraphs[0].text == "Paid to STF-1"


def test_tracked_deletion_is_dropped():
    def build(document):
        paragraph = document.add_paragraph("Paid to ")
        paragraph._p.append(
            _xml(f"<w:del {_REV}><w:r><w:delText>{_NAME}</w:delText></w:r></w:del>")
        )
        paragraph.add_run("the vendor")

    output = _open_and_redact(build)

    _assert_gone(output, _NAME, _AUTHOR, "w:author", "delText")
    assert Document(BytesIO(output)).paragraphs[0].text == "Paid to the vendor"


def test_deleted_table_row_is_dropped():
    def build(document):
        table = document.add_table(rows=2, cols=1)
        table.cell(0, 0).text = "Kept row"
        table.cell(1, 0).text = _NAME
        table.rows[1]._tr.get_or_add_trPr().append(_xml(f"<w:del {_REV}/>"))

    output = _open_and_redact(build)

    _assert_gone(output, _NAME, _AUTHOR)
    assert len(Document(BytesIO(output)).tables[0].rows) == 1


def test_tracked_move_keeps_only_the_new_location():
    def build(document):
        old = document.add_paragraph()
        old._p.append(
            _xml(f"<w:moveFrom {_REV}><w:r><w:t>{_NAME}</w:t></w:r></w:moveFrom>")
        )
        new = document.add_paragraph()
        new._p.append(
            _xml(f"<w:moveTo {_REV}><w:r><w:t>Moved line</w:t></w:r></w:moveTo>")
        )

    output = _open_and_redact(build)

    _assert_gone(output, _NAME, _AUTHOR, "w:author")
    assert [p.text for p in Document(BytesIO(output)).paragraphs] == ["", "Moved line"]


def test_comment_text_author_and_anchors_are_removed():
    from docx.opc.packuri import PackURI
    from docx.opc.part import Part

    def build(document):
        paragraph = document.add_paragraph("Approved payment")
        document.add_comment(
            paragraph.runs, text=f"Ask {_NAME}", author=_AUTHOR, initials="PR"
        )
        people = Part(
            PackURI("/word/people.xml"),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.people+xml",
            f'<w15:people xmlns:w15="http://schemas.microsoft.com/office/word/2012/'
            f'wordml"><w15:person w15:author="{_AUTHOR}"/></w15:people>'.encode(),
            document.part.package,
        )
        document.part.relate_to(
            people, "http://schemas.microsoft.com/office/2011/relationships/people"
        )

    source = _build_docx(build)
    assert b"commentReference" in _all_zip_text(source)
    output = _open_and_redact(build)

    _assert_gone(output, _NAME, _AUTHOR, "commentRange", "commentReference")
    assert not [name for name in _zip_parts(output) if "comment" in name]
    assert not [name for name in _zip_parts(output) if "people" in name]
    assert Document(BytesIO(output)).paragraphs[0].text == "Approved payment"


@pytest.mark.parametrize(
    ("kind", "content_type", "reltype"),
    [
        ("footnote", "WML_FOOTNOTES", "FOOTNOTES"),
        ("endnote", "WML_ENDNOTES", "ENDNOTES"),
    ],
)
def test_footnote_and_endnote_text_is_scanned_and_redacted(kind, content_type, reltype):
    from docx.opc.constants import CONTENT_TYPE as CT
    from docx.opc.constants import RELATIONSHIP_TYPE as RT
    from docx.opc.packuri import PackURI
    from docx.opc.part import Part
    from docx.oxml.ns import nsdecls

    def build(document):
        paragraph = document.add_paragraph("See note")
        paragraph._p.append(_xml(f'<w:r><w:{kind}Reference w:id="1"/></w:r>'))
        notes = (
            f"<w:{kind}s {nsdecls('w')}>"
            f'<w:{kind} w:id="1"><w:p><w:r><w:t>Source: {_NAME}</w:t></w:r></w:p>'
            f"<w:tbl><w:tr><w:tc><w:p><w:r><w:t>{_NAME}</w:t></w:r></w:p></w:tc>"
            f"</w:tr></w:tbl></w:{kind}></w:{kind}s>"
        )
        part = Part(
            PackURI(f"/word/{kind}s.xml"),
            getattr(CT, content_type),
            notes.encode(),
            document.part.package,
        )
        document.part.relate_to(part, getattr(RT, reltype))

    gateway = PythonDocxDocument.open(_build_docx(build))
    assert _redact_token(gateway, _NAME) == 2  # the note paragraph and its table cell
    output = gateway.to_bytes()

    _assert_gone(output, _NAME)
    assert f"word/{kind}s.xml" in _zip_parts(output)  # redacted, not dropped
