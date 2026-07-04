"""Presidio recognizer for names supplied via plain-text lists.

This is an infrastructure adapter: it subclasses Presidio's ``EntityRecognizer``
so the analyzer can call it, but the matching itself is plain regex. The match
score is injected (from ``Settings``) rather than imported from a constants
module, removing the duplicated ``0.9`` magic number.
"""

from __future__ import annotations

import re

from presidio_analyzer import (
    AnalysisExplanation,
    EntityRecognizer,
    RecognizerResult,
)


class CustomNameRecognizer(EntityRecognizer):
    """Recognizes names supplied via plain-text lists.

    Each loaded name is searched as a case-insensitive whole-word/phrase pattern
    within a cell and returned as a Presidio RecognizerResult.
    """

    def __init__(
        self,
        supported_entity: str,
        names: list[str] | None = None,
        score: float = 0.9,
        name: str = "CustomNameRecognizer",
    ) -> None:
        """Initialize recognizer for one entity type with a list of names."""
        super().__init__(supported_entities=[supported_entity], name=name)
        self.names = [n.strip() for n in (names or []) if n.strip()]
        self._score = score
        self._patterns = self._compile_patterns()

    def _compile_patterns(self) -> dict[str, re.Pattern[str]]:
        compiled: dict[str, re.Pattern[str]] = {}
        for raw_name in self.names:
            # Escape regex metacharacters, then allow word boundaries on both sides.
            escaped = re.escape(raw_name)
            pattern = re.compile(rf"\b{escaped}\b", re.IGNORECASE | re.UNICODE)
            compiled[raw_name] = pattern
        return compiled

    def load_analysis_pattern(self) -> None:  # noqa: D102
        pass

    def analyze(
        self,
        text: str,
        entities: list[str],
        nlp_artifacts=None,
        regex_flags: int = re.IGNORECASE | re.UNICODE,
    ) -> list[RecognizerResult]:
        """Find all loaded names in ``text``."""
        if not self.names or not text:
            return []

        supported_entity = self.supported_entities[0]
        if supported_entity not in entities:
            return []

        results: list[RecognizerResult] = []
        for raw_name, pattern in self._patterns.items():
            escaped = re.escape(raw_name)
            for match in pattern.finditer(text):
                results.append(
                    RecognizerResult(
                        entity_type=supported_entity,
                        start=match.start(),
                        end=match.end(),
                        score=self._score,
                        analysis_explanation=AnalysisExplanation(
                            recognizer=self.__class__.__name__,
                            original_score=self._score,
                            pattern_name=f"custom list: {raw_name}",
                            pattern=escaped,
                            textual_explanation=f"Name matched custom {supported_entity.lower()} list",
                        ),
                    )
                )
        return results

    def load(self) -> None:
        """No-op: patterns are compiled at construction time."""


def build_custom_recognizers(
    person_names: list[str],
    organization_names: list[str],
    score: float,
) -> list[CustomNameRecognizer]:
    """Create up to two recognizers (PERSON, ORGANIZATION) from name lists.

    A recognizer is created only when its list is non-empty, matching the
    original behavior.
    """
    recognizers: list[CustomNameRecognizer] = []
    if person_names:
        recognizers.append(
            CustomNameRecognizer(
                supported_entity="PERSON",
                names=person_names,
                score=score,
                name="CustomPersonRecognizer",
            )
        )
    if organization_names:
        recognizers.append(
            CustomNameRecognizer(
                supported_entity="ORGANIZATION",
                names=organization_names,
                score=score,
                name="CustomOrganizationRecognizer",
            )
        )
    return recognizers
