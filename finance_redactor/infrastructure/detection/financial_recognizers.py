"""Presidio recognizers for Kenyan bank accounts, M-Pesa numbers and SWIFT codes.

Card numbers and IBANs don't need anything here - Presidio's own
``CreditCardRecognizer`` (Luhn) and ``IbanRecognizer`` (checksum) cover them.
The three formats below have no checksum, and a bare 10-digit number looks
exactly like an invoice number or a staff ID. So each one only matches when
its label is right in front of it ("A/C No:", "Paybill", "SWIFT"), and the
label is part of the regex itself rather than a Presidio context word.
Context words only boost a score when real NLP tokens exist, and the PDF
detector has none (see ``pattern_detector.py``), so a context-word design
would quietly never fire on PDFs.

The returned span covers the value only, never the label, so "A/C No:
0123456789" becomes "A/C No: [ACCOUNT]".
"""

from __future__ import annotations

import re

from presidio_analyzer import AnalysisExplanation, EntityRecognizer, RecognizerResult

# Above the PDF flow's 0.4 threshold and the UI's default, below a master-list
# hit. The label requirement is what makes these reliable, not the score.
_SCORE = 0.85

# Label words match in any case; the values themselves are digits, except
# SWIFT codes, which are uppercase by definition and matched that way.
# Optional "No." / "Number" / "#" and a separator follow each label.
_NUMBER_WORD = r"(?i:\s*(?:no\.?|number|#))?\s*[:#.-]?\s*"

_PATTERNS: dict[str, re.Pattern[str]] = {
    # 8-16 digits, single spaces or hyphens allowed between digits.
    "KE_BANK_ACCOUNT": re.compile(
        r"(?i:\b(?:a/c|acct|acc|account))\.?"
        + _NUMBER_WORD
        + r"(?P<value>\d(?:[ -]?\d){7,15})\b"
    ),
    "MPESA_NUMBER": re.compile(
        r"(?i:\b(?:till|pay\s?bill|m-?pesa|business\s+(?:no\.?|number)))"
        + _NUMBER_WORD
        + r"(?P<value>\d{5,7})\b"
    ),
    # 4 bank + 2 country letters, 2 location characters, optional 3 for branch.
    "SWIFT_CODE": re.compile(
        r"(?i:\b(?:swift|bic)(?:\s*code)?)\s*[:#.-]?\s*"
        r"(?P<value>[A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?)\b"
    ),
}


class LabelledNumberRecognizer(EntityRecognizer):
    """Matches a value only when its label sits right before it."""

    def __init__(self, supported_entity: str, pattern: re.Pattern[str]) -> None:
        """Build a recognizer for one entity type from a regex with a ``value`` group."""
        super().__init__(
            supported_entities=[supported_entity],
            name=f"{supported_entity.title().replace('_', '')}Recognizer",
        )
        self._pattern = pattern

    def load(self) -> None:
        """No-op: the regex is compiled at import time."""

    def analyze(
        self, text: str, entities: list[str], nlp_artifacts=None
    ) -> list[RecognizerResult]:
        """Return the value span of every labelled match in ``text``."""
        entity = self.supported_entities[0]
        if entity not in entities or not text:
            return []
        return [
            RecognizerResult(
                entity_type=entity,
                start=match.start("value"),
                end=match.end("value"),
                score=_SCORE,
                analysis_explanation=AnalysisExplanation(
                    recognizer=self.__class__.__name__,
                    original_score=_SCORE,
                    pattern_name=entity,
                    pattern=self._pattern.pattern,
                    textual_explanation=f"Labelled {entity.lower()} value",
                ),
            )
            for match in self._pattern.finditer(text)
        ]


def build_financial_recognizers() -> list[LabelledNumberRecognizer]:
    """Return one recognizer per labelled financial format."""
    return [
        LabelledNumberRecognizer(entity, pattern)
        for entity, pattern in _PATTERNS.items()
    ]
