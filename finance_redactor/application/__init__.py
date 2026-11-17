"""Application layer: use cases and the ports they depend on.

Use cases orchestrate domain rules and abstract ``ports`` (Protocols). They
never import a concrete framework, so they can be exercised with fakes and are
unaffected by swapping Presidio, PyMuPDF, or the storage backend.
"""
