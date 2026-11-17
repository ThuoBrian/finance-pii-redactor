"""A fake composition root for the web API tests.

No NLP model or real master list loads. The detector flags fixed, made-up
terms, and background tasks run inline so tests are deterministic.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from fastapi.testclient import TestClient

from finance_redactor.application.redact_docx import RedactDocxService
from finance_redactor.application.redact_excel import RedactExcelService
from finance_redactor.application.redact_pdf import RedactPdfService
from finance_redactor.config import DEFAULT_SETTINGS
from finance_redactor.domain.entities import DetectionSource, PiiDetection, Span
from finance_redactor.domain.quality import QualityIssue
from finance_redactor.infrastructure.documents.docx_gateway import PythonDocxDocument
from finance_redactor.infrastructure.documents.excel_gateway import (
    OpenpyxlExcelGateway,
)
from finance_redactor.infrastructure.documents.pdf_gateway import PyMuPdfDocument
from finance_redactor.presentation.api import build_api
from finance_redactor.presentation.api.context import AppContext, MasterListState
from finance_redactor.presentation.jobs import JobStore

PORT = 8501
BASE = f"http://127.0.0.1:{PORT}"
HEADERS = {"X-FPR-Client": "1"}

# Made-up terms the fake detector flags, with their kind and source.
TERMS = {
    "Jane Doe": ("PERSON", DetectionSource.MASTER_LIST),
    "Acme Widgets": ("ORGANIZATION", DetectionSource.MODEL),
    "salaries": ("ORGANIZATION", DetectionSource.MODEL),
}


class FakeDetector:
    """Flags every occurrence of the terms in :data:`TERMS`."""

    def __init__(self, on_analyze: Callable[[], None] | None = None) -> None:
        """Optionally call ``on_analyze`` before each text (e.g. to cancel)."""
        self._on_analyze = on_analyze

    def analyze(
        self, text: str, entities: list[str], threshold: float
    ) -> list[PiiDetection]:
        """Return a detection for each known term found in ``text``."""
        if self._on_analyze is not None:
            self._on_analyze()
        found = []
        for term, (kind, source) in TERMS.items():
            start = text.find(term)
            if start >= 0 and kind in entities:
                found.append(
                    PiiDetection(
                        kind, Span(start, start + len(term)), 0.9, term, source
                    )
                )
        return found


class Fake:
    """Records what the API asked of the composition root."""

    def __init__(self, tmp_path: Path, counts: dict[str, int]) -> None:
        """Start with the given category counts."""
        self.counts = counts
        self.refreshed = 0
        self.shut_down = 0
        self.jobs = JobStore(spawn=lambda run: run())
        self.path = tmp_path / "Names List - Organized.xlsx"
        # Called before the detector reads each text; tests set it.
        self.on_analyze: Callable[[], None] | None = None

    def load(self) -> MasterListState:
        """Return a master list with one quality issue."""
        return MasterListState(
            detector=FakeDetector(),
            master_map={},
            counts=self.counts,
            issues=[
                QualityIssue(
                    kind="dup",
                    severity="warning",
                    title="Duplicate names",
                    detail="Same name twice.",
                    examples=["Alex Sample"],
                    total=3,
                )
            ],
            fingerprint="abc",
            path=self.path,
            mtime=None,
        )

    def refresh(self) -> None:
        """Count refreshes."""
        self.refreshed += 1

    def shutdown(self) -> None:
        """Count shutdowns."""
        self.shut_down += 1

    def excel_service(self) -> RedactExcelService:
        """Return the real Excel use case on the fake detector."""
        return RedactExcelService(
            FakeDetector(lambda: self.on_analyze and self.on_analyze()),
            {},
            DEFAULT_SETTINGS.auto_prefixes,
            fixed_masks=DEFAULT_SETTINGS.fixed_masks,
        )

    def docx_service(self) -> RedactDocxService:
        """Return the real Word use case on the fake detector."""
        return RedactDocxService(
            FakeDetector(lambda: self.on_analyze and self.on_analyze()),
            PythonDocxDocument.open,
            {},
            DEFAULT_SETTINGS.auto_prefixes,
            custom_words_score=DEFAULT_SETTINGS.custom_words_score,
            fixed_masks=DEFAULT_SETTINGS.fixed_masks,
        )

    def pdf_service(self) -> RedactPdfService:
        """Return the real PDF use case on the fake detector, without OCR."""
        return RedactPdfService(
            PyMuPdfDocument.open,
            {},
            DEFAULT_SETTINGS.auto_prefixes,
            FakeDetector(lambda: self.on_analyze and self.on_analyze()),
            custom_words_score=DEFAULT_SETTINGS.custom_words_score,
            fixed_masks=DEFAULT_SETTINGS.fixed_masks,
        )

    def context(self) -> AppContext:
        """Return an AppContext backed by this fake."""
        return AppContext(
            load_master_list=self.load,
            refresh_master_list=self.refresh,
            jobs=self.jobs,
            shutdown=self.shutdown,
            settings=lambda: DEFAULT_SETTINGS,
            excel_gateway=OpenpyxlExcelGateway(),
            # Looked up per call, so a test can swap in a failing one.
            excel_service=lambda: self.excel_service(),
            docx_service=lambda: self.docx_service(),
            pdf_service=lambda: self.pdf_service(),
            pdf_open=PyMuPdfDocument.open,
        )


def make_client(
    tmp_path: Path, counts: dict[str, int] | None = None, static_dir: Path | None = None
) -> tuple[TestClient, Fake]:
    """Return a test client on 127.0.0.1:8501 and the fake behind it."""
    fake = Fake(tmp_path, {"Staff": 2} if counts is None else counts)
    app = build_api(
        fake.context(), port=PORT, static_dir=static_dir or tmp_path / "no-bundle"
    )
    return TestClient(app, base_url=BASE), fake
