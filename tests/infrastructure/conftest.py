"""Fixtures for exercising the real ``PresidioEngine`` without spaCy.

``regex_engine`` builds the production engine - same registry, same
financial, address and master-list recognizers - on a no-op NLP engine, so
every regex path runs for real in a few seconds instead of loading
``en_core_web_lg``. spaCy's own PERSON/ORG guesses are therefore absent;
that part is covered with a mocked analyzer in ``test_presidio_detector.py``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator

import pytest
from presidio_analyzer.nlp_engine import NlpArtifacts, NlpEngine

from finance_redactor.config import DEFAULT_SETTINGS
from finance_redactor.infrastructure.detection.custom_recognizer import (
    build_custom_recognizers,
)
from finance_redactor.infrastructure.detection.presidio_detector import PresidioEngine


class NullNlpEngine(NlpEngine):
    """A real, truthy no-op ``NlpEngine`` that never loads a model.

    Must be truthy: ``AnalyzerEngine`` treats a falsy ``nlp_engine`` (even
    ``None``) as "not provided" and silently loads its own spaCy default.
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
            tokens=[],  # type: ignore[arg-type]  # no real spaCy Doc
            tokens_indices=[],
            lemmas=[],
            nlp_engine=self,
            language=language,
        )

    def process_batch(
        self,
        texts: Iterable[str],
        language: str,
        batch_size: int = 1,
        n_process: int = 1,
        **kwargs: object,
    ) -> Iterator[tuple[str, NlpArtifacts]]:
        """Yield empty artifacts for each text, matching the base signature."""
        for text in texts:
            yield text, self.process_text(text, language)

    def is_stopword(self, word: str, language: str) -> bool:
        """Report nothing as a stopword."""
        return False

    def is_punct(self, word: str, language: str) -> bool:
        """Report nothing as punctuation."""
        return False

    def get_supported_entities(self) -> list[str]:
        """Report no NLP-derived entities."""
        return []

    def get_supported_languages(self) -> list[str]:
        """Report the one language the app runs in."""
        return ["en"]


@pytest.fixture
def regex_engine() -> Callable[..., PresidioEngine]:
    """Return a factory: ``regex_engine(people=[...], orgs=[...])``."""

    def build(
        people: list[str] | None = None, orgs: list[str] | None = None
    ) -> PresidioEngine:
        recognizers = build_custom_recognizers(
            people or [], orgs or [], DEFAULT_SETTINGS.custom_match_score
        )
        return PresidioEngine(DEFAULT_SETTINGS, recognizers, nlp_engine=NullNlpEngine())

    return build
