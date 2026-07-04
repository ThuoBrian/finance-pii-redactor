"""Presentation layer: Streamlit flows and view formatting.

The only layer that imports Streamlit. View functions call use cases and render
their results; ``presenters`` turn domain results into UI artifacts (HTML, the
findings tables).
"""

from finance_redactor.presentation.excel_view import run_excel_flow
from finance_redactor.presentation.pdf_view import run_pdf_flow

__all__ = ["run_excel_flow", "run_pdf_flow"]
