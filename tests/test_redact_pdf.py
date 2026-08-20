"""Tests for the PDF pseudonymization / blackout use case.

Framework-free: a fake :class:`PdfDocument` stands in for PyMuPDF and a fake
:class:`PiiDetector` stands in for the real spaCy-free ``PatternDetector``,
so these tests run without any heavy dependency. Most tests drive the
service purely through the ``custom_words`` list (the fake pattern detector
finds nothing by default); a few specifically exercise the pattern-detector
merge.
"""

from __future__ import annotations

import pytest

from finance_redactor.application.redact_pdf import RedactionStyle, RedactPdfService
from finance_redactor.domain.entities import DetectionSource, PiiDetection, Span


class FakePdfDocument:
    """In-memory PDF double for testing RedactPdfService."""

    def __init__(
        self, pages: list[str], image_rects: dict[int, list[tuple]] | None = None
    ) -> None:
        """Create a fake document with the given page texts and image rectangles."""
        self._pages = pages
        self._image_rects = image_rects or {}
        self.redactions_by_page: dict[int, list[tuple[str, str]]] = {}
        self.blackout_by_page: dict[int, bool] = {}
        self.closed = False

    @property
    def page_count(self) -> int:
        """Return the number of pages."""
        return len(self._pages)

    def page_text(self, page_index: int) -> str:
        """Return the text of the requested page."""
        return self._pages[page_index]

    def page_image_rects(
        self, page_index: int
    ) -> list[tuple[float, float, float, float]]:
        """Return image rectangles recorded for this page."""
        return [
            tuple(float(c) for c in r) for r in self._image_rects.get(page_index, [])
        ]

    def to_bytes(self) -> bytes:
        """Render the document to bytes (here, the joined page texts)."""
        return b"\n---PAGE---\n".join(p.encode("utf-8") for p in self._pages)

    def close(self) -> None:
        """Mark the document as closed."""
        self.closed = True

    def redact_page(
        self,
        page_index: int,
        replacements: list[tuple[str | list[str], str]],
        blackout: bool = False,
    ) -> list[object]:
        """Apply replacements for this test document.

        Each candidate list is tried in order; the first candidate found in the
        page text is replaced and recorded. Unknown candidate lists are ignored.
        The ``__IMAGE__`` sentinel is treated as a request to redact images.
        """
        rects: list[object] = []
        self.blackout_by_page[page_index] = blackout
        image_sentinel = "__IMAGE__"
        for candidates, replacement in replacements:
            if isinstance(candidates, str):
                candidates = [candidates]
            if image_sentinel in candidates:
                for _ in self._image_rects.get(page_index, []):
                    self.redactions_by_page.setdefault(page_index, []).append(
                        (image_sentinel, "")
                    )
                    rects.append((image_sentinel, ""))
                continue
            page_text = self._pages[page_index]
            for candidate in candidates:
                if candidate in page_text:
                    self._pages[page_index] = page_text.replace(
                        candidate, replacement, 1
                    )
                    self.redactions_by_page.setdefault(page_index, []).append(
                        (candidate, replacement)
                    )
                    rects.append((candidate, replacement))
                    break
        return rects


class FakePatternDetector:
    """A ``PiiDetector`` double that returns a fixed, canned list of matches.

    Real production code always hits the real ``PatternDetector`` for
    emails/URLs; tests that don't care about that merge use the default
    (finds nothing), keeping their assertions focused on custom words alone.
    """

    def __init__(self, detections: list[PiiDetection] | None = None) -> None:
        """Store the canned detections to return from every ``analyze`` call."""
        self._detections = detections or []

    def analyze(
        self, text: str, entities: list[str], threshold: float
    ) -> list[PiiDetection]:
        """Return the canned detections, ignoring the actual text/args."""
        return list(self._detections)


def _document_factory(source: object) -> FakePdfDocument:
    """Return the FakePdfDocument passed as the source."""
    assert isinstance(source, FakePdfDocument)
    return source


def _service(pattern_detector: FakePatternDetector | None = None) -> RedactPdfService:
    return RedactPdfService(
        open_document=_document_factory,
        master_map={},
        auto_prefixes={"CUSTOM": "CST", "EMAIL_ADDRESS": "EML", "URL": "URL"},
        pattern_detector=pattern_detector or FakePatternDetector(),
    )


def test_execute_returns_redacted_document_and_findings() -> None:
    """The service redacts every page, records findings, and returns bytes."""
    doc = FakePdfDocument(
        ["John paid invoice 1", "No name here", "John paid invoice 2"]
    )
    result = _service().execute(doc, ["John"])

    assert result.page_count == 3
    assert result.entity_count == 2
    assert result.data == doc.to_bytes()
    assert doc.closed is True
    assert result.findings[0].page == 0
    assert result.findings[0].detected_text == "John"
    assert result.findings[1].page == 2


def test_pseudonym_is_consistent_across_pages() -> None:
    """The same word on different pages maps to the same pseudonym."""
    doc = FakePdfDocument(["John paid", "John approved"])
    _service().execute(doc, ["John"])

    page_0_label = doc.redactions_by_page[0][0][1]
    page_1_label = doc.redactions_by_page[1][0][1]
    assert page_0_label == page_1_label
    assert page_0_label.startswith("CST-AUTO-")


def test_empty_pages_are_skipped() -> None:
    """Pages with no text do not produce findings or redactions."""
    doc = FakePdfDocument(["", "John paid", "   "])
    result = _service().execute(doc, ["John"])

    assert result.entity_count == 1
    assert 0 not in doc.redactions_by_page
    assert 2 not in doc.redactions_by_page
    assert 1 in doc.redactions_by_page


def test_crosswalk_lists_distinct_assignments() -> None:
    """The crosswalk contains each distinct word->pseudonym assignment once."""
    doc = FakePdfDocument(["John paid", "John approved", "Mary paid"])
    result = _service().execute(doc, ["John", "Mary"])

    assert len(result.crosswalk) == 2
    names = {a.original_name for a in result.crosswalk}
    assert names == {"John", "Mary"}
    assert all(a.auto for a in result.crosswalk)


def test_overlapping_custom_words_are_deduped_leftmost_longest() -> None:
    """Two overlapping custom words resolve via leftmost/longest, as before."""
    doc = FakePdfDocument(["Jane Doe Enterprises invoice"])
    result = _service().execute(doc, ["Jane Doe Enterprises", "Doe Enterprises"])

    assert result.entity_count == 1
    assert result.findings[0].detected_text == "Jane Doe Enterprises"


def test_custom_word_with_pdf_artifacts_is_detected_after_normalization() -> None:
    """Ligatures and line-break hyphens are normalized before matching."""
    raw = "Acme Sup-\nplies invoice"
    doc = FakePdfDocument([raw])
    result = _service().execute(doc, ["Acme Supplies"])

    assert result.entity_count == 1
    assert result.findings[0].detected_text == "Acme Supplies"
    # The page text was updated using whichever candidate the gateway could find.
    pseudonym = result.crosswalk[0].pseudonym
    assert pseudonym in doc._pages[0]


def test_document_is_closed_even_if_page_text_raises() -> None:
    """The underlying document is closed if the pipeline raises."""

    class FailingDocument(FakePdfDocument):
        def page_text(self, page_index: int) -> str:
            raise RuntimeError("page read failure")

    doc = FailingDocument(["John paid"])

    with pytest.raises(RuntimeError, match="page read failure"):
        _service().execute(doc, ["John"])

    assert doc.closed is True


def test_blackout_mode_passes_blackout_flag() -> None:
    """Blackout mode instructs the gateway to cover text with black boxes."""
    doc = FakePdfDocument(["John paid"])
    _service().execute(
        doc, ["John"], style=RedactionStyle.BLACKOUT, redact_images=False
    )

    assert doc.blackout_by_page[0] is True
    # Text redaction still records the matched text and assigned pseudonym.
    assert doc.redactions_by_page[0][0][0] == "John"
    assert doc.redactions_by_page[0][0][1].startswith("CST-AUTO-")


def test_blackout_mode_can_redact_images() -> None:
    """Blackout mode adds an image sentinel redaction when images are present.

    Independent of text matching - an empty word list still blacks out images.
    """
    doc = FakePdfDocument(
        ["John paid"],
        image_rects={0: [(10.0, 10.0, 50.0, 50.0)]},
    )
    _service().execute(doc, [], style=RedactionStyle.BLACKOUT, redact_images=True)

    sentinels = [r for r, _ in doc.redactions_by_page[0] if r == "__IMAGE__"]
    assert sentinels == ["__IMAGE__"]


def test_pseudonymize_mode_can_redact_images_too() -> None:
    """Image blackout is independent of redaction style, not blackout-only.

    Previously gated to Blackout style only; now applies in Pseudonymize
    style as well (the gateway already hardcodes black fill for images
    regardless of style - only the application-layer gate changed here).
    Text is still pseudonymized normally, not blacked out.
    """
    doc = FakePdfDocument(
        ["John paid"],
        image_rects={0: [(10.0, 10.0, 50.0, 50.0)]},
    )
    _service().execute(
        doc, ["John"], style=RedactionStyle.PSEUDONYMIZE, redact_images=True
    )

    sentinels = [r for r, _ in doc.redactions_by_page[0] if r == "__IMAGE__"]
    assert sentinels == ["__IMAGE__"]
    assert doc.blackout_by_page[0] is False


def test_pattern_detector_matches_are_merged_with_custom_words() -> None:
    """Emails/URLs from the pattern detector are redacted alongside custom words.

    Both sources contribute detections on the same page; each keeps its own
    ``DetectionSource`` and resolves to its own pseudonym prefix.
    """
    text = "Contact jane@example.com or ask John for details"
    email_span = Span(
        text.index("jane@example.com"),
        text.index("jane@example.com") + len("jane@example.com"),
    )
    detector = FakePatternDetector(
        [
            PiiDetection(
                entity_type="EMAIL_ADDRESS",
                span=email_span,
                score=1.0,
                text="jane@example.com",
                source=DetectionSource.PATTERN,
            )
        ]
    )
    doc = FakePdfDocument([text])
    result = _service(detector).execute(doc, ["John"])

    assert result.entity_count == 2
    sources = {f.detected_text: f.source for f in result.findings}
    assert sources["jane@example.com"] == DetectionSource.PATTERN
    assert sources["John"] == DetectionSource.CUSTOM
    pseudonyms = {a.original_name: a.pseudonym for a in result.crosswalk}
    assert pseudonyms["jane@example.com"].startswith("EML-AUTO-")
    assert pseudonyms["John"].startswith("CST-AUTO-")
