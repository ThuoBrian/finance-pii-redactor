"""Why a detection deserves a second look in the review table.

Only the spaCy model guesses. A master-list name, a typed word and a pattern
match (email, bank number, address) were put there on purpose or matched a
strict rule, so they never get a hint. The hint is a reading aid and a sort
key for the reviewer; it never changes what is redacted.
"""

from __future__ import annotations

from finance_redactor.domain.common_words import COMMON_ENGLISH_WORDS
from finance_redactor.domain.entities import DetectionSource

ORDINARY_WORD = "ordinary word"
ALL_CAPS = "ALL-CAPS"
ONE_WORD_ORGANIZATION = "one-word organization"


def review_hint(text: str, entity_type: str, source: DetectionSource) -> str:
    """Return a short reason to double-check a model guess, or "" for none.

    ``ordinary word`` is a plain English function word (``the``, ``across``) and
    is the strongest signal. ``ALL-CAPS`` marks the usual heading and acronym
    false positives from the recasing pass (``TOTAL AMOUNT``, ``USD``).
    ``one-word organization`` is weaker: real organizations are sometimes one
    word, but so are the labels the model mistakes for one.
    """
    if source is not DetectionSource.MODEL:
        return ""
    words = text.split()
    if len(words) == 1 and words[0].casefold() in COMMON_ENGLISH_WORDS:
        return ORDINARY_WORD
    if text.isupper():
        return ALL_CAPS
    if len(words) == 1 and entity_type == "ORGANIZATION":
        return ONE_WORD_ORGANIZATION
    return ""
