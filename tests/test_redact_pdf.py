"""Tests for the PDF pseudonymization use case.

Framework-free: a fake :class:`PdfDocument` and detector stand in for PyMuPDF
and Presidio, so these tests run without the heavy language model.
"""

from __future__ import annotations

import pytest

from finance_redactor.application.redact_pdf import RedactPdfService
from finance_redactor.domain.entities import DetectionSource, PiiDetection, Span


class FakePdfDocument:
    """In-memory PDF double for testing RedactPdfService."""

    def __init__(self, pages: list[str]) -> None:
        """Create a fake document with the given page texts."""
        self._pages = pages
        self.redactions_by_page: dict[int, list[tuple[str, str]]] = {}
        self.closed = False

    @property
    def page_count(self) -> int:
        """Return the number of pages."""
        return len(self._pages)

    def page_text(self, page_index: int) -> str:
        """Return the text of the requested page."""
        return self._pages[page_index]

    def redact_page(self, page_index: int, redactions: list[tuple[str, str]]) -> None:
        """Record the redactions applied to this page."""
        self.redactions_by_page[page_index] = redactions

    def to_bytes(self) -> bytes:
        """Render the document to bytes (here, the joined page texts)."""
        return b"\n---PAGE---\n".join(p.encode("utf-8") for p in self._pages)

    def close(self) -> None:
        """Mark the document as closed."""
        self.closed = True


def _document_factory(source: object) -> FakePdfDocument:
    """Return the FakePdfDocument passed as the source."""
    assert isinstance(source, FakePdfDocument)
    return source


class _NameDetector:
    """Fake detector: flags the literal names ``John`` and ``Mary``."""

    _NAMES = ("John", "Mary")

    def analyze(
        self, text: str, entities: list[str], threshold: float
    ) -> list[PiiDetection]:
        """Return a detection for each configured name found in ``text``."""
        if "PERSON" not in entities:
            return []
        detections: list[PiiDetection] = []
        for name in self._NAMES:
            idx = text.find(name)
            if idx != -1:
                detections.append(
                    PiiDetection(
                        entity_type="PERSON",
                        span=Span(idx, idx + len(name)),
                        score=0.99,
                        text=name,
                        source=DetectionSource.MODEL,
                    )
                )
        return detections


def _service(detector: _NameDetector | None = None) -> RedactPdfService:
    return RedactPdfService(
        detector=detector or _NameDetector(),
        open_document=_document_factory,
        master_map={},
        auto_prefixes={"PERSON": "PSN"},
    )


def test_execute_returns_redacted_document_and_findings() -> None:
    """The service redacts every page, records findings, and returns bytes."""
    doc = FakePdfDocument(
        ["John paid invoice 1", "No name here", "John paid invoice 2"]
    )
    result = _service().execute(doc, ["PERSON"], 0.35)

    assert result.page_count == 3
    assert result.entity_count == 2
    assert result.data == doc.to_bytes()
    assert doc.closed is True
    assert result.findings[0].page == 0
    assert result.findings[0].detected_text == "John"
    assert result.findings[1].page == 2


def test_pseudonym_is_consistent_across_pages() -> None:
    """The same name on different pages maps to the same pseudonym."""
    doc = FakePdfDocument(["John paid", "John approved"])
    _service().execute(doc, ["PERSON"], 0.35)

    page_0_label = doc.redactions_by_page[0][0][1]
    page_1_label = doc.redactions_by_page[1][0][1]
    assert page_0_label == page_1_label
    assert page_0_label.startswith("PSN-AUTO-")


def test_empty_pages_are_skipped() -> None:
    """Pages with no text do not produce findings or redactions."""
    doc = FakePdfDocument(["", "John paid", "   "])
    result = _service().execute(doc, ["PERSON"], 0.35)

    assert result.entity_count == 1
    assert 0 not in doc.redactions_by_page
    assert 2 not in doc.redactions_by_page
    assert 1 in doc.redactions_by_page


def test_crosswalk_lists_distinct_assignments() -> None:
    """The crosswalk contains each distinct name->pseudonym assignment once."""
    doc = FakePdfDocument(["John paid", "John approved", "Mary paid"])
    result = _service().execute(doc, ["PERSON"], 0.35)

    assert len(result.crosswalk) == 2
    names = {a.original_name for a in result.crosswalk}
    assert names == {"John", "Mary"}
    assert all(a.auto for a in result.crosswalk)


def test_document_is_closed_even_on_detector_error() -> None:
    """The underlying document is closed if the pipeline raises."""

    class FailingDetector:
        def analyze(
            self, text: str, entities: list[str], threshold: float
        ) -> list[PiiDetection]:
            raise RuntimeError("detector failure")

    doc = FakePdfDocument(["John paid"])
    service = _service(detector=FailingDetector())

    with pytest.raises(RuntimeError, match="detector failure"):
        service.execute(doc, ["PERSON"], 0.35)

    assert doc.closed is True
