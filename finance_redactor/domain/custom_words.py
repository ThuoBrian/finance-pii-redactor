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
from collections.abc import Iterable

from finance_redactor.domain.entities import DetectionSource, PiiDetection, Span

_CUSTOM_ENTITY_TYPE = "CUSTOM"


def find_custom_words(
    text: str, words: Iterable[str], score: float
) -> list[PiiDetection]:
    """Find literal, case-insensitive, whole-word/phrase matches of ``words`` in ``text``.

    Blank/whitespace-only entries in ``words`` are skipped. Internal
    whitespace inside a multi-word phrase matches flexibly (one or more
    spaces), and each match is boundary-checked (no word character
    immediately before or after) so a short word like ``cat`` doesn't fire
    inside ``category`` - the same spirit as ``CustomNameRecognizer``'s
    matching, just standalone. Every match gets ``entity_type="CUSTOM"`` and
    ``source=DetectionSource.CUSTOM``.
    """
    detections: list[PiiDetection] = []
    for word in words:
        word = word.strip()
        if not word:
            continue
        tokens = word.split()
        pattern = re.compile(
            r"(?<!\w)" + r"\s+".join(re.escape(token) for token in tokens) + r"(?!\w)",
            re.IGNORECASE,
        )
        for match in pattern.finditer(text):
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
