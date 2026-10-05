"""Tests for the Word (.docx) pseudonymization use case.

Framework-free: a fake :class:`WordDocument` and detector stand in for
python-docx and Presidio, so these tests run without the heavy language model.
"""

from __future__ import annotations

import pytest

from finance_redactor.application.redact_docx import RedactDocxService
from finance_redactor.config import DEFAULT_SETTINGS
from finance_redactor.domain.entities import DetectionSource, PiiDetection, Span
from finance_redactor.domain.pseudonyms import MasterEntry


class FakeWordDocument:
    """In-memory Word document double for testing RedactDocxService."""

    def __init__(self, blocks: list[str], links: int = 0) -> None:
        """Create a fake document with the given block (paragraph) texts."""
        self._blocks = blocks
        self._links = links
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

    def remove_external_links(self) -> int:
        """Report the canned link count."""
        return self._links

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

    def __init__(self) -> None:
        """Track how many times ``analyze`` was called."""
        self.call_count = 0

    def analyze(
        self, text: str, entities: list[str], threshold: float
    ) -> list[PiiDetection]:
        """Return a detection for each configured name found in ``text``."""
        self.call_count += 1
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
        fixed_masks=DEFAULT_SETTINGS.fixed_masks,
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


def test_custom_words_are_pseudonymized_and_survive_across_blocks() -> None:
    """An ad-hoc custom word gets a stable CUSTOM auto-id, consistent across blocks."""
    doc = FakeWordDocument(
        ["Project Nightingale kickoff", "Recap of Project Nightingale"]
    )
    service = RedactDocxService(
        detector=_NameDetector(),
        open_document=_document_factory,
        master_map={},
        auto_prefixes={"PERSON": "PSN", "CUSTOM": "CST"},
        fixed_masks=DEFAULT_SETTINGS.fixed_masks,
    )

    result = service.execute(
        doc, ["PERSON"], 0.35, custom_words=["Project Nightingale"]
    )

    assert result.entity_count == 2
    labels = {
        a.pseudonym
        for a in result.crosswalk
        if a.original_name == "Project Nightingale"
    }
    assert len(labels) == 1
    (label,) = labels
    assert label.startswith("CST-AUTO-")
    assert doc.replacements_by_block[0][0][1] == label
    assert doc.replacements_by_block[1][0][1] == label


def test_custom_words_do_not_override_an_overlapping_master_list_hit() -> None:
    """A custom word matching a curated master-list name keeps the curated id."""

    class _MasterListStyleDetector:
        """Fake detector that tags 'Jane Doe' as a master-list-sourced PERSON hit."""

        def analyze(
            self, text: str, entities: list[str], threshold: float
        ) -> list[PiiDetection]:
            if "PERSON" not in entities:
                return []
            idx = text.find("Jane Doe")
            if idx == -1:
                return []
            return [
                PiiDetection(
                    entity_type="PERSON",
                    span=Span(idx, idx + len("Jane Doe")),
                    score=0.9,
                    text="Jane Doe",
                    source=DetectionSource.MASTER_LIST,
                )
            ]

    doc = FakeWordDocument(["Paid to Jane Doe for services"])
    service = RedactDocxService(
        detector=_MasterListStyleDetector(),
        open_document=_document_factory,
        master_map={
            ("PERSON", "jane doe"): MasterEntry(pseudonym="STF-10010", category="Staff")
        },
        auto_prefixes={"PERSON": "PSN", "CUSTOM": "CST"},
        fixed_masks=DEFAULT_SETTINGS.fixed_masks,
    )

    result = service.execute(doc, ["PERSON"], 0.35, custom_words=["Jane Doe"])

    assert result.entity_count == 1
    assert result.crosswalk[0].pseudonym == "STF-10010"
    assert doc.replacements_by_block[0][0][1] == "STF-10010"


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


def test_excluded_term_is_not_replaced_in_any_block() -> None:
    """Unticking a false positive drops it from the Word output too."""
    doc = FakeWordDocument(["Total salaries paid", "John approved salaries"])

    result = _service().execute(
        doc,
        ["PERSON"],
        0.35,
        custom_words=["salaries"],
        exclude=frozenset({"salaries"}),
    )

    replaced = [
        text for block in doc.replacements_by_block.values() for _, text in block
    ]
    assert all("salaries" not in t for t in replaced)
    assert all(a.original_name != "salaries" for a in result.crosswalk)


def test_excluding_one_term_leaves_others_replaced_in_word() -> None:
    doc = FakeWordDocument(["John paid salaries"])

    result = _service().execute(
        doc,
        ["PERSON"],
        0.35,
        custom_words=["salaries"],
        exclude=frozenset({"salaries"}),
    )

    assert [a.original_name for a in result.crosswalk] == ["John"]


class _CardDetector:
    """Fake detector: flags a synthetic test card number as CREDIT_CARD."""

    card = "4111 1111 1111 1111"

    def analyze(
        self, text: str, entities: list[str], threshold: float
    ) -> list[PiiDetection]:
        """Return a CREDIT_CARD hit wherever the test card appears."""
        idx = text.find(self.card)
        if idx == -1:
            return []
        return [
            PiiDetection(
                entity_type="CREDIT_CARD",
                span=Span(idx, idx + len(self.card)),
                score=1.0,
                text=self.card,
                source=DetectionSource.PATTERN,
            )
        ]


def test_card_number_is_masked_and_never_reaches_the_crosswalk() -> None:
    doc = FakeWordDocument([f"Charged to card {_CardDetector.card} today"])
    service = RedactDocxService(
        detector=_CardDetector(),
        open_document=_document_factory,
        master_map={},
        auto_prefixes={"PERSON": "PSN"},
        fixed_masks=DEFAULT_SETTINGS.fixed_masks,
    )

    result = service.execute(doc, ["CREDIT_CARD"], 0.35)

    assert b"Charged to card [CARD] today" in result.data
    assert _CardDetector.card.encode() not in result.data
    assert result.crosswalk == []
    assert [f.entity_type for f in result.findings] == ["CREDIT_CARD"]


def test_link_targets_removed_on_open_are_reported() -> None:
    result = _service().execute(
        FakeWordDocument(["No name"], links=3), ["PERSON"], 0.35
    )

    assert result.removed_links == 3


# --- scan()/redact() split -------------------------------------------------


def test_scan_then_redact_matches_execute_for_a_custom_word() -> None:
    """scan()+redact() with no exclusions equals execute() for a custom word."""
    blocks = ["Total salaries paid", "No name here", "More salaries noted"]
    service = _service()

    expected = service.execute(
        FakeWordDocument(list(blocks)), ["PERSON"], 0.35, custom_words=["salaries"]
    )

    scan_result = service.scan(FakeWordDocument(list(blocks)), ["PERSON"], 0.35)
    actual = service.redact(FakeWordDocument(list(blocks)), scan_result, ["salaries"])

    assert actual.findings == expected.findings
    assert actual.crosswalk == expected.crosswalk
    assert actual.data == expected.data


def test_scan_then_redact_matches_execute_for_a_detector_sourced_match() -> None:
    """scan()+redact() with no exclusions equals execute() for a detector hit."""
    blocks = ["John paid invoice 1", "No name here", "John paid invoice 2"]
    service = _service()

    expected = service.execute(FakeWordDocument(list(blocks)), ["PERSON"], 0.35)

    scan_result = service.scan(FakeWordDocument(list(blocks)), ["PERSON"], 0.35)
    actual = service.redact(FakeWordDocument(list(blocks)), scan_result)

    assert actual.findings == expected.findings
    assert actual.crosswalk == expected.crosswalk
    assert actual.data == expected.data


def test_scan_then_redact_matches_execute_with_an_excluded_term() -> None:
    """scan()+redact() reproduces execute()'s exclude behavior exactly."""
    blocks = ["Total salaries paid to John"]
    service = _service()

    expected = service.execute(
        FakeWordDocument(list(blocks)),
        ["PERSON"],
        0.35,
        custom_words=["salaries"],
        exclude=frozenset({"salaries"}),
    )

    scan_result = service.scan(FakeWordDocument(list(blocks)), ["PERSON"], 0.35)
    actual = service.redact(
        FakeWordDocument(list(blocks)),
        scan_result,
        ["salaries"],
        exclude=frozenset({"salaries"}),
    )

    assert actual.findings == expected.findings
    assert actual.crosswalk == expected.crosswalk
    assert actual.data == expected.data


def test_redact_does_not_call_the_detector_again_across_exclude_changes() -> None:
    """The whole point of the split: a tick change never re-runs detection."""
    detector = _NameDetector()
    service = _service(detector)
    scan_result = service.scan(
        FakeWordDocument(["salaries, John, Mary"]), ["PERSON"], 0.35
    )
    calls_after_scan = detector.call_count
    assert calls_after_scan > 0

    service.redact(
        FakeWordDocument(["salaries, John, Mary"]),
        scan_result,
        ["salaries"],
        exclude=frozenset({"salaries"}),
    )
    assert detector.call_count == calls_after_scan

    service.redact(
        FakeWordDocument(["salaries, John, Mary"]),
        scan_result,
        ["salaries"],
        exclude=frozenset(),
    )
    assert detector.call_count == calls_after_scan


def test_scan_closes_the_document_and_does_not_redact() -> None:
    """scan() is read-only: it never removes links or replaces block text."""
    doc = FakeWordDocument(["John paid"])

    _service().scan(doc, ["PERSON"], 0.35)

    assert doc.closed is True
    assert doc.replacements_by_block == {}


def test_scan_records_every_block_including_blank_ones() -> None:
    """Block indices must stay aligned between scan() and redact()."""
    doc = FakeWordDocument(["", "John paid", "   "])

    scan_result = _service().scan(doc, ["PERSON"], 0.35)

    assert scan_result.block_count == 3
    assert scan_result.blocks[0].detections == []
    assert scan_result.blocks[2].detections == []


def test_scan_redact_excluded_term_is_not_replaced_in_any_block() -> None:
    """The exclude behavior still holds when driven through scan()+redact()."""
    doc = FakeWordDocument(["Total salaries paid", "John approved salaries"])
    service = _service()
    scan_result = service.scan(
        FakeWordDocument(["Total salaries paid", "John approved salaries"]),
        ["PERSON"],
        0.35,
    )

    result = service.redact(
        doc, scan_result, ["salaries"], exclude=frozenset({"salaries"})
    )

    replaced = [
        text for block in doc.replacements_by_block.values() for _, text in block
    ]
    assert all("salaries" not in t for t in replaced)
    assert all(a.original_name != "salaries" for a in result.crosswalk)


def test_scan_redact_skips_blank_blocks() -> None:
    """A blank block scanned as empty detections is also skipped by redact()."""
    doc = FakeWordDocument(["", "John paid", "   "])
    service = _service()
    scan_result = service.scan(
        FakeWordDocument(["", "John paid", "   "]), ["PERSON"], 0.35
    )

    result = service.redact(doc, scan_result)

    assert result.entity_count == 1
    assert 0 not in doc.replacements_by_block
    assert 2 not in doc.replacements_by_block
    assert 1 in doc.replacements_by_block


def test_scan_redact_excluding_one_term_leaves_others_replaced() -> None:
    doc = FakeWordDocument(["John paid salaries"])
    service = _service()
    scan_result = service.scan(
        FakeWordDocument(["John paid salaries"]), ["PERSON"], 0.35
    )

    result = service.redact(
        doc, scan_result, ["salaries"], exclude=frozenset({"salaries"})
    )

    assert [a.original_name for a in result.crosswalk] == ["John"]
