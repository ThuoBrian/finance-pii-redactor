"""PDF pseudonymization / blackout use case.

Orchestrates the per-page pipeline: extract text (gateway) -> detect (detector)
-> dedupe overlaps (domain rule) -> resolve pseudonyms (domain) -> redact
(gateway). A single :class:`Pseudonymizer` spans the whole document so a name is
pseudonymized consistently across pages, and the accumulated crosswalk is
returned alongside the redacted bytes.

In ``blackout`` mode, detected text is covered with a black box instead of being
replaced by a pseudonym, and images are always blacked out. The crosswalk is
still returned for text detections so reviewers can see what was redacted.

Behavior preserved from the original ``redact_pdf``: pages without text are
skipped; a finding is recorded for every kept detection even when its text
cannot be located on the page; redactions are applied per page.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum

from finance_redactor.application.ports import PdfDocumentFactory, PiiDetector
from finance_redactor.application.results import PdfRedactionResult
from finance_redactor.domain.entities import Finding
from finance_redactor.domain.pseudonyms import MasterEntry, Pseudonymizer
from finance_redactor.domain.rules import dedupe_overlapping


class RedactionStyle(str, Enum):
    """How detected text should be redacted in a PDF."""

    PSEUDONYMIZE = "pseudonymize"
    BLACKOUT = "blackout"


class RedactPdfService:
    """Detects and pseudonymizes (or blacks out) PII throughout a PDF document."""

    _IMAGE_SENTINEL = "__IMAGE__"

    def __init__(
        self,
        detector: PiiDetector,
        open_document: PdfDocumentFactory,
        master_map: Mapping[tuple[str, str], MasterEntry],
        auto_prefixes: Mapping[str, str],
    ) -> None:
        """Wire the detector, a PDF-opening factory, and pseudonym vocabulary."""
        self._detector = detector
        self._open_document = open_document
        self._master_map = master_map
        self._auto_prefixes = auto_prefixes

    def execute(
        self,
        source: object,
        entities: list[str],
        threshold: float,
        *,
        style: RedactionStyle = RedactionStyle.PSEUDONYMIZE,
        redact_images: bool = False,
    ) -> PdfRedactionResult:
        """Redact ``source`` and return new bytes, findings, page count, crosswalk."""
        document = self._open_document(source)
        pseudonymizer = Pseudonymizer(self._master_map, self._auto_prefixes)
        try:
            findings: list[Finding] = []
            for page_index in range(document.page_count):
                text = document.page_text(page_index)
                has_text = bool(text.strip())
                detections = (
                    self._detector.analyze(text, entities, threshold)
                    if has_text
                    else []
                )

                kept = dedupe_overlapping(detections)
                redactions: list[tuple[str, str]] = []
                for detection in kept:
                    pseudonym = pseudonymizer.assign(
                        detection.entity_type, detection.text
                    ).pseudonym
                    findings.append(
                        Finding(
                            page=page_index,
                            detected_text=detection.text,
                            entity_type=detection.entity_type,
                            score=detection.score,
                            source=detection.source,
                        )
                    )
                    redactions.append((detection.text, pseudonym))

                if (
                    style == RedactionStyle.BLACKOUT
                    and redact_images
                    and document.page_image_rects(page_index)
                ):
                    redactions.append((self._IMAGE_SENTINEL, ""))

                if redactions:
                    document.redact_page(
                        page_index,
                        redactions,
                        blackout=(style == RedactionStyle.BLACKOUT),
                    )

            return PdfRedactionResult(
                data=document.to_bytes(),
                findings=findings,
                page_count=document.page_count,
                crosswalk=pseudonymizer.crosswalk(),
            )
        finally:
            document.close()
