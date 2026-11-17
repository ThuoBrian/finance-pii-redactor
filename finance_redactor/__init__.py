"""Finance PII Redactor.

A clean-architecture rebuild of the local PII redaction tool. Layers, from the
core outward, follow the dependency rule (inner layers know nothing of outer):

- ``domain``         - framework-free entities and business rules.
- ``application``    - use cases orchestrating the domain via abstract ports.
- ``infrastructure`` - concrete adapters (Presidio, PyMuPDF, openpyxl, files).
- ``presentation``   - the local web API, the built interface, view formatting.

``config.Settings`` is the single source of truth for tunable constants.
"""
