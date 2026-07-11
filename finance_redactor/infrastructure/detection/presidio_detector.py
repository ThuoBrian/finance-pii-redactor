"""Presidio-backed PII detector.

Implements the :class:`PiiDetector` port. It is the only place that knows about
``AnalyzerEngine`` and the spaCy NLP engine. Library-specific
``RecognizerResult`` objects are translated into the domain's
:class:`PiiDetection` at this boundary, so nothing upstream depends on Presidio.
Replacement (pseudonymization) is handled in the domain, not here.
"""

from __future__ import annotations

from collections.abc import Sequence

from presidio_analyzer import AnalyzerEngine, RecognizerResult
from presidio_analyzer.nlp_engine import NlpEngine, NlpEngineProvider

from finance_redactor.config import Settings
from finance_redactor.domain.entities import PiiDetection, Span
from finance_redactor.domain.rules import classify_source, dedupe_overlapping
from finance_redactor.infrastructure.detection.custom_recognizer import (
    CustomNameRecognizer,
)
from finance_redactor.infrastructure.detection.recasing import recase_uppercase


class PresidioEngine:
    """Detects PII via Microsoft Presidio + spaCy."""

    def __init__(
        self,
        settings: Settings,
        recognizers: Sequence[CustomNameRecognizer] = (),
        nlp_engine: NlpEngine | None = None,
    ) -> None:
        """Build the analyzer (spaCy model + custom recognizers).

        ``nlp_engine`` can be injected so the heavy spaCy model is loaded once
        and cached while the lightweight master-list recognizers are rebuilt on
        every run. When omitted, a new engine is created.
        """
        self._settings = settings
        if nlp_engine is None:
            nlp_engine = self._create_nlp_engine(settings)
        self._analyzer = AnalyzerEngine(
            nlp_engine=nlp_engine,
            supported_languages=[settings.language],
        )
        for recognizer in recognizers:
            self._analyzer.registry.add_recognizer(recognizer)

    @staticmethod
    def _create_nlp_engine(settings: Settings) -> NlpEngine:
        """Create and return the heavy spaCy NLP engine.

        This is a separate method so callers can cache just the model and reuse
        it across PresidioEngine instances with fresh custom recognizers.
        """
        configuration = {
            "nlp_engine_name": "spacy",
            "models": [
                {"lang_code": settings.language, "model_name": settings.spacy_model}
            ],
        }
        provider = NlpEngineProvider(nlp_configuration=configuration)
        return provider.create_engine()

    def analyze(
        self, text: str, entities: list[str], threshold: float
    ) -> list[PiiDetection]:
        """Detect PII in a single text string and return domain detections.

        Runs spaCy once on the raw text and, when the text contains ALL-CAPS
        tokens, a second time on a length-preserving recased copy
        (``MARY WANJIRU`` -> ``Mary Wanjiru``) that the model can recognize. Spans
        from both passes are valid against the original ``text`` (recasing
        preserves length), so they are unioned and de-duplicated; the higher-score
        detection wins exact-span ties.
        """
        if not isinstance(text, str) or not text.strip():
            return []
        results = list(
            self._analyzer.analyze(
                text=text,
                language=self._settings.language,
                entities=entities,
                score_threshold=threshold,
            )
        )
        recased = recase_uppercase(text)
        if recased != text:
            results.extend(
                self._analyzer.analyze(
                    text=recased,
                    language=self._settings.language,
                    entities=entities,
                    score_threshold=threshold,
                )
            )
        # The same span can be detected in both the original and recased passes
        # with different scores. Prefer the higher-confidence result for exact
        # spans before the domain rule deduplicates overlapping spans.
        results.sort(key=lambda r: r.score, reverse=True)
        best_by_span: dict[tuple[int, int], RecognizerResult] = {}
        for result in results:
            key = (result.start, result.end)
            if key not in best_by_span:
                best_by_span[key] = result

        detections = [
            self._to_detection(result, text) for result in best_by_span.values()
        ]
        return dedupe_overlapping(detections)

    def _to_detection(self, result: RecognizerResult, text: str) -> PiiDetection:
        return PiiDetection(
            entity_type=result.entity_type,
            span=Span(result.start, result.end),
            score=result.score,
            text=text[result.start : result.end],
            source=classify_source(result.score, self._settings.custom_match_score),
        )
