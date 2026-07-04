"""Domain layer: framework-free entities and business rules.

This layer has no dependency on Presidio, PyMuPDF, pandas, or Streamlit. It
defines the vocabulary the rest of the system speaks (``PiiDetection``, ``Span``,
``Finding``) and the pure rules that operate on it (deduplication, source
classification, and pseudonym assignment).
"""

from finance_redactor.domain.entities import (
    DetectionSource,
    Finding,
    PiiDetection,
    Span,
)
from finance_redactor.domain.pseudonyms import (
    Assignment,
    MasterEntry,
    Pseudonymizer,
    apply_replacements,
    normalize,
)
from finance_redactor.domain.rules import (
    classify_source,
    dedupe_overlapping,
)

__all__ = [
    "Span",
    "PiiDetection",
    "Finding",
    "DetectionSource",
    "dedupe_overlapping",
    "classify_source",
    "Assignment",
    "MasterEntry",
    "Pseudonymizer",
    "apply_replacements",
    "normalize",
]
