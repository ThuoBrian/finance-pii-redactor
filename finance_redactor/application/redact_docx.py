"""Word (.docx) pseudonymization use case.

Orchestrates the per-block pipeline: extract flattened paragraph text (gateway)
-> detect (detector) -> dedupe overlaps (domain rule) -> resolve pseudonyms
(domain) -> write the replacements back (gateway). A single
:class:`Pseudonymizer` spans the whole document so a name is pseudonymized
consistently across paragraphs, table cells, and headers/footers, and the
accumulated crosswalk is returned alongside the pseudonymized bytes.

Unlike the PDF flow, no text normalization is needed - .docx text has no
ligature/hyphenation artifacts to undo - and there is no blackout mode:
Word text stays editable, replaced in place with pseudonyms (matching the
Excel flow's approach), and images are untouched.
"""

from __future__ import annotations

from collections.abc import Mapping

from finance_redactor.application.ports import PiiDetector, WordDocumentFactory
from finance_redactor.application.results import DocxRedactionResult
from finance_redactor.domain.custom_words import find_custom_words
from finance_redactor.domain.entities import Finding
from finance_redactor.domain.pseudonyms import MasterEntry, Pseudonymizer
from finance_redactor.domain.rules import dedupe_overlapping


class RedactDocxService:
    """Detects and pseudonymizes PII throughout a Word document."""

    def __init__(
        self,
        detector: PiiDetector,
        open_document: WordDocumentFactory,
        master_map: Mapping[tuple[str, str], MasterEntry],
        auto_prefixes: Mapping[str, str],
        fuzzy_threshold: float = 0.84,
        custom_words_score: float = 1.0,
    ) -> None:
        """Wire the detector, a docx-opening factory, and pseudonym vocabulary.

        ``fuzzy_threshold`` should normally be ``Settings.fuzzy_match_threshold``,
        passed explicitly by the composition root; the default here only covers
        callers (e.g. tests) that don't care about the fuzzy-suggestion feature.
        ``custom_words_score`` should normally be ``Settings.custom_words_score``;
        it's the confidence recorded for an ad-hoc "words to redact" match (see
        ``execute``'s ``custom_words`` param).
        """
        self._detector = detector
        self._open_document = open_document
        self._master_map = master_map
        self._auto_prefixes = auto_prefixes
        self._fuzzy_threshold = fuzzy_threshold
        self._custom_words_score = custom_words_score

    def execute(
        self,
        source: object,
        entities: list[str],
        threshold: float,
        *,
        custom_words: list[str] | None = None,
    ) -> DocxRedactionResult:
        """Pseudonymize ``source`` and return new bytes, findings, crosswalk.

        ``custom_words``, if given, is a list of ad-hoc words/phrases to
        redact in every block in addition to whatever ``entities`` detects -
        matched literally and case-insensitively (see
        ``domain/custom_words.find_custom_words``), even if not in the master
        list. Not curated, not saved anywhere: re-supplied by the caller on
        every run.
        """
        document = self._open_document(source)
        pseudonymizer = Pseudonymizer(
            self._master_map, self._auto_prefixes, fuzzy_threshold=self._fuzzy_threshold
        )
        try:
            findings: list[Finding] = []
            for block_index in range(document.block_count):
                text = document.block_text(block_index)
                if not text.strip():
                    continue

                detections = self._detector.analyze(text, entities, threshold)
                if custom_words:
                    detections = detections + find_custom_words(
                        text, custom_words, self._custom_words_score
                    )
                kept = dedupe_overlapping(detections)
                if not kept:
                    continue

                replacements = []
                for detection in kept:
                    pseudonym = pseudonymizer.assign(
                        detection.entity_type, detection.text
                    ).pseudonym
                    findings.append(
                        Finding(
                            page=block_index,
                            detected_text=detection.text,
                            entity_type=detection.entity_type,
                            score=detection.score,
                            source=detection.source,
                        )
                    )
                    replacements.append((detection.span, pseudonym))
                document.replace_block_text(block_index, replacements)

            return DocxRedactionResult(
                data=document.to_bytes(),
                findings=findings,
                block_count=document.block_count,
                crosswalk=pseudonymizer.crosswalk(),
            )
        finally:
            document.close()
