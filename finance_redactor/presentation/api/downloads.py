"""File downloads for every format.

Names come from the job's neutral stem (``redacted-YYYYMMDD-HHMM``), never
from the upload's own name, which can be a person's or a vendor's.
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from finance_redactor.presentation.api import docx, excel, pdf
from finance_redactor.presentation.api.context import Context, job_for

router = APIRouter(prefix="/api/jobs/{job_id}/files", tags=["files"])


@router.get("/{kind}")
def download(job_id: str, kind: str, context: Context) -> Response:
    """Return one output file as an attachment."""
    job = job_for(context, job_id)
    if job.format == "excel":
        data, filename, media_type = excel.excel_file(job, context, kind)
    elif job.format == "docx":
        data, filename, media_type = docx.docx_file(job, kind)
    else:
        data, filename, media_type = pdf.pdf_file(job, kind)
    return Response(
        content=data,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
