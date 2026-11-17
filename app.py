"""Finance PII Redactor - entry point and composition root.

This file is the single place where concrete adapters are wired into use cases
(dependency injection). ``create_app`` builds the FastAPI app (API plus the
built React interface) around an :class:`AppContext`; ``python app.py`` serves
it on 127.0.0.1 and opens the browser.

The heavy NLP engine loads once per process. The master-list bundle (parsed
rows, recognizers, detection engine) is cached on the workbook's path and
modification time, so an edit or a folder change takes effect on the next
request that needs it.
"""

from __future__ import annotations

import os
import socket
import threading
import webbrowser

from fastapi import FastAPI
from presidio_analyzer.nlp_engine import NlpEngine

from finance_redactor.application.ports import OcrEngine
from finance_redactor.application.redact_docx import RedactDocxService
from finance_redactor.application.redact_excel import RedactExcelService
from finance_redactor.application.redact_pdf import RedactPdfService
from finance_redactor.config import Settings, current_settings
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
from finance_redactor.presentation.api import build_api
from finance_redactor.presentation.api.context import AppContext, MasterListState
from finance_redactor.presentation.jobs import JobStore

# 8501 is Streamlit's old port, kept so bookmarks and docs still work;
# FPR_PORT overrides it.
PORT = int(os.environ.get("FPR_PORT", "8501"))


def _build_master_list_bundle(
    settings: Settings, nlp_engine: NlpEngine, mtime: float | None
) -> MasterListState:
    """Parse the master list and build its detection engine."""
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
    return MasterListState(
        detector=PresidioEngine(settings, recognizers, nlp_engine=nlp_engine),
        master_map=repo.master_map(),
        counts=repo.counts_by_category(),
        issues=repo.quality_report(),
        fingerprint=repo.fingerprint(),
        path=settings.master_list_file,
        mtime=mtime,
    )


def create_app(port: int = PORT) -> FastAPI:
    """Build the web app: wire adapters into the API context.

    The NLP engine loads once per process. The master-list bundle is cached
    on the workbook's path and modification time, and ``refresh_master_list``
    clears it for a Box sync that has not changed the mtime yet.
    """
    lock = threading.Lock()
    cache: dict[str, object] = {}

    nlp: list[NlpEngine] = []

    def nlp_engine() -> NlpEngine:
        if not nlp:
            nlp.append(PresidioEngine._create_nlp_engine(current_settings()))
        return nlp[0]

    def load_master_list() -> MasterListState:
        settings = current_settings()
        path = settings.master_list_file
        try:
            mtime: float | None = path.stat().st_mtime
        except OSError:
            mtime = None
        with lock:
            if cache.get("key") != (str(path), mtime):
                cache["state"] = _build_master_list_bundle(
                    settings, nlp_engine(), mtime
                )
                cache["key"] = (str(path), mtime)
            state = cache["state"]
            assert isinstance(state, MasterListState)
            return state

    ocr: list[OcrEngine | None] = []

    def ocr_engine() -> OcrEngine | None:
        # Optional: scans are reported but not read when OCR is missing. The
        # model itself loads on first use.
        if not ocr:
            try:
                from finance_redactor.infrastructure.ocr.rapid_ocr import (
                    RapidOcrEngine,
                )
            except ImportError:
                ocr.append(None)
            else:
                ocr.append(RapidOcrEngine())
        return ocr[0]

    def refresh_master_list() -> None:
        with lock:
            cache.pop("key", None)
            cache.pop("state", None)

    def shutdown() -> None:
        # os._exit: uvicorn would otherwise wait on open connections. The
        # delay gives the "closing" response time to reach the browser.
        threading.Timer(0.5, os._exit, args=(0,)).start()

    context = AppContext(
        load_master_list=load_master_list,
        refresh_master_list=refresh_master_list,
        jobs=JobStore(),
        shutdown=shutdown,
        settings=current_settings,
        excel_gateway=OpenpyxlExcelGateway(),
        excel_service=lambda: _excel_service(current_settings(), load_master_list()),
        docx_service=lambda: _docx_service(current_settings(), load_master_list()),
        pdf_service=lambda: _pdf_service(
            current_settings(), load_master_list(), ocr_engine()
        ),
        pdf_open=PyMuPdfDocument.open,
    )
    return build_api(context, port=port)


def _excel_service(settings: Settings, state: MasterListState) -> RedactExcelService:
    """Build the Excel use case on the current master list."""
    return RedactExcelService(
        state.detector,
        state.master_map,
        settings.auto_prefixes,
        settings.fuzzy_match_threshold,
        fixed_masks=settings.fixed_masks,
    )


def _docx_service(settings: Settings, state: MasterListState) -> RedactDocxService:
    """Build the Word use case on the current master list."""
    return RedactDocxService(
        state.detector,
        PythonDocxDocument.open,
        state.master_map,
        settings.auto_prefixes,
        settings.fuzzy_match_threshold,
        settings.custom_words_score,
        fixed_masks=settings.fixed_masks,
    )


def _pdf_service(
    settings: Settings, state: MasterListState, ocr: OcrEngine | None
) -> RedactPdfService:
    """Build the PDF use case on the current master list."""
    return RedactPdfService(
        PyMuPdfDocument.open,
        state.master_map,
        settings.auto_prefixes,
        state.detector,
        settings.fuzzy_match_threshold,
        settings.custom_words_score,
        fixed_masks=settings.fixed_masks,
        ocr=ocr,
    )


def _serve() -> None:
    """Start the web app on 127.0.0.1 and open it in the browser."""
    import uvicorn

    with socket.socket() as probe:
        try:
            probe.bind(("127.0.0.1", PORT))
        except OSError:
            print(
                f"Port {PORT} is already in use. The app may already be open: "
                f"try http://127.0.0.1:{PORT}/ in your browser, or close the "
                "other window first.",
                flush=True,
            )
            raise SystemExit(1) from None
    app = create_app()
    # Warm the NLP model and master list while the browser opens.
    threading.Thread(target=app.state.context.load_master_list, daemon=True).start()
    url = f"http://127.0.0.1:{PORT}/"
    print(
        f"Finance PII Redactor is running at {url} - keep this window open.",
        flush=True,
    )
    threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    _serve()
