"""Finance PII Redactor - Streamlit entry point and composition root.

This file is the single place where concrete adapters are wired into use cases
(dependency injection). It stays thin: configure the page, build the object
graph, route the upload to the right presentation flow. The heavy NLP engine is
built once and cached across reruns.
"""

from __future__ import annotations

import streamlit as st

from finance_redactor.application.redact_excel import RedactExcelService
from finance_redactor.application.redact_pdf import RedactPdfService
from finance_redactor.config import DEFAULT_SETTINGS
from finance_redactor.infrastructure.detection.custom_recognizer import (
    build_custom_recognizers,
)
from finance_redactor.infrastructure.detection.presidio_detector import PresidioEngine
from finance_redactor.infrastructure.documents.excel_gateway import (
    OpenpyxlExcelGateway,
)
from finance_redactor.infrastructure.documents.pdf_gateway import PyMuPdfDocument
from finance_redactor.infrastructure.names.master_list_repository import (
    MasterListRepository,
)
from finance_redactor.presentation.excel_view import run_excel_flow
from finance_redactor.presentation.pdf_view import run_pdf_flow


def _main() -> None:
    """Run the Streamlit UI. Called only when executed via streamlit run."""
    settings = DEFAULT_SETTINGS

    @st.cache_resource(show_spinner="Loading NLP model (first run only)...")
    def _get_nlp_engine():
        """Load the heavy spaCy model once and reuse it across reruns."""
        return PresidioEngine._create_nlp_engine(settings)

    # The master list is lightweight and user-editable: reload it on every rerun
    # so edits to data/Names List - Organized.xlsx take effect without a server
    # restart.
    repo = MasterListRepository(settings.master_list_file, settings.categories)
    names = repo.names_by_entity()
    recognizers = build_custom_recognizers(
        names.get("PERSON", []),
        names.get("ORGANIZATION", []),
        settings.custom_match_score,
    )
    engine = PresidioEngine(settings, recognizers, nlp_engine=_get_nlp_engine())

    master_map = repo.master_map()
    name_counts = repo.counts_by_category()

    st.set_page_config(
        page_title="Finance PII Redactor", page_icon=":shield:", layout="wide"
    )
    st.title("Finance PII Redactor")
    st.caption(
        "Upload an Excel or PDF file, choose what to pseudonymize, and download a "
        "copy with names replaced by stable IDs (e.g. STF-91345). "
        "All processing happens locally — no data leaves your laptop."
    )

    uploaded = st.file_uploader(
        "Upload a file (.xlsx, .xls, or .pdf)",
        type=["xlsx", "xls", "pdf"],
        help="The file is processed entirely on your machine.",
    )

    if uploaded is None:
        st.info("Upload a file above to get started.")
        st.stop()

    extension = uploaded.name.rsplit(".", 1)[-1].lower()

    if extension in {"xlsx", "xls"}:
        run_excel_flow(
            uploaded,
            excel_service=RedactExcelService(
                engine, master_map, settings.auto_prefixes
            ),
            excel_gateway=OpenpyxlExcelGateway(),
            settings=settings,
            name_counts=name_counts,
        )
    elif extension == "pdf":
        run_pdf_flow(
            uploaded,
            pdf_service=RedactPdfService(
                engine, PyMuPdfDocument.open, master_map, settings.auto_prefixes
            ),
            settings=settings,
            name_counts=name_counts,
        )
    else:
        st.error("Unsupported file type. Please upload an Excel or PDF file.")
        st.stop()


from streamlit.runtime.scriptrunner import get_script_run_ctx as _get_ctx  # noqa: E402

if _get_ctx() is not None:
    _main()
