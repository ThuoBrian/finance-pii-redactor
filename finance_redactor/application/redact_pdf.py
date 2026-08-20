"""PDF pseudonymization / blackout use case.

The PDF flow has no spaCy-model or master-list-based name/organization
detection - that stays a deliberate team decision (unreliable guessing on
scanned financial PDFs). It does, however, automatically catch email
addresses and websites (via the injected ``pattern_detector`` - see
``infrastructure/detection/pattern_detector.py``, which is deterministic
regex matching, not a statistical guess, and never loads a spaCy model) and,
by default, blacks out embedded images/logos. The words/phrases the user
types into the "words to redact" box (`pdf_view.py`'s Advanced settings) are
a *supplement* on top of that, for anything pattern-matching and image
blackout don't cover (names, project codenames, case numbers). Orchestrates
the per-page pipeline: extract text (gateway) -> normalize PDF artifacts ->
find emails/URLs (``pattern_detector``) and the user's words
(`domain/custom_words.find_custom_words`) -> dedupe overlaps (domain rule) ->
resolve pseudonyms (domain) -> redact (gateway). A single
:class:`Pseudonymizer` spans the whole document so the same word is
pseudonymized consistently across pages, and the accumulated crosswalk is
returned alongside the redacted bytes. A custom-word match is
``entity_type="CUSTOM"``/``DetectionSource.CUSTOM`` and always resolves to a
flagged ``CST-AUTO-<hash>`` id - there's no master list to resolve a curated
one against (``master_map`` is still accepted, and still wired through to
``Pseudonymizer``, purely so a real master list could be reinstated later by
passing one at the composition root - nothing here special-cases PDF).

PDF text extraction can introduce ligatures, hyphenation, and irregular
whitespace that break exact matching. The text is therefore normalized
before searching for emails/URLs/the user's words; spans are translated back
to the original extracted text so the gateway can search for them in the PDF.

In ``blackout`` mode, matched text is covered with a black box instead of
being replaced by a pseudonym. Image/logo blackout (when ``redact_images``
is set) applies in *either* style - it was previously gated to Blackout
style only, which was purely an application-layer restriction; the gateway
itself always hardcodes black fill for images regardless of style. The
crosswalk is still returned for text matches so reviewers can see what was
redacted.

Behavior preserved from the original ``redact_pdf``: pages without text are
skipped; a finding is recorded for every kept match even when its text
cannot be located on the page; redactions are applied per page.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import Enum

from finance_redactor.application.ports import PdfDocumentFactory, PiiDetector
from finance_redactor.application.results import PdfRedactionResult
from finance_redactor.domain.custom_words import find_custom_words
from finance_redactor.domain.entities import IMAGE_REDACTION_SENTINEL, Finding
from finance_redactor.domain.pseudonyms import MasterEntry, Pseudonymizer
from finance_redactor.domain.rules import dedupe_overlapping
from finance_redactor.infrastructure.detection.pdf_text_normalizer import (
    NormalizedText,
    normalize_pdf_text,
)

# Fixed, low threshold for the always-on email/URL pass - not user-tunable
# (there's no UI control for it, matching the "just works" ask). Presidio's
# own recognizers already validate matches (e.g. EmailRecognizer's TLD check)
# before assigning a score, so this only needs to be low enough to admit the
# lower-confidence URL patterns (e.g. schema-less matches score 0.5).
_PATTERN_THRESHOLD = 0.4
_PATTERN_ENTITIES = ["EMAIL_ADDRESS", "URL"]


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
        pattern_detector: PiiDetector,
        fuzzy_threshold: float = 0.84,
        custom_words_score: float = 1.0,
    ) -> None:
        """Wire a PDF-opening factory, the pseudonym vocabulary, and a detector.

        ``pattern_detector`` finds emails/URLs and is always supplied by the
        composition root (see ``infrastructure/detection/pattern_detector.py``) -
        this is a fixed, always-on capability, not optional or user-tunable.
        ``fuzzy_threshold`` should normally be ``Settings.fuzzy_match_threshold``,
        passed explicitly by the composition root; the default here only covers
        callers (e.g. tests) that don't care about the fuzzy-suggestion feature.
        ``custom_words_score`` should normally be ``Settings.custom_words_score``;
        it's the confidence recorded for every custom-word match (see
        ``execute``'s ``custom_words`` param).
        """
        self._open_document = open_document
        self._master_map = master_map
        self._auto_prefixes = auto_prefixes
        self._pattern_detector = pattern_detector
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

        Emails and URLs are always detected automatically (``pattern_detector``,
        no toggle). ``custom_words`` is an additional list of words/phrases to
        redact on every page - matched literally and case-insensitively (see
        ``domain/custom_words.find_custom_words``). An empty ``custom_words``
        list just means there's nothing extra to add on top of the automatic
        email/URL/image detection - this method runs cleanly either way.
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
                    [
                        *self._pattern_detector.analyze(
                            normalized.text, _PATTERN_ENTITIES, _PATTERN_THRESHOLD
                        ),
                        *find_custom_words(
                            normalized.text, custom_words, self._custom_words_score
                        ),
                    ]
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

                if redact_images and document.page_image_rects(page_index):
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
