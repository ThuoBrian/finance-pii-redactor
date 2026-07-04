"""Infrastructure layer: concrete adapters for external libraries and I/O.

Everything that imports Presidio, PyMuPDF, openpyxl, or the filesystem lives
here and nowhere else. Each adapter implements an application ``port`` so it can
be swapped without touching the use cases.
"""
