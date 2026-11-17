"""Word: Options, scan, Review (with typed words), and the files to download.

Pseudonymize only, no blackout; scan once, then every review change is a
rebuild from the cached scan (typed words are matched during the rebuild, so
adding one never re-runs detection); unticked terms carry over to a new scan
when it finds them again; the crosswalk leaves as its own CSV.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any

from fastapi import APIRouter, HTTPException

from finance_redactor.domain.errors import UnreadableFileError
from finance_redactor.presentation.api.context import (
    Context,
    job_for,
    scanned_state,
    start_or_409,
)
from finance_redactor.presentation.api.review import (
    checked_detection,
    checked_exclusions,
    checked_words,
    crosswalk_csv,
    entity_options,
    mapping_rows,
    review_parts,
    text_occurrences,
    threshold_options,
)
from finance_redactor.presentation.jobs import Job, Progress, UserFacingError
from finance_redactor.presentation.presenters import (
    carry_over_exclusions,
    merge_findings,
    plural,
)
from finance_redactor.presentation.schemas import (
    DetectionOptionsOut,
    DocxDownloadOut,
    DocxReviewOut,
    DocxScanIn,
    WordsApplyIn,
)

UNREADABLE = (
    "This file could not be read as a Word document. It may be corrupted, or "
    "not really a .docx file despite its name. Open it in Word, save a fresh "
    "copy, and upload that instead."
)
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

router = APIRouter(prefix="/api/jobs/{job_id}/docx", tags=["docx"])


@router.get("/options")
def options(job_id: str, context: Context) -> DetectionOptionsOut:
    """Return the confidence slider and the kinds of information to hide."""
    job_for(context, job_id, "docx")
    settings = context.settings()
    entities, entity_help = entity_options(settings)
    return DetectionOptionsOut(
        threshold=threshold_options(settings),
        entities=entities,
        entity_help=entity_help,
    )


@router.post("/scan", status_code=202)
def scan(job_id: str, body: DocxScanIn, context: Context) -> dict[str, str]:
    """Start scanning and rebuilding in the background; poll the job for progress."""
    job = job_for(context, job_id, "docx")
    entities = checked_detection(context.settings(), body.entities, body.threshold)
    words = checked_words(body.words)

    def work(progress: Progress) -> None:
        service = context.docx_service()
        try:
            result = service.scan(
                BytesIO(job.data), entities, body.threshold, on_progress=progress
            )
            job.task.label = "Replacing names with codes..."
            first = service.redact(BytesIO(job.data), result, words)
            with job.lock:
                previous = job.state.get("applied", frozenset())
            # Back from Review: keep the terms unticked there that this run
            # found again, rather than wiping the review.
            carried = carry_over_exclusions(previous, first.findings)
            built = (
                service.redact(BytesIO(job.data), result, words, exclude=carried)
                if carried
                else first
            )
        except UnreadableFileError:
            raise UserFacingError(UNREADABLE) from None
        with job.lock:
            job.state.update(
                scan=result,
                built=built,
                # Unfiltered baseline for the review list: a term unticked
                # and rebuilt away must keep its row so it can be re-ticked.
                all_findings=first.findings,
                applied=carried,
                carried=carried,
                words=words,
            )

    return start_or_409(context, job, "Scanning the document...", work)


def _review(state: dict[str, Any]) -> DocxReviewOut:
    built = state["built"]
    all_findings = state["all_findings"]
    rows, summary, filters, clean = review_parts(all_findings)
    links = built.removed_links
    if not summary:
        summary = "Nothing was detected in the text."
    if links:
        summary += f" {plural(links, 'hyperlink target')} removed."
    return DocxReviewOut(
        summary=summary,
        rows=rows,
        applied=sorted(state["applied"]),
        carried=sorted(state["carried"]),
        words=list(state["words"]),
        filters=filters,
        clean=clean,
        mapping=mapping_rows(built.crosswalk),
        occurrences=text_occurrences(built.findings),
    )


@router.get("/review")
def review(job_id: str, context: Context) -> DocxReviewOut:
    """Return the Review step's data."""
    return _review(scanned_state(job_for(context, job_id, "docx")))


@router.post("/apply")
def apply(job_id: str, body: WordsApplyIn, context: Context) -> DocxReviewOut:
    """Rebuild with the review choices. No re-detection: a pass over the scan."""
    job = job_for(context, job_id, "docx")
    state = scanned_state(job)
    words = checked_words(body.words)
    # Only terms already on screen can be unticked; a newly typed word's
    # terms are new, so they cannot be in the request yet.
    excluded = checked_exclusions(body.excluded, state["all_findings"])
    built = context.docx_service().redact(
        BytesIO(job.data), state["scan"], words, exclude=excluded
    )
    # A newly typed word brings terms the first run never found; add them so
    # each one can still be unticked.
    all_findings = merge_findings(state["all_findings"], built.findings)
    with job.lock:
        job.state.update(
            built=built,
            all_findings=all_findings,
            applied=excluded,
            carried=frozenset(),
            words=words,
        )
        return _review(dict(job.state))


@router.get("/download")
def download_info(job_id: str, context: Context) -> DocxDownloadOut:
    """Return the warnings and notes for the Download step."""
    state = scanned_state(job_for(context, job_id, "docx"))
    built = state["built"]
    return DocxDownloadOut(
        excluded=sorted(state["applied"]),
        removed_links=built.removed_links,
        has_mapping=bool(built.crosswalk),
    )


def docx_file(job: Job, kind: str) -> tuple[bytes, str, str]:
    """Return ``(bytes, file name, media type)`` for ``redacted`` or ``crosswalk``.

    The crosswalk holds real names, so it only ever leaves as its own CSV.
    """
    state = scanned_state(job)
    built = state["built"]
    if kind == "redacted":
        return built.data, f"{job.stem}.docx", DOCX_TYPE
    if kind == "crosswalk":
        return crosswalk_csv(job.stem, built.crosswalk)
    raise HTTPException(404, "No such file for a Word upload.")
