"""What the routers need from the composition root.

``app.py`` builds one :class:`AppContext` with the concrete adapters wired in
and hands it to :func:`finance_redactor.presentation.api.build_api`. Routers
reach it through :func:`get_context`, so they never import infrastructure and
tests can pass fakes.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request

from finance_redactor.application.ports import (
    ExcelGateway,
    PdfDocumentFactory,
    PiiDetector,
)
from finance_redactor.application.redact_docx import RedactDocxService
from finance_redactor.application.redact_excel import RedactExcelService
from finance_redactor.application.redact_pdf import RedactPdfService
from finance_redactor.config import Settings
from finance_redactor.domain.pseudonyms import MasterEntry
from finance_redactor.domain.quality import QualityIssue
from finance_redactor.presentation.jobs import Job, JobStore, Progress


@dataclass(frozen=True)
class MasterListState:
    """The loaded master list and the detector built from it."""

    detector: PiiDetector
    master_map: Mapping[tuple[str, str], MasterEntry]
    counts: Mapping[str, int]
    issues: Sequence[QualityIssue]
    fingerprint: str
    path: Path
    mtime: float | None


@dataclass(frozen=True)
class AppContext:
    """Callables and state the routers share.

    ``load_master_list`` returns the cached bundle (rebuilt when the
    workbook's path or modification time changes); ``refresh_master_list``
    clears that cache outright.
    ``excel_service``, ``docx_service`` and ``pdf_service`` build the use
    cases on the current master list; the composition root owns that wiring.
    ``pdf_open`` opens a PDF, for the page preview.
    """

    load_master_list: Callable[[], MasterListState]
    refresh_master_list: Callable[[], None]
    jobs: JobStore
    shutdown: Callable[[], None]
    settings: Callable[[], Settings]
    excel_gateway: ExcelGateway
    excel_service: Callable[[], RedactExcelService]
    docx_service: Callable[[], RedactDocxService]
    pdf_service: Callable[[], RedactPdfService]
    pdf_open: PdfDocumentFactory


def get_context(request: Request) -> AppContext:
    """FastAPI dependency: the context ``build_api`` stored on the app."""
    context: AppContext = request.app.state.context
    return context


Context = Annotated[AppContext, Depends(get_context)]

GONE = "That file is no longer open. Upload it again."
BUSY = "Still working on this file. Wait for it to finish."


def job_for(
    context: AppContext, job_id: str, fmt: str | None = None, *, idle: bool = True
) -> Job:
    """Return the job, 404 if unknown or another format, 409 if busy and ``idle``."""
    job = context.jobs.get(job_id)
    if job is None or (fmt is not None and job.format != fmt):
        raise HTTPException(404, GONE)
    if idle and job.task.status == "running":
        raise HTTPException(409, BUSY)
    return job


def scanned_state(job: Job) -> dict[str, Any]:
    """Return a snapshot of the job's state, 409 if it has not been scanned."""
    with job.lock:
        if "scan" not in job.state:
            raise HTTPException(409, "This file has not been scanned yet.")
        return dict(job.state)


def start_or_409(
    context: AppContext, job: Job, label: str, work: Callable[[Progress], None]
) -> dict[str, str]:
    """Start the job's background task, or 409 if one is already running."""
    if not context.jobs.start_task(job, label, work):
        raise HTTPException(409, BUSY)
    return {"status": "running"}
