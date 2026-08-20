"""Finance PII Redactor - Streamlit entry point and composition root.

This file is the single place where concrete adapters are wired into use cases
(dependency injection). It stays thin: configure the page, build the object
graph, route the upload to the right presentation flow. The heavy NLP engine is
built once and cached across reruns; the master-list-derived bundle (parsed
rows, recognizers, detection engine) is cached alongside it, keyed on the
workbook's modification time so edits still take effect on the next refresh.
"""

from __future__ import annotations

import streamlit as st

from finance_redactor.application.redact_docx import RedactDocxService
from finance_redactor.application.redact_excel import RedactExcelService
from finance_redactor.application.redact_pdf import RedactPdfService
from finance_redactor.config import current_settings
from finance_redactor.infrastructure.detection.custom_recognizer import (
    build_custom_recognizers,
)
from finance_redactor.infrastructure.detection.presidio_detector import PresidioEngine
from finance_redactor.infrastructure.documents.docx_gateway import PythonDocxDocument
from finance_redactor.infrastructure.documents.excel_gateway import (
    OpenpyxlExcelGateway,
)
from finance_redactor.infrastructure.documents.pdf_gateway import PyMuPdfDocument
from finance_redactor.infrastructure.names.master_list_repository import (
    MasterListRepository,
)
from finance_redactor.presentation.docx_view import run_docx_flow
from finance_redactor.presentation.excel_view import run_excel_flow
from finance_redactor.presentation.master_list_setup import (
    render_master_list_setup_dialog,
)
from finance_redactor.presentation.pdf_view import run_pdf_flow


def _main() -> None:
    """Run the Streamlit UI. Called only when executed via streamlit run."""
    # Must be the very first Streamlit command in the script - anything that
    # renders before it (the master-list-setup dialog below, or even a
    # cache_resource spinner on a cold cache) would otherwise raise.
    st.set_page_config(
        page_title="Finance PII Redactor", page_icon=":shield:", layout="wide"
    )

    # Re-resolved fresh (not DEFAULT_SETTINGS) so a folder saved via the in-app
    # "Set up shared master list" dialog takes effect on the next rerun - see
    # current_settings()'s docstring.
    settings = current_settings()

    @st.cache_resource(show_spinner="Loading NLP model (first run only)...")
    def _get_nlp_engine():
        """Load the heavy spaCy model once and reuse it across reruns."""
        return PresidioEngine._create_nlp_engine(settings)

    @st.cache_resource(show_spinner="Loading master list...")
    def _get_master_list_bundle(_path: str, _mtime: float | None):
        """Parse the master list and build its detection engine, cached by path+mtime.

        Keying on the workbook's path and modification time means identical
        reruns (e.g. toggling an unrelated widget) reuse the same parsed rows
        and compiled recognizer patterns instead of redoing the ~26k-row parse
        and regex compilation every time, while a real edit to the workbook -
        or the master-list folder changing (e.g. via the "Set up shared
        master list" dialog) - busts the cache immediately. ``_path`` alone
        would already change on a folder switch, but including both makes the
        key robust even in the unlikely case two different files share an
        mtime.
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
        return (
            engine,
            repo.master_map(),
            repo.counts_by_category(),
            repo.quality_report(),
        )

    try:
        master_list_mtime = settings.master_list_file.stat().st_mtime
    except OSError:
        master_list_mtime = None

    engine, master_map, name_counts, quality_issues = _get_master_list_bundle(
        str(settings.master_list_file), master_list_mtime
    )

    # A brand-new install (or one whose FPR_MASTER_LIST_DIR/persisted setting
    # is missing, wrong, or not yet synced) loads 0 names - offer the in-app
    # setup dialog right away instead of leaving the user to discover
    # data/README.md's manual env-var steps on their own. Dismissible per
    # session (via the dialog's own buttons) so it doesn't reappear on every
    # rerun for someone who intentionally isn't using a shared list.
    if sum(name_counts.values()) == 0 and not st.session_state.get(
        "master_list_setup_dismissed", False
    ):
        render_master_list_setup_dialog(settings.names_dir)

    st.title("Finance PII Redactor")
    st.caption(
        "Upload an Excel, PDF, or Word file, choose what to pseudonymize, and "
        "download a copy with names replaced by stable IDs (e.g. STF-91345). "
        "All processing happens locally — no data leaves your laptop."
    )

    uploaded = st.file_uploader(
        "Upload a file (.xlsx, .xls, .pdf, or .docx)",
        type=["xlsx", "xls", "pdf", "docx"],
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
            ),
            settings=settings,
            name_counts=name_counts,
            quality_issues=quality_issues,
        )
    elif extension == "docx":
        run_docx_flow(
            uploaded,
            docx_service=RedactDocxService(
                engine,
                PythonDocxDocument.open,
                master_map,
                settings.auto_prefixes,
                settings.fuzzy_match_threshold,
            ),
            settings=settings,
            name_counts=name_counts,
            quality_issues=quality_issues,
        )
    else:
        st.error("Unsupported file type. Please upload an Excel, PDF, or Word file.")
        st.stop()


from streamlit.runtime.scriptrunner import get_script_run_ctx as _get_ctx  # noqa: E402

if _get_ctx() is not None:
    _main()
