"""Domain layer: framework-free entities and business rules.

This layer has no dependency on Presidio, PyMuPDF, pandas, or any web framework. It
defines the vocabulary the rest of the system speaks (``PiiDetection``, ``Span``,
``Finding``) and the pure rules that operate on it (deduplication, source
classification, and pseudonym assignment).
"""
