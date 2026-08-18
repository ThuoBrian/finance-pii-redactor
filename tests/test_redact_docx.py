"""Tests for the Word (.docx) pseudonymization use case.

Framework-free: a fake :class:`WordDocument` and detector stand in for
python-docx and Presidio, so these tests run without the heavy language model.
"""

from __future__ import annotations

import pytest

from finance_redactor.application.redact_docx import RedactDocxService
from finance_redactor.domain.entities import DetectionSource, PiiDetection, Span


class FakeWordDocument:
    """In-memory Word document double for testing RedactDocxService."""

    def __init__(self, blocks: list[str]) -> None:
        """Create a fake document with the given block (paragraph) texts."""
        self._blocks = blocks
        self.replacements_by_block: dict[int, list[tuple[Span, str]]] = {}
        self.closed = False

    @property
    def block_count(self) -> int:
        """Return the number of blocks."""
        return len(self._blocks)

    def block_text(self, block_index: int) -> str:
        """Return the text of the requested block."""
        return self._blocks[block_index]

    def replace_block_text(
        self, block_index: int, replacements: list[tuple[Span, str]]
    ) -> None:
        """Apply replacements right-to-left, recording what was requested."""
        self.replacements_by_block[block_index] = replacements
        text = self._blocks[block_index]
        for span, pseudonym in sorted(
            replacements, key=lambda item: item[0].start, reverse=True
        ):
            text = text[: span.start] + pseudonym + text[span.end :]
        self._blocks[block_index] = text

    def to_bytes(self) -> bytes:
        """Render the document to bytes (here, the joined block texts)."""
        return b"\n---BLOCK---\n".join(b.encode("utf-8") for b in self._blocks)

    def close(self) -> None:
        """Mark the document as closed."""
        self.closed = True


def _document_factory(source: object) -> FakeWordDocument:
    """Return the FakeWordDocument passed as the source."""
    assert isinstance(source, FakeWordDocument)
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


def _service(detector: _NameDetector | None = None) -> RedactDocxService:
    return RedactDocxService(
        detector=detector or _NameDetector(),
        open_document=_document_factory,
        master_map={},
        auto_prefixes={"PERSON": "PSN"},
    )


def test_execute_returns_pseudonymized_document_and_findings() -> None:
    """The service pseudonymizes every block and records findings."""
    doc = FakeWordDocument(
        ["John paid invoice 1", "No name here", "John paid invoice 2"]
    )
    result = _service().execute(doc, ["PERSON"], 0.35)

    assert result.block_count == 3
    assert result.entity_count == 2
    assert result.data == doc.to_bytes()
    assert doc.closed is True
    assert result.findings[0].page == 0
    assert result.findings[0].detected_text == "John"
    assert result.findings[1].page == 2


def test_pseudonym_is_consistent_across_blocks() -> None:
    """The same name in different blocks maps to the same pseudonym."""
    doc = FakeWordDocument(["John paid", "John approved"])
    _service().execute(doc, ["PERSON"], 0.35)

    block_0_label = doc.replacements_by_block[0][0][1]
    block_1_label = doc.replacements_by_block[1][0][1]
    assert block_0_label == block_1_label
    assert block_0_label.startswith("PSN-AUTO-")


def test_blank_blocks_are_skipped() -> None:
    """Blocks with no text do not produce findings or replacements."""
    doc = FakeWordDocument(["", "John paid", "   "])
    result = _service().execute(doc, ["PERSON"], 0.35)

    assert result.entity_count == 1
    assert 0 not in doc.replacements_by_block
    assert 2 not in doc.replacements_by_block
    assert 1 in doc.replacements_by_block


def test_crosswalk_lists_distinct_assignments() -> None:
    """The crosswalk contains each distinct name->pseudonym assignment once."""
    doc = FakeWordDocument(["John paid", "John approved", "Mary paid"])
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

    doc = FakeWordDocument(["John paid"])
    service = _service(detector=FailingDetector())

    with pytest.raises(RuntimeError, match="detector failure"):
        service.execute(doc, ["PERSON"], 0.35)

    assert doc.closed is True
