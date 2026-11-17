"""Upload a file and start over.

Scan, review and download endpoints for each format are added on top of the
job created here.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, UploadFile

from finance_redactor.presentation.api.context import Context, job_for
from finance_redactor.presentation.jobs import file_format
from finance_redactor.presentation.schemas import JobOut, JobStatusOut, TaskOut

# 200 MB: generous for a spreadsheet, PDF or Word file, small enough to hold
# in memory.
MAX_UPLOAD_BYTES = 200 * 1024 * 1024

# xlsx and docx are zip containers; a PDF starts with its version marker.
_MAGIC = {"excel": b"PK\x03\x04", "docx": b"PK\x03\x04", "pdf": b"%PDF-"}

UNSUPPORTED = (
    "Unsupported file type. Please upload an Excel (.xlsx), PDF, or Word file. "
    "An older .xls workbook can be re-saved as .xlsx from Excel."
)

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("", status_code=201)
async def upload(file: UploadFile, context: Context) -> JobOut:
    """Store an upload as a new job, replacing any earlier one."""
    fmt = file_format(file.filename or "")
    if fmt is None:
        raise HTTPException(415, UNSUPPORTED)
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "The file is larger than 200 MB.")
    if not data.startswith(_MAGIC[fmt]):
        raise HTTPException(
            415, "This file's contents don't match its extension. Is it damaged?"
        )
    job = context.jobs.create(file.filename or "", data, fmt)
    return JobOut(id=job.id, filename=job.filename, format=job.format, size=len(data))


@router.get("/{job_id}")
def job_status(job_id: str, context: Context) -> JobStatusOut:
    """Return the upload and its background task, polled while a scan runs."""
    job = job_for(context, job_id, idle=False)
    task = job.task
    return JobStatusOut(
        id=job.id,
        filename=job.filename,
        format=job.format,
        size=len(job.data),
        task=TaskOut(
            status=task.status,
            label=task.label,
            done=task.done,
            total=task.total,
            error=task.error,
        ),
    )


@router.post("/{job_id}/cancel")
def cancel(job_id: str, context: Context) -> dict[str, bool]:
    """Ask a running scan to stop at its next step. Harmless when idle."""
    job = job_for(context, job_id, idle=False)
    return {"cancelling": context.jobs.cancel(job)}


@router.delete("/{job_id}", status_code=204)
def start_over(job_id: str, context: Context) -> Response:
    """Drop the job and everything built from it."""
    context.jobs.delete(job_id)
    # 204 even for an unknown id: the job is gone either way.
    return Response(status_code=204)
