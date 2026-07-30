"""Presidio recognizer for names supplied via the master list.

This is an infrastructure adapter: it subclasses Presidio's ``EntityRecognizer``
so the analyzer can call it, but matching itself is a single Aho-Corasick
automaton (``pyahocorasick``) rather than one regex per name. Scanning a text
used to cost O(number of names) regex passes — with a ~26k-row master list that
was ~64ms per unique text, the dominant cost on any file with more than a few
hundred unique values. An automaton scans the text once, in time proportional
to the text length, regardless of how many names are loaded.

The match score is injected (from ``Settings``) rather than imported from a
constants module, removing the duplicated ``0.9`` magic number.
"""

from __future__ import annotations

import re

import ahocorasick
from presidio_analyzer import (
    AnalysisExplanation,
    EntityRecognizer,
    RecognizerResult,
)

from finance_redactor.domain.aliases import aliases
from finance_redactor.domain.entities import Span
from finance_redactor.infrastructure.detection.pdf_text_normalizer import (
    normalize_pdf_text,
)

# Matches Python regex \w (Unicode word character): used to replicate \b-style
# boundary checks against automaton match positions instead of a regex engine.
_WORD_CHAR = re.compile(r"\w", re.UNICODE)


def _is_word_char(ch: str) -> bool:
    return bool(_WORD_CHAR.match(ch))


class CustomNameRecognizer(EntityRecognizer):
    r"""Recognizes names supplied via the master list.

    Every alias variant of every loaded name (org-suffix equivalents, ``&``/
    ``and`` swaps — see :mod:`finance_redactor.domain.aliases`) is inserted as a
    literal key into one Aho-Corasick automaton per entity type, lowercased for
    case-insensitive matching. ``analyze`` then makes one pass over the
    (whitespace-normalized) input text: automaton matches are exact literal hits,
    so equivalents that a regex would express with ``\\s+`` or alternation are
    instead pre-expanded into separate literal keys before matching, and a
    boundary check (equivalent to the old ``\\b...(?!\\w)`` regex wrapper) is
    applied to each raw match afterward.
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
        self._automaton = self._build_automaton()

    def _build_automaton(self) -> ahocorasick.Automaton:
        automaton = ahocorasick.Automaton()
        for raw_name in self.names:
            for variant in aliases(raw_name):
                key = variant.lower()
                if key:
                    # Later names win ties on an identical alias key; harmless,
                    # since this only affects the informational explanation
                    # text below, not the span/score a match produces, and not
                    # pseudonym resolution (which re-looks-up the matched text
                    # against the master map independently).
                    automaton.add_word(key, (raw_name, len(key)))
        automaton.make_automaton()
        return automaton

    def load_analysis_pattern(self) -> None:  # noqa: D102
        pass

    def analyze(
        self,
        text: str,
        entities: list[str],
        nlp_artifacts=None,
    ) -> list[RecognizerResult]:
        """Find all loaded names (and their alias variants) in ``text``."""
        if not self.names or not text:
            return []

        supported_entity = self.supported_entities[0]
        if supported_entity not in entities:
            return []

        # Collapsing whitespace runs to one space replicates the old regex's
        # `\s+` flexibility between name tokens (irregular spacing in Excel
        # cells, or PDF text already normalized upstream — reapplying here is
        # a no-op in that case). `to_raw_span` maps matches back to `text`.
        normalized = normalize_pdf_text(text)
        haystack = normalized.text.lower()

        results: list[RecognizerResult] = []
        for end_index, (raw_name, key_len) in self._automaton.iter(haystack):
            start = end_index - key_len + 1
            end = end_index + 1
            if start > 0 and _is_word_char(haystack[start - 1]):
                continue
            if end < len(haystack) and _is_word_char(haystack[end]):
                continue
            raw_span = normalized.to_raw_span(Span(start, end))
            results.append(
                RecognizerResult(
                    entity_type=supported_entity,
                    start=raw_span.start,
                    end=raw_span.end,
                    score=self._score,
                    analysis_explanation=AnalysisExplanation(
                        recognizer=self.__class__.__name__,
                        original_score=self._score,
                        pattern_name=f"custom list: {raw_name}",
                        pattern=raw_name,
                        textual_explanation=(
                            f"Name matched custom {supported_entity.lower()} list"
                        ),
                    ),
                )
            )
        return results

    def load(self) -> None:
        """No-op: the automaton is built at construction time."""


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
