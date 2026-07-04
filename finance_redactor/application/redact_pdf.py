"""PDF pseudonymization use case.

Orchestrates the per-page pipeline: extract text (gateway) -> detect (detector)
-> dedupe overlaps (domain rule) -> resolve pseudonyms (domain) -> redact
(gateway). A single :class:`Pseudonymizer` spans the whole document so a name is
pseudonymized consistently across pages, and the accumulated crosswalk is
returned alongside the redacted bytes.

Behavior preserved from the original ``redact_pdf``: pages without text are
skipped; a finding is recorded for every kept detection even when its text
cannot be located on the page; redactions are applied per page.
"""

from __future__ import annotations

from collections.abc import Mapping

from finance_redactor.application.ports import PdfDocumentFactory, PiiDetector
from finance_redactor.application.results import PdfRedactionResult
from finance_redactor.domain.entities import Finding
from finance_redactor.domain.pseudonyms import MasterEntry, Pseudonymizer
from finance_redactor.domain.rules import dedupe_overlapping


class RedactPdfService:
    """Detects and pseudonymizes PII throughout a PDF document."""

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
        self, source: object, entities: list[str], threshold: float
    ) -> PdfRedactionResult:
        """Redact ``source`` and return new bytes, findings, page count, crosswalk."""
        document = self._open_document(source)
        pseudonymizer = Pseudonymizer(self._master_map, self._auto_prefixes)
        try:
            findings: list[Finding] = []
            for page_index in range(document.page_count):
                text = document.page_text(page_index)
                if not text.strip():
                    continue

                detections = self._detector.analyze(text, entities, threshold)
                if not detections:
                    continue

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

                document.redact_page(page_index, redactions)

            return PdfRedactionResult(
                data=document.to_bytes(),
                findings=findings,
                page_count=document.page_count,
                crosswalk=pseudonymizer.crosswalk(),
            )
        finally:
            document.close()
