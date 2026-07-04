"""Core domain entities and value objects.

These types are the single, framework-neutral representation of a PII finding.
Adapters convert their library-specific results (e.g. Presidio's
``RecognizerResult``) into these on the way in, so no other layer depends on a
third-party data model.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DetectionSource(str, Enum):
    """Where a detection originated.

    The string values are also the human-readable labels shown in the UI's
    "Source" column. ``MASTER_LIST`` covers names matched against the maintained
    master list; ``MODEL`` covers names found only by the spaCy NER model.
    """

    MODEL = "model"
    MASTER_LIST = "master list"


@dataclass(frozen=True)
class Span:
    """A half-open character range ``[start, end)`` within some text."""

    start: int
    end: int

    def overlaps(self, other: Span) -> bool:
        """Return True if this span and ``other`` share at least one position."""
        return self.start < other.end and self.end > other.start


@dataclass(frozen=True)
class PiiDetection:
    """One detected piece of PII within a single text string.

    ``text`` is the exact matched substring, carried alongside the span so
    downstream layers (PDF search, findings tables) need not re-slice.
    """

    entity_type: str
    span: Span
    score: float
    text: str
    source: DetectionSource


@dataclass(frozen=True)
class Finding:
    """A reportable detection located within a document (page-oriented).

    Used for the PDF flow's detection summary; ``page`` is zero-based.
    """

    page: int
    detected_text: str
    entity_type: str
    score: float
    source: DetectionSource
