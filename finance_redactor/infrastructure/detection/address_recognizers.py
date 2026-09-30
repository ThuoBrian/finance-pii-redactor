"""Presidio recognizer for postal and street addresses.

Deliberately pattern-based, not spaCy's LOCATION type: the model tags every
town and country ("Nairobi", "Kenya") but misses the parts that actually
locate someone ("P.O. Box 12345-00100", "Plot 7", "14 Ngong Road"). Plain
place names are left alone by design; see docs/troubleshooting.md.

Every match becomes the fixed ``[ADDRESS]`` mask (``Settings.fixed_masks``),
so a raw address never reaches the crosswalk or the PDF mapping.

Street suffixes must be capitalised or all caps. Lowercase ``road`` or
``street`` in prose is not an address, and the ALL-CAPS form still matches.
Suffixes that are also everyday words ("Drive", "Close", "Way", as in "Year
End Close") only count after a house number.
"""

from __future__ import annotations

import re

from finance_redactor.infrastructure.detection.financial_recognizers import (
    LabelledNumberRecognizer,
)


def _cased(words: list[str]) -> str:
    """Alternation of each word as capitalised or all caps (``Road|ROAD``)."""
    return "|".join(f"{w}|{w.upper()}" for w in words)


_WORD = r"[A-Z][A-Za-z'-]+"
_NAME = rf"{_WORD}(?:\s+{_WORD}){{0,2}}"
_HOUSE_NUMBER = r"\d{1,5}[A-Za-z]?"
_STRONG_SUFFIX = _cased(["Road", "Rd", "Street", "Avenue", "Ave", "Lane"])
_STRONG_SUFFIX += "|" + _cased(["Crescent", "Highway"])
_WEAK_SUFFIX = _cased(["Drive", "Close", "Way"])

_POSTAL = (
    r"(?i:\bp\.?\s?o\.?\s*box|\bprivate\s+bag)\s*(?i:no\.?\s*)?\d{1,6}"
    r"(?:\s*[-\u2013]\s*\d{5})?"
    # Trailing town, as in "P.O. Box 123-00100, Nairobi".
    rf"(?:\s*,?\s*{_WORD})?"
    # A bare "Box 12" is too common in forms; the postcode makes it an address.
    r"|(?i:\bbox)\s*\d{1,6}\s*[-\u2013]\s*\d{5}"
)
_PLOT = (
    r"\b(?:[Pp]lot|PLOT|House|HOUSE|Hse|HSE|L\.?\s?R\.?)"
    r"(?i:\s*(?:no\.?|number))?\s*[:#.]?\s*\d(?:[\w/-]*\w)?"
)
_STREET = (
    rf"\b(?:{_HOUSE_NUMBER}\s+)?{_NAME}\s+(?:{_STRONG_SUFFIX})\b\.?"
    rf"|\b{_HOUSE_NUMBER}\s+{_NAME}\s+(?:{_WEAK_SUFFIX})\b\.?"
)

ADDRESS_PATTERN = re.compile(rf"(?P<value>{_POSTAL}|{_PLOT}|{_STREET})")


def build_address_recognizers() -> list[LabelledNumberRecognizer]:
    """Return the address recognizer (a list, like the financial builder)."""
    return [LabelledNumberRecognizer("ADDRESS", ADDRESS_PATTERN)]
