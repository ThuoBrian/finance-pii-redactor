"""Finance PII Redactor - Streamlit entry point and composition root.

This file is the single place where concrete adapters are wired into use cases
(dependency injection). It stays thin: configure the page, build the object
graph, route the upload to the right presentation flow. The heavy NLP engine is
built once and cached across reruns; the master-list-derived bundle (parsed
rows, recognizers, detection engine, fuzzy-match candidate index) is cached
alongside it, keyed on the workbook's modification time so edits still take
effect on the next refresh.
"""

from __future__ import annotations

import streamlit as st

from finance_redactor.application.redact_excel import RedactExcelService
from finance_redactor.application.redact_pdf import RedactPdfService
from finance_redactor.config import DEFAULT_SETTINGS
from finance_redactor.domain.pseudonyms import build_candidate_index
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

    @st.cache_resource(show_spinner="Loading master list...")
    def _get_master_list_bundle(_mtime: float | None):
        """Parse the master list and build its detection engine, cached by mtime.

        Keying on the workbook's modification time means identical mtimes
        across reruns (e.g. toggling an unrelated widget) reuse the same
        parsed rows and compiled recognizer patterns instead of redoing the
        ~26k-row parse and regex compilation on every rerun, while a real edit
        to the workbook changes the mtime and busts the cache immediately. The
        fuzzy-match candidate index (``build_candidate_index``) is derived from
        ``master_map`` here too, once, rather than being rebuilt by every
        ``Pseudonymizer`` constructed per file processed.
        """
        repo = MasterListRepository(
            settings.master_list_file,
            settings.categories,
            category_sheets=settings.category_sheets,
        )
        names = repo.names_by_entity()
        recognizers = build_custom_recognizers(
            names.get("PERSON", []),
            names.get("ORGANIZATION", []),
            settings.custom_match_score,
        )
        engine = PresidioEngine(settings, recognizers, nlp_engine=_get_nlp_engine())
        master_map = repo.master_map()
        return (
            engine,
            master_map,
            # Built once per master-list load (see docs/GOTCHA.md): the
            # fuzzy-match candidate pool is otherwise a full pass over every
            # curated name and alias variant, repeated on every file processed.
            build_candidate_index(master_map),
            repo.counts_by_category(),
            repo.quality_report(),
        )

    try:
        master_list_mtime = settings.master_list_file.stat().st_mtime
    except OSError:
        master_list_mtime = None

    engine, master_map, candidates_by_type, name_counts, quality_issues = (
        _get_master_list_bundle(master_list_mtime)
    )

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
                engine,
                master_map,
                settings.auto_prefixes,
                settings.fuzzy_match_threshold,
                candidates_by_type,
            ),
            excel_gateway=OpenpyxlExcelGateway(),
            settings=settings,
            name_counts=name_counts,
            quality_issues=quality_issues,
        )
    elif extension == "pdf":
        run_pdf_flow(
            uploaded,
            pdf_service=RedactPdfService(
                engine,
                PyMuPdfDocument.open,
                master_map,
                settings.auto_prefixes,
                settings.fuzzy_match_threshold,
                candidates_by_type,
            ),
            settings=settings,
            name_counts=name_counts,
            quality_issues=quality_issues,
        )
    else:
        st.error("Unsupported file type. Please upload an Excel or PDF file.")
        st.stop()


from streamlit.runtime.scriptrunner import get_script_run_ctx as _get_ctx  # noqa: E402

if _get_ctx() is not None:
    _main()
