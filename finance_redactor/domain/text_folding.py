"""Accent (diacritic) folding, shared by every name-matching path.

A US/ASCII keyboard can't easily type accented Latin characters (``José``,
``Muñoz``, ``André``), so both the master list and documents may spell the
same name with or without accents. Every place that compares two name
strings - the ad-hoc "words to redact" box (:mod:`domain.custom_words`), the
master-list Aho-Corasick recognizer
(:mod:`infrastructure.detection.custom_recognizer`), and pseudonym-code
lookup (:mod:`domain.pseudonyms`) - needs to treat the accented and
unaccented spellings as the same name, in both directions.
"""

from __future__ import annotations

import unicodedata


def fold_diacritics(text: str) -> str:
    """Strip combining accent marks (``José`` -> ``Jose``), one output char per input char.

    Each character is Unicode-decomposed (NFKD) on its own and reduced to its
    first non-combining component, falling back to the original character if
    decomposition yields none. This keeps the result the **same length** as
    ``text``, so offsets found on a folded copy map back exactly onto the
    original.
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
