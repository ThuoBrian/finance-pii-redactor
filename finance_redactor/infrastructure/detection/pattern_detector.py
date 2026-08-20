"""Lightweight, spaCy-free email/URL detection for the PDF flow.

Implements the :class:`PiiDetector` port, like ``PresidioEngine``, but
deliberately does *not* wrap the full spaCy-backed analyzer: PDF has no
automatic name/organization detection at all (a deliberate team decision -
see ``application/redact_pdf.py``), yet emails and websites are still worth
catching automatically, since matching them is a deterministic pattern, not
a statistical guess. Presidio's own ``EmailRecognizer``/``UrlRecognizer`` are
plain regex (``PatternRecognizer`` subclasses) - reused here directly rather
than hand-rolling a URL/TLD regex, since Presidio's is already well-tested
and already a project dependency.

Gotcha (verified by measuring actual construction time/memory, not
assumed): ``AnalyzerEngine.__init__`` treats a falsy ``nlp_engine`` argument -
including the seemingly obvious ``nlp_engine=None`` - as "not provided" and
silently builds *and loads* its own default engine, which is the full
spaCy-backed one (``NlpEngineProvider().create_engine()`` followed by
``.load()``). Passing ``None`` measured at ~14s / ~690MB peak - identical to
loading ``en_core_web_lg`` directly - completely defeating the point of this
detector. The fix is ``_NullNlpEngine`` below: a real (truthy) ``NlpEngine``
instance whose ``is_loaded()`` is always ``True`` (so ``AnalyzerEngine`` never
calls ``.load()``) and whose ``process_text()`` returns an empty
``NlpArtifacts`` with no real NLP work done. With it, construction measured
at ~2s (pure package-import cost, no tracemalloc skew) / ~56MB peak, and
``en_core_web_lg`` never appears in ``sys.modules``. Email/URL matching
itself doesn't need real NLP artifacts (tokens/lemmas) - it's pure regex;
the only thing lost is optional context-word score boosting, which these
recognizers don't rely on to clear their own score thresholds.
"""

from __future__ import annotations

from presidio_analyzer import AnalyzerEngine, RecognizerRegistry, RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts, NlpEngine
from presidio_analyzer.predefined_recognizers import EmailRecognizer, UrlRecognizer

from finance_redactor.domain.entities import DetectionSource, PiiDetection, Span
from finance_redactor.domain.rules import dedupe_overlapping


class _NullNlpEngine(NlpEngine):
    """A real, truthy no-op ``NlpEngine`` - never loads a model.

    Exists solely to stop ``AnalyzerEngine.__init__`` from substituting its
    own spaCy-backed default when no NLP engine is supplied (see the module
    docstring). Every method is a cheap no-op; nothing here ever touches
    spaCy or a model file.
    """

    def load(self) -> None:
        """Do nothing - there is no model to load."""

    def is_loaded(self) -> bool:
        """Report already loaded, so ``AnalyzerEngine`` never calls ``load()``."""
        return True

    def process_text(self, text: str, language: str) -> NlpArtifacts:
        """Return empty artifacts - pattern recognizers don't need real NLP."""
        return NlpArtifacts(
            entities=[],
            tokens=[],
            tokens_indices=[],
            lemmas=[],
            nlp_engine=self,
            language=language,
        )

    def process_batch(self, texts, language, batch_size=1, n_process=1, **kwargs):
        """Yield empty artifacts for each text, matching the base signature."""
        for text in texts:
            yield text, self.process_text(text, language)

    def is_stopword(self, word: str, language: str) -> bool:
        """Report nothing as a stopword - no real tokenization happens."""
        return False

    def is_punct(self, word: str, language: str) -> bool:
        """Report nothing as punctuation - no real tokenization happens."""
        return False

    def get_supported_entities(self) -> list[str]:
        """Report no NLP-derived entities - only the pattern recognizers matter."""
        return []

    def get_supported_languages(self) -> list[str]:
        """Report the one language this detector is built for."""
        return ["en"]


class PatternDetector:
    """Detects only email addresses and URLs, with no NLP model involved."""

    def __init__(self, language: str = "en") -> None:
        """Build an analyzer containing only the two pattern recognizers."""
        self._language = language
        registry = RecognizerRegistry()
        registry.add_recognizer(EmailRecognizer(supported_language=language))
        registry.add_recognizer(UrlRecognizer(supported_language=language))
        self._analyzer = AnalyzerEngine(
            registry=registry,
            nlp_engine=_NullNlpEngine(),
            supported_languages=[language],
        )

    def analyze(
        self, text: str, entities: list[str], threshold: float
    ) -> list[PiiDetection]:
        """Return all email/URL matches in ``text`` for the requested entity types.

        ``entities`` is still respected (e.g. a caller can request only
        ``["EMAIL_ADDRESS"]``), but this detector can never return anything
        other than ``EMAIL_ADDRESS``/``URL`` regardless, since that's all its
        registry contains.
        """
        if not text.strip():
            return []
        results = self._analyzer.analyze(
            text=text,
            language=self._language,
            entities=entities,
            score_threshold=threshold,
        )
        detections = [self._to_detection(result, text) for result in results]
        return dedupe_overlapping(detections)

    @staticmethod
    def _to_detection(result: RecognizerResult, text: str) -> PiiDetection:
        return PiiDetection(
            entity_type=result.entity_type,
            span=Span(result.start, result.end),
            score=result.score,
            text=text[result.start : result.end],
            source=DetectionSource.PATTERN,
        )
