"""PDF pseudonymization / blackout use case.

The injected ``detector`` is the same spaCy-backed engine Excel and Word use,
so the PDF flow finds emails, websites, bank/payment details and addresses by
pattern, curated master-list names by exact match, and names or organizations
*not* on the master list by spaCy NER. An unlisted name gets a flagged
``AUTO-`` placeholder in the mapping, never the name itself. The user's
"words to redact" box still covers codenames, case numbers and anything the
model misses. Embedded images/logos are blacked out by default, and external
link targets (URLs, files, other documents) are removed from every page.

PDF originally ran no model at all: spaCy was judged too unreliable on
scanned financial PDFs. A scanned page has no text layer for the model to
misread, though, and leaving unlisted names in place leaked them. Model
false positives are unticked in the review table like any other.

Orchestrates the per-page pipeline: extract text (gateway) -> normalize PDF
artifacts -> detect (``detector``) and find the user's words
(`domain/custom_words.find_custom_words`) -> dedupe overlaps (domain rule) ->
resolve pseudonyms (domain) -> redact (gateway). A single
:class:`Pseudonymizer` spans the whole document so the same word gets the
same label across pages, and the accumulated crosswalk is returned alongside
the redacted bytes.

What gets written into the PDF is a **document-local label** (``[001]``), not
the pseudonym. The pseudonym embeds the master-list ``Internal ID``, so
stamping it into the document hands a reader the join key, so anyone
holding the master list can re-identify the file with no mapping at all. The
label means nothing outside this one document; the separately downloaded
mapping carries ``label -> Internal ID`` (and no names), and the master list
turns that ID into a name. Two hops, two sets of hands. Excel and Word still
write pseudonyms directly - this scheme is PDF-only for now.

A custom-word match is ``entity_type="CUSTOM"``/``DetectionSource.CUSTOM``.
The master map is keyed ``(PERSON|ORGANIZATION, name)``, so such a match
cannot resolve on an exact key; ``Pseudonymizer`` resolves it by name alone
instead (see its ``_resolve_by_name``), which is how a typed word carries
a curated ``Internal ID`` into the mapping. A word that isn't on the list, or
one that matches two curated rows disagreeing on the ID, is still redacted
but flagged with no ``Internal ID``.

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

import re
from collections.abc import Mapping
from enum import Enum

from finance_redactor.application.ports import PdfDocumentFactory, PiiDetector
from finance_redactor.application.results import PdfRedactionResult
from finance_redactor.domain.custom_words import find_custom_words
from finance_redactor.domain.entities import IMAGE_REDACTION_SENTINEL, Finding
from finance_redactor.domain.pdf_text_normalizer import (
    NormalizedText,
    normalize_pdf_text,
)
from finance_redactor.domain.pseudonyms import (
    MasterEntry,
    Pseudonymizer,
    normalize,
)
from finance_redactor.domain.rules import dedupe_overlapping

# Fixed threshold - not user-tunable (PDF has no threshold widget, matching
# the "just works" ask). Low enough to admit schema-less URLs (score 0.5) and
# spaCy names (0.85); Presidio's recognizers validate matches before scoring.
_THRESHOLD = 0.4
_ENTITIES = ["EMAIL_ADDRESS", "URL", "PERSON", "ORGANIZATION"]

# Bracketed numbers already present in the source, which look like the
# ``[001]`` labels this flow writes. Counted, reported, and otherwise left
# alone - the label format is fixed (see domain/pseudonyms.format_label).
_BRACKETED_NUMBER = re.compile(r"\[\d{1,4}\]")


class RedactionStyle(str, Enum):
    """How matched text should be redacted in a PDF."""

    PSEUDONYMIZE = "pseudonymize"
    BLACKOUT = "blackout"


class RedactPdfService:
    """Pseudonymizes (or blacks out) detected PII and the user's words in a PDF."""

    def __init__(
        self,
        open_document: PdfDocumentFactory,
        master_map: Mapping[tuple[str, str], MasterEntry],
        auto_prefixes: Mapping[str, str],
        detector: PiiDetector,
        fuzzy_threshold: float = 0.84,
        custom_words_score: float = 1.0,
        *,
        fixed_masks: Mapping[str, str],
    ) -> None:
        """Wire a PDF-opening factory, the pseudonym vocabulary, and a detector.

        ``detector`` is the composition root's spaCy-backed engine (see
        ``infrastructure/detection/presidio_detector.py``) - always on, not
        optional or user-tunable.
        ``fuzzy_threshold`` should normally be ``Settings.fuzzy_match_threshold``,
        passed explicitly by the composition root; the default here only covers
        callers (e.g. tests) that don't care about the fuzzy-suggestion feature.
        ``custom_words_score`` should normally be ``Settings.custom_words_score``;
        it's the confidence recorded for every custom-word match (see
        ``execute``'s ``custom_words`` param). ``fixed_masks`` is
        ``Settings.fixed_masks``: those bank/payment types are also requested
        from the detector, and are written as their mask with no label and no
        mapping row.
        """
        self._open_document = open_document
        self._master_map = master_map
        self._auto_prefixes = auto_prefixes
        self._detector = detector
        self._fuzzy_threshold = fuzzy_threshold
        self._custom_words_score = custom_words_score
        self._fixed_masks = fixed_masks

    def execute(
        self,
        source: object,
        custom_words: list[str],
        *,
        style: RedactionStyle = RedactionStyle.PSEUDONYMIZE,
        redact_images: bool = False,
        exclude: frozenset[str] = frozenset(),
    ) -> PdfRedactionResult:
        """Redact ``source`` and return new bytes, findings, page count, crosswalk.

        Names, organizations, emails, URLs and masked types are always
        detected automatically (``detector``, no toggle). ``custom_words`` is an
        additional list of words/phrases to redact on every page - matched
        literally and case-insensitively (see
        ``domain/custom_words.find_custom_words``). An empty ``custom_words``
        list just means there's nothing extra to add on top of the automatic
        detection - this method runs cleanly either way.

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
            # Before redacting: ``apply_redactions`` silently deletes links
            # that overlap a redaction, which would make this count too low.
            removed_links = document.remove_external_links()
            findings: list[Finding] = []
            bracketed = 0
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
                        *self._detector.analyze(
                            normalized.text,
                            [*_ENTITIES, *self._fixed_masks],
                            _THRESHOLD,
                        ),
                        *find_custom_words(
                            normalized.text, custom_words, self._custom_words_score
                        ),
                    ]
                    if has_text
                    else []
                )

                # Sorted by position, not by dedupe_overlapping's own order:
                # that sorts by source priority first (see domain/rules.py), so
                # a master-list match late on the page would otherwise be
                # assigned - and therefore numbered - before a custom-word match
                # near the top. The gateway adds all annotations and applies
                # them in one pass, so the order it receives them in is
                # irrelevant to the output; it only fixes the label numbering.
                bracketed += len(_BRACKETED_NUMBER.findall(normalized.text))

                kept = sorted(
                    dedupe_overlapping(detections), key=lambda d: d.span.start
                )
                redactions: list[tuple[str | list[str], str]] = []
                for detection in kept:
                    # Dropped before ``assign``, so an excluded term claims no
                    # ordinal and the labels that do get written stay
                    # contiguous. It also never reaches the crosswalk, which is
                    # what keeps it out of the names-free mapping file.
                    if normalize(detection.text) in exclude:
                        continue
                    # The document gets the document-local label, never the
                    # pseudonym: the pseudonym embeds the master-list Internal
                    # ID, and keeping that out of the output is the whole point
                    # of the two-hop scheme (see domain/pseudonyms.py).
                    # A bank/payment mask skips ``assign`` too, for the same
                    # two reasons: no ordinal, and no mapping row.
                    label = (
                        self._fixed_masks.get(detection.entity_type)
                        or pseudonymizer.assign(
                            detection.entity_type, detection.text
                        ).label
                    )
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
                    redactions.append((candidates, label))

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
                source_bracketed_numbers=bracketed,
                removed_links=removed_links,
            )
        finally:
            document.close()
