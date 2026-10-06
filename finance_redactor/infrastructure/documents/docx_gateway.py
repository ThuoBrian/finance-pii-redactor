"""Word (.docx) read/write adapter (python-docx).

Implements the :class:`WordDocument` port. Wraps a ``docx.Document`` and
exposes only the operations the use case needs: enumerating paragraph
"blocks" (body, table cells, headers/footers), reading a block's flattened
text, and splicing pseudonyms back into the underlying runs so unaffected
text keeps its original formatting.

Hyperlinks are stripped on open, before any text is read (see
``_strip_hyperlinks``): the target could be ``mailto:`` a person, and
python-docx's ``paragraph.runs`` skips the runs inside ``<w:hyperlink>``, so
without this a link's *visible* text was never scanned either.
"""

from __future__ import annotations

import zipfile
from io import BytesIO
from typing import cast

from docx import Document as open_docx
from docx.document import Document
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.part import XmlPart
from docx.oxml.ns import qn
from docx.oxml.xmlchemy import BaseOxmlElement
from docx.table import Table
from docx.text.paragraph import Paragraph

from finance_redactor.domain.entities import Span
from finance_redactor.domain.errors import UnreadableFileError


def _table_paragraphs(table: Table) -> list[Paragraph]:
    """Return every paragraph in a table's cells, recursing into nested tables."""
    paragraphs: list[Paragraph] = []
    for row in table.rows:
        for cell in row.cells:
            paragraphs.extend(cell.paragraphs)
            for nested_table in cell.tables:
                paragraphs.extend(_table_paragraphs(nested_table))
    return paragraphs


_R_ID = qn("r:id")
_HYPERLINK = qn("w:hyperlink")
_FLD_SIMPLE = qn("w:fldSimple")
_INSTR = qn("w:instr")
_INSTR_TEXT = qn("w:instrText")
_FLD_CHAR = qn("w:fldChar")
_FLD_CHAR_TYPE = qn("w:fldCharType")


def _unwrap(element: BaseOxmlElement) -> None:
    """Replace ``element`` with its own children, in place."""
    parent = element.getparent()
    if parent is None:
        return
    index = parent.index(element)
    for offset, child in enumerate(list(element)):
        parent.insert(index + offset, child)
    parent.remove(element)


def _fld_char_type(run: BaseOxmlElement) -> str | None:
    fld_char = run.find(_FLD_CHAR)
    return None if fld_char is None else fld_char.get(_FLD_CHAR_TYPE)


def _remove_complex_field_code(instr_text: BaseOxmlElement) -> None:
    """Drop a ``HYPERLINK`` field's code runs and markers, keeping its result.

    A complex field is sibling runs: ``begin``, code (``instrText``),
    ``separate``, the visible result, ``end``. The result runs stay as plain
    text. If the layout isn't the expected one, blank the code instead, which
    still removes the target.
    """
    run = instr_text.getparent()
    parent = None if run is None else run.getparent()
    if run is None or parent is None:
        instr_text.text = ""
        return
    siblings = list(parent)
    index = siblings.index(run)
    begin = next(
        (i for i in range(index, -1, -1) if _fld_char_type(siblings[i]) == "begin"),
        None,
    )
    separate = next(
        (
            i
            for i in range(index, len(siblings))
            if _fld_char_type(siblings[i]) in {"separate", "end"}
        ),
        None,
    )
    if begin is None or separate is None:
        instr_text.text = ""
        return
    end = next(
        (
            i
            for i in range(separate, len(siblings))
            if _fld_char_type(siblings[i]) == "end"
        ),
        None,
    )
    doomed = siblings[begin : separate + 1]
    if end is not None and end != separate:
        doomed.append(siblings[end])
    for element in doomed:
        parent.remove(element)


def _strip_part_hyperlinks(part: XmlPart) -> int:
    """Strip every hyperlink from one XML part; return external targets removed."""
    external = {r_id for r_id, rel in part.rels.items() if rel.reltype == RT.HYPERLINK}
    root = part.element
    removed = 0
    # Internal (anchor) links are unwrapped too: their runs are just as
    # invisible to ``paragraph.runs``.
    for element in list(root.iter(_HYPERLINK)):
        if element.get(_R_ID) in external:
            removed += 1
        _unwrap(element)
    # Anything else pointing at a hyperlink relationship (a clickable image's
    # ``a:hlinkClick``, say) goes; a dangling r:id would corrupt the file.
    for element in list(root.iter()):
        if element.get(_R_ID) in external:
            removed += 1
            parent = element.getparent()
            if parent is not None:
                parent.remove(element)
    for r_id in external:
        part.rels.pop(r_id)
    for element in list(root.iter(_FLD_SIMPLE)):
        if "HYPERLINK" in (element.get(_INSTR) or "").upper():
            removed += 1
            _unwrap(element)
    for element in list(root.iter(_INSTR_TEXT)):
        if "HYPERLINK" in (element.text or "").upper():
            removed += 1
            _remove_complex_field_code(element)
    return removed


def _strip_hyperlinks(document: Document) -> int:
    """Strip hyperlinks from every XML part (body, headers, footers, notes)."""
    return sum(
        _strip_part_hyperlinks(part)
        for part in document.part.package.iter_parts()
        if isinstance(part, XmlPart)
    )


def _collect_paragraphs(document: Document) -> list[Paragraph]:
    """Enumerate every paragraph in the document: body, tables, headers/footers.

    Headers/footers linked across sections (``is_linked_to_previous``) share
    the same underlying part, so each distinct part is only visited once
    (tracked by ``id(part)``) to avoid scanning/replacing the same text twice.

    Known limitation: text inside text boxes, SmartArt, and embedded objects
    is not part of ``paragraph.runs`` and is not scanned - mirrors the PDF
    flow's "only the selectable text layer is processed" limitation.
    """
    paragraphs = list(document.paragraphs)
    for table in document.tables:
        paragraphs.extend(_table_paragraphs(table))

    seen_part_ids: set[int] = set()
    for section in document.sections:
        for header_or_footer in (section.header, section.footer):
            part_id = id(header_or_footer.part)
            if part_id in seen_part_ids:
                continue
            seen_part_ids.add(part_id)
            paragraphs.extend(header_or_footer.paragraphs)
            for table in header_or_footer.tables:
                paragraphs.extend(_table_paragraphs(table))
    return paragraphs


class PythonDocxDocument:
    """A single open Word document being pseudonymized paragraph by paragraph."""

    def __init__(self, document: Document) -> None:
        """Wrap an already-open python-docx ``Document`` and index its blocks.

        Hyperlinks are stripped first, so link text is part of the blocks.
        """
        self._document = document
        self._removed_links = _strip_hyperlinks(document)
        self._paragraphs = _collect_paragraphs(document)

    @classmethod
    def open(cls, source: object) -> PythonDocxDocument:
        """Open a .docx from bytes or a readable file-like object.

        Raises :class:`UnreadableFileError` for a corrupted document or one
        renamed to ``.docx`` without really being one - python-docx raises
        ``BadZipFile`` when the bytes aren't a zip at all, and ``KeyError``
        when they're a zip but missing the docx package parts.
        """
        data = source.read() if hasattr(source, "read") else source
        # `source` is deliberately typed as `object` at the port boundary (it
        # may be raw bytes or any file-like upload, e.g. Streamlit's
        # UploadedFile) - the actual runtime contract (bytes in, either way)
        # isn't expressible there without narrowing the port itself.
        try:
            return cls(open_docx(BytesIO(cast(bytes, data))))
        except (zipfile.BadZipFile, KeyError) as e:
            raise UnreadableFileError from e

    @property
    def block_count(self) -> int:
        """Total number of paragraph blocks."""
        return len(self._paragraphs)

    def block_text(self, block_index: int) -> str:
        """Return the flattened text (all runs concatenated) of one block."""
        return "".join(run.text for run in self._paragraphs[block_index].runs)

    def replace_block_text(
        self, block_index: int, replacements: list[tuple[Span, str]]
    ) -> None:
        """Splice each ``(span, pseudonym)`` into the block's runs in place.

        Spans are offsets into ``block_text(block_index)`` (the original,
        pre-replacement text). Replacements are applied right-to-left (like
        the domain's ``apply_replacements``) so an earlier span's offsets stay
        valid while a later one is rewritten. For a span crossing more than
        one run, the pseudonym is inserted once, in the run where the span
        starts (taking that run's formatting); any other run's overlapping
        portion is blanked, and text outside every span keeps its own run and
        formatting untouched.
        """
        runs = self._paragraphs[block_index].runs
        if not runs:
            return
        texts = [run.text for run in runs]
        starts: list[int] = []
        position = 0
        for text in texts:
            starts.append(position)
            position += len(text)
        lengths = [len(text) for text in texts]

        ordered = sorted(replacements, key=lambda item: item[0].start, reverse=True)
        for span, pseudonym in ordered:
            inserted = False
            for i in range(len(runs)):
                run_start = starts[i]
                run_end = run_start + lengths[i]
                overlap_start = max(span.start, run_start)
                overlap_end = min(span.end, run_end)
                if overlap_start >= overlap_end:
                    continue
                local_start = overlap_start - run_start
                local_end = overlap_end - run_start
                replacement_text = pseudonym if not inserted else ""
                texts[i] = (
                    texts[i][:local_start] + replacement_text + texts[i][local_end:]
                )
                inserted = True

        for run, text in zip(runs, texts):
            if run.text != text:
                run.text = text

    def remove_external_links(self) -> int:
        """Return how many link targets were stripped (done on open)."""
        return self._removed_links

    def to_bytes(self) -> bytes:
        """Render the pseudonymized document to bytes."""
        output = BytesIO()
        self._document.save(output)
        return output.getvalue()

    def close(self) -> None:
        """Release underlying resources (no-op: python-docx holds nothing open)."""
