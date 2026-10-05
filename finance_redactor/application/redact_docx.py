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

``execute`` runs the whole pipeline - including the detector call - every
time, which is wasteful when only ``exclude`` changed (unticking a false
positive in the review table). ``scan``/``redact`` split that in two, the
same way Excel's ``RedactExcelService`` and PDF's ``RedactPdfService`` already
are: ``scan`` opens the document once and runs the detector once per block,
returning a :class:`DocxScanResult`; ``redact`` takes that cached result plus
a fresh ``custom_words``/``exclude`` and rebuilds the output with no detector
call and no ``block_text`` call at all. ``execute`` is unchanged and kept for
callers that don't need the split.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from finance_redactor.application.ports import PiiDetector, WordDocumentFactory
from finance_redactor.application.results import DocxRedactionResult
from finance_redactor.domain.custom_words import find_custom_words
from finance_redactor.domain.entities import Finding, PiiDetection, Span
from finance_redactor.domain.pseudonyms import (
    MasterEntry,
    Pseudonymizer,
    normalize,
)
from finance_redactor.domain.rules import dedupe_overlapping


@dataclass(frozen=True)
class _DocxBlockScan:
    """One block's worth of detector output, cached between ``scan`` and ``redact``.

    ``detections`` is the detector's own output only - never includes custom
    words, which depend on the per-call ``custom_words`` list and so can't be
    cached across a tick change.
    """

    text: str
    detections: list[PiiDetection]


@dataclass(frozen=True)
class DocxScanResult:
    """A document's detector pass, cached so ``redact`` never re-detects.

    Internal cache between :meth:`RedactDocxService.scan` and
    :meth:`RedactDocxService.redact` - not a use-case output in its own right,
    so it lives here rather than in ``application/results.py``.
    """

    blocks: list[_DocxBlockScan]

    @property
    def block_count(self) -> int:
        """Number of blocks captured by the scan."""
        return len(self.blocks)


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
        *,
        fixed_masks: Mapping[str, str],
    ) -> None:
        """Wire the detector, a docx-opening factory, and pseudonym vocabulary.

        ``fuzzy_threshold`` should normally be ``Settings.fuzzy_match_threshold``,
        passed explicitly by the composition root; the default here only covers
        callers (e.g. tests) that don't care about the fuzzy-suggestion feature.
        ``custom_words_score`` should normally be ``Settings.custom_words_score``;
        it's the confidence recorded for an ad-hoc "words to redact" match (see
        ``execute``'s ``custom_words`` param). ``fixed_masks`` is
        ``Settings.fixed_masks``: bank/payment types get that mask and never
        reach the pseudonymizer, so the raw number stays out of the crosswalk.
        """
        self._detector = detector
        self._open_document = open_document
        self._master_map = master_map
        self._auto_prefixes = auto_prefixes
        self._fuzzy_threshold = fuzzy_threshold
        self._custom_words_score = custom_words_score
        self._fixed_masks = fixed_masks

    def execute(
        self,
        source: object,
        entities: list[str],
        threshold: float,
        *,
        custom_words: list[str] | None = None,
        exclude: frozenset[str] = frozenset(),
    ) -> DocxRedactionResult:
        """Pseudonymize ``source`` and return new bytes, findings, crosswalk.

        ``custom_words``, if given, is a list of ad-hoc words/phrases to
        redact in every block in addition to whatever ``entities`` detects -
        matched literally and case-insensitively (see
        ``domain/custom_words.find_custom_words``), even if not in the master
        list. Not curated, not saved anywhere: re-supplied by the caller on
        every run.

        ``exclude`` is a set of already-normalized terms (see
        ``domain/pseudonyms.normalize``) the operator ticked off in the review
        table as false positives. A matching detection is dropped before it
        reaches the pseudonymizer, so it is neither replaced in the output nor
        recorded in the crosswalk. Per-run only: nothing about it persists, and
        the caller re-supplies it on every call.
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
                replacements = self._block_replacements(
                    block_index=block_index,
                    detections=detections,
                    exclude=exclude,
                    pseudonymizer=pseudonymizer,
                    findings=findings,
                )
                if not replacements:
                    continue
                document.replace_block_text(block_index, replacements)

            removed_links = document.remove_external_links()
            return DocxRedactionResult(
                data=document.to_bytes(),
                findings=findings,
                block_count=document.block_count,
                crosswalk=pseudonymizer.crosswalk(),
                removed_links=removed_links,
            )
        finally:
            document.close()

    def scan(
        self, source: object, entities: list[str], threshold: float
    ) -> DocxScanResult:
        """Run the detector once per block and cache the result for ``redact``.

        Pure and read-only: no custom words, no dedupe, no ``exclude``, no
        replacements applied, and ``remove_external_links`` is never called.
        This is the expensive pass (the detector call is spaCy/Presidio under
        the hood) - the whole point of splitting it out is that the caller
        runs it exactly once per upload, then reuses the result across every
        tick change in the review table via :meth:`redact`.

        Every block is recorded, including blank ones (with an empty
        ``detections`` list), so block indices stay aligned between this
        result and ``redact``'s enumeration of it.
        """
        document = self._open_document(source)
        try:
            blocks: list[_DocxBlockScan] = []
            for block_index in range(document.block_count):
                text = document.block_text(block_index)
                detections = (
                    self._detector.analyze(text, entities, threshold)
                    if text.strip()
                    else []
                )
                blocks.append(_DocxBlockScan(text=text, detections=detections))
            return DocxScanResult(blocks=blocks)
        finally:
            document.close()

    def redact(
        self,
        source: object,
        scan_result: DocxScanResult,
        custom_words: list[str] | None = None,
        *,
        exclude: frozenset[str] = frozenset(),
    ) -> DocxRedactionResult:
        """Rebuild the pseudonymized document from an existing :class:`DocxScanResult`.

        ``source`` must be freshly opened (the caller resets its read
        position before calling this) - a new document build needs a fresh
        set of runs to splice into, and a fresh :class:`Pseudonymizer` so this
        call's crosswalk starts clean. Everything but ``custom_words`` and
        ``exclude`` comes from ``scan_result``: this method calls
        ``document.block_text()`` and ``self._detector.analyze()`` zero
        times, which is what makes re-applying a changed ``exclude`` set
        cheap.
        """
        document = self._open_document(source)
        pseudonymizer = Pseudonymizer(
            self._master_map, self._auto_prefixes, fuzzy_threshold=self._fuzzy_threshold
        )
        try:
            findings: list[Finding] = []
            for block_index, block in enumerate(scan_result.blocks):
                if not block.text.strip():
                    continue

                detections = (
                    [
                        *block.detections,
                        *find_custom_words(
                            block.text, custom_words, self._custom_words_score
                        ),
                    ]
                    if custom_words
                    else list(block.detections)
                )
                replacements = self._block_replacements(
                    block_index=block_index,
                    detections=detections,
                    exclude=exclude,
                    pseudonymizer=pseudonymizer,
                    findings=findings,
                )
                if not replacements:
                    continue
                document.replace_block_text(block_index, replacements)

            removed_links = document.remove_external_links()
            return DocxRedactionResult(
                data=document.to_bytes(),
                findings=findings,
                block_count=document.block_count,
                crosswalk=pseudonymizer.crosswalk(),
                removed_links=removed_links,
            )
        finally:
            document.close()

    def _block_replacements(
        self,
        *,
        block_index: int,
        detections: list[PiiDetection],
        exclude: frozenset[str],
        pseudonymizer: Pseudonymizer,
        findings: list[Finding],
    ) -> list[tuple[Span, str]]:
        """Dedupe/exclude/assign/build the replacement list for one block.

        Shared by ``execute`` and ``redact`` - identical logic, factored out
        once both methods needed it. Appends to ``findings`` in place (one
        list spans the whole document in both callers) and returns this
        block's ``(span, pseudonym)`` replacement list.
        """
        kept = [
            d
            for d in dedupe_overlapping(detections)
            if normalize(d.text) not in exclude
        ]
        replacements: list[tuple[Span, str]] = []
        for detection in kept:
            pseudonym = (
                self._fixed_masks.get(detection.entity_type)
                or pseudonymizer.assign(detection.entity_type, detection.text).pseudonym
            )
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
        return replacements
