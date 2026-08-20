"""PDF pseudonymization / blackout use case.

The PDF flow has no automatic detection at all - no spaCy model, no
master-list matching. It redacts *only* the words/phrases the user typed
into the "words to redact" box (`pdf_view.py`'s Advanced settings, the sole
input - the UI stops with a message if it's empty). Orchestrates the
per-page pipeline: extract text (gateway) -> normalize PDF artifacts ->
find the user's words (`domain/custom_words.find_custom_words`) -> dedupe
overlaps (domain rule) -> resolve pseudonyms (domain) -> redact (gateway). A
single :class:`Pseudonymizer` spans the whole document so the same word is
pseudonymized consistently across pages, and the accumulated crosswalk is
returned alongside the redacted bytes. Every match is
``entity_type="CUSTOM"``/``DetectionSource.CUSTOM`` and always resolves to a
flagged ``CST-AUTO-<hash>`` id - there's no master list to resolve a curated
one against (``master_map`` is still accepted, and still wired through to
``Pseudonymizer``, purely so a real master list could be reinstated later by
passing one at the composition root - nothing here special-cases PDF).

PDF text extraction can introduce ligatures, hyphenation, and irregular
whitespace that break exact matching. The text is therefore normalized
before searching for the user's words; spans are translated back to the
original extracted text so the gateway can search for them in the PDF.

In ``blackout`` mode, matched text is covered with a black box instead of
being replaced by a pseudonym, and images are always blacked out. The
crosswalk is still returned for text matches so reviewers can see what was
redacted.

Behavior preserved from the original ``redact_pdf``: pages without text are
skipped; a finding is recorded for every kept match even when its text
cannot be located on the page; redactions are applied per page.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum

from finance_redactor.application.ports import PdfDocumentFactory
from finance_redactor.application.results import PdfRedactionResult
from finance_redactor.domain.custom_words import find_custom_words
from finance_redactor.domain.entities import IMAGE_REDACTION_SENTINEL, Finding
from finance_redactor.domain.pseudonyms import MasterEntry, Pseudonymizer
from finance_redactor.domain.rules import dedupe_overlapping
from finance_redactor.infrastructure.detection.pdf_text_normalizer import (
    NormalizedText,
    normalize_pdf_text,
)


class RedactionStyle(str, Enum):
    """How matched text should be redacted in a PDF."""

    PSEUDONYMIZE = "pseudonymize"
    BLACKOUT = "blackout"


class RedactPdfService:
    """Pseudonymizes (or blacks out) only the user-supplied words in a PDF."""

    def __init__(
        self,
        open_document: PdfDocumentFactory,
        master_map: Mapping[tuple[str, str], MasterEntry],
        auto_prefixes: Mapping[str, str],
        fuzzy_threshold: float = 0.84,
        custom_words_score: float = 1.0,
    ) -> None:
        """Wire a PDF-opening factory and the pseudonym vocabulary.

        ``fuzzy_threshold`` should normally be ``Settings.fuzzy_match_threshold``,
        passed explicitly by the composition root; the default here only covers
        callers (e.g. tests) that don't care about the fuzzy-suggestion feature.
        ``custom_words_score`` should normally be ``Settings.custom_words_score``;
        it's the confidence recorded for every match (see ``execute``'s
        ``custom_words`` param - the only source of matches in this flow).
        """
        self._open_document = open_document
        self._master_map = master_map
        self._auto_prefixes = auto_prefixes
        self._fuzzy_threshold = fuzzy_threshold
        self._custom_words_score = custom_words_score

    def execute(
        self,
        source: object,
        custom_words: list[str],
        *,
        style: RedactionStyle = RedactionStyle.PSEUDONYMIZE,
        redact_images: bool = False,
    ) -> PdfRedactionResult:
        """Redact ``source`` and return new bytes, findings, page count, crosswalk.

        ``custom_words`` is the list of words/phrases to redact on every
        page - matched literally and case-insensitively (see
        ``domain/custom_words.find_custom_words``). This is the *only* thing
        redacted in this flow; an empty list means nothing is found on any
        page (the presentation layer is expected to stop before calling this
        with an empty list, but this method itself still runs cleanly either
        way).
        """
        document = self._open_document(source)
        pseudonymizer = Pseudonymizer(
            self._master_map, self._auto_prefixes, fuzzy_threshold=self._fuzzy_threshold
        )
        try:
            findings: list[Finding] = []
            for page_index in range(document.page_count):
                raw_text = document.page_text(page_index)
                has_text = bool(raw_text.strip())
                normalized = (
                    normalize_pdf_text(raw_text)
                    if has_text
                    else NormalizedText("", raw_text, ())
                )
                detections = (
                    find_custom_words(
                        normalized.text, custom_words, self._custom_words_score
                    )
                    if has_text
                    else []
                )

                kept = dedupe_overlapping(detections)
                redactions: list[tuple[str | list[str], str]] = []
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
                    raw_span = normalized.to_raw_span(detection.span)
                    raw_substring = raw_text[raw_span.start : raw_span.end]
                    # Pass the normalized match text first, with the original
                    # extracted substring as a fallback so PyMuPDF can find it
                    # even when the page stores it with ligatures or hyphens.
                    candidates: list[str] = [detection.text]
                    if raw_substring != detection.text:
                        candidates.append(raw_substring)
                    redactions.append((candidates, pseudonym))

                if (
                    style == RedactionStyle.BLACKOUT
                    and redact_images
                    and document.page_image_rects(page_index)
                ):
                    redactions.append((IMAGE_REDACTION_SENTINEL, ""))

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
