"""Ad-hoc word/phrase matching for the PDF and Word "words to redact" box.

A small, framework-free literal matcher - deliberately independent of
Presidio/``CustomNameRecognizer``'s automaton machinery. That machinery is
built once and cached process-wide (``app.py``'s ``_get_master_list_bundle``,
keyed on the master-list workbook), which is right for a ~26k-row curated
list but wrong for a handful of words one user types for one run: routing
them through the shared cached engine would mean either mutating it (a
cross-session leak - one user's ad-hoc words becoming visible to another) or
rebuilding it per request. Neither is needed here, so this stays a separate,
standalone regex-based path merged in at the application layer (see
``redact_pdf.py``/``redact_docx.py``).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from finance_redactor.domain.entities import DetectionSource, PiiDetection, Span

_CUSTOM_ENTITY_TYPE = "CUSTOM"


def _fold_diacritics(text: str) -> str:
    """Strip combining accent marks (``José`` -> ``Jose``), one output char per input char.

    Each character is Unicode-decomposed (NFKD) on its own and reduced to its
    first non-combining component, falling back to the original character if
    decomposition yields none. This keeps the result the **same length** as
    ``text`` (mirroring :func:`recasing.recase_uppercase`'s length-preserving
    approach) so offsets found on a folded copy map back exactly onto the
    original - needed because many Latin American (and other) names carry
    accents (``José``, ``Muñoz``, ``André``) that a US/ASCII keyboard can't
    easily type, so a user typing the unaccented form into the "words to
    redact" box should still match the accented form in the document, and
    vice versa (e.g. an OCR pass that dropped accents).
    """
    return "".join(
        next(
            (
                c
                for c in unicodedata.normalize("NFKD", ch)
                if not unicodedata.combining(c)
            ),
            ch,
        )
        for ch in text
    )


def find_custom_words(
    text: str, words: Iterable[str], score: float
) -> list[PiiDetection]:
    """Find literal, case- and accent-insensitive matches of ``words`` in ``text``.

    Blank/whitespace-only entries in ``words`` are skipped. Internal
    whitespace inside a multi-word phrase matches flexibly (one or more
    spaces), and each match is boundary-checked (no word character
    immediately before or after) so a short word like ``cat`` doesn't fire
    inside ``category`` - the same spirit as ``CustomNameRecognizer``'s
    matching, just standalone. Matching is accent-insensitive in both
    directions via :func:`_fold_diacritics` (typing ``Jose Garcia`` matches
    ``José García`` in the text, and typing ``José`` matches an unaccented
    ``Jose`` in the text) - the reported ``PiiDetection.text`` still comes
    from the original, unfolded text, so the real accented spelling is what
    shows up in the crosswalk/review table. Every match gets
    ``entity_type="CUSTOM"`` and ``source=DetectionSource.CUSTOM``.
    """
    detections: list[PiiDetection] = []
    folded_text = _fold_diacritics(text)
    for word in words:
        word = word.strip()
        if not word:
            continue
        tokens = _fold_diacritics(word).split()
        pattern = re.compile(
            r"(?<!\w)" + r"\s+".join(re.escape(token) for token in tokens) + r"(?!\w)",
            re.IGNORECASE,
        )
        for match in pattern.finditer(folded_text):
            detections.append(
                PiiDetection(
                    entity_type=_CUSTOM_ENTITY_TYPE,
                    span=Span(match.start(), match.end()),
                    score=score,
                    text=text[match.start() : match.end()],
                    source=DetectionSource.CUSTOM,
                )
            )
    return detections
