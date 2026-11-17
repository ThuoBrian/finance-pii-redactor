"""PDF: Options, scan, Review (words and table columns), page preview, files.

Fixed detection settings (no threshold or kinds to choose); scan once, then every
review change is a rebuild from the cached scan; unticked terms and chosen
columns carry over to a new scan.

Two mapping files, built by two separate functions on purpose:

- the label mapping (``[001] = Internal ID``) has **no names**, so it is
  Internal and can travel with the PDF;
- the mapping with names is Confidential and opt-in. It is only built after
  the user switches it on for this document (``/names-file``), and never in
  black-out style, which has nothing to decode.
"""

from __future__ import annotations

from io import BytesIO
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query, Response

from finance_redactor.application.redact_pdf import (
    LARGE_PDF_PAGES,
    OCR_SECONDS_PER_PAGE,
    RedactionStyle,
)
from finance_redactor.domain.errors import EncryptedPdfError, UnreadableFileError
from finance_redactor.domain.tables import suggested_columns
from finance_redactor.presentation.api.context import (
    Context,
    job_for,
    scanned_state,
    start_or_409,
)
from finance_redactor.presentation.api.review import (
    checked_exclusions,
    checked_words,
    review_parts,
    text_occurrences,
)
from finance_redactor.presentation.jobs import Job, Progress, UserFacingError
from finance_redactor.presentation.presenters import (
    carry_over_exclusions,
    merge_findings,
    not_located_warning,
    pdf_job_size_note,
    pdf_mapping_dataframe,
    pdf_mapping_notes,
    pdf_mapping_with_names_dataframe,
    pdf_review_dataframe,
    plural,
    scanned_pages_warning,
)
from finance_redactor.presentation.schemas import (
    NamesFileIn,
    PdfApplyIn,
    PdfDownloadOut,
    PdfMappingRowOut,
    PdfOptionsOut,
    PdfReviewOut,
    PdfScanIn,
    TableColumnOut,
)

ENCRYPTED = (
    "This PDF is password-protected, so its pages can't be read. Open it in a "
    "PDF reader, enter the password, save an unlocked copy, and upload that "
    "copy instead."
)
UNREADABLE = (
    "This file could not be read as a PDF. It may be corrupted, or not really "
    "a .pdf file despite its name. Open it in a PDF reader, save a fresh "
    "copy, and upload that instead."
)
# Page previews: sharp enough to read, small enough to load quickly.
PREVIEW_DPI = 110

router = APIRouter(prefix="/api/jobs/{job_id}/pdf", tags=["pdf"])


@router.get("/options")
def options(job_id: str, context: Context) -> PdfOptionsOut:
    """Return OCR availability and the job-size notes, counted once per upload."""
    job = job_for(context, job_id, "pdf")
    service = context.pdf_service()
    with job.lock:
        if "job_size" not in job.state:
            try:
                job.state["job_size"] = service.count_scanned_pages(BytesIO(job.data))
            except (EncryptedPdfError, UnreadableFileError):
                # The scan reports this properly; Options just has no size.
                job.state["job_size"] = (0, 0)
        scanned, total = job.state["job_size"]

    def note(reading: bool) -> str:
        return pdf_job_size_note(
            scanned,
            total,
            reading_scans=reading and service.can_read_scans,
            seconds_per_page=OCR_SECONDS_PER_PAGE,
            large_pages=LARGE_PDF_PAGES,
        )

    return PdfOptionsOut(
        can_read_scans=service.can_read_scans,
        total_pages=total,
        size_note_reading=note(True),
        size_note_not_reading=note(False),
    )


def _style(value: str) -> RedactionStyle:
    try:
        return RedactionStyle(value)
    except ValueError:
        raise HTTPException(422, "Unknown redaction style.") from None


@router.post("/scan", status_code=202)
def scan(job_id: str, body: PdfScanIn, context: Context) -> dict[str, str]:
    """Start scanning and building in the background; poll the job for progress."""
    job = job_for(context, job_id, "pdf")
    style = _style(body.style)
    words = checked_words(body.words)

    def work(progress: Progress) -> None:
        service = context.pdf_service()
        fingerprint = context.load_master_list().fingerprint
        with job.lock:
            previous_excluded = job.state.get("applied", frozenset())
            previous_columns = job.state.get("columns", frozenset())
        try:
            result = service.scan(
                BytesIO(job.data), read_scans=body.read_scans, on_progress=progress
            )
            job.task.label = "Building the redacted PDF..."
            # Name-, account- and contact-like columns start chosen, plus any
            # the user added on an earlier run of this file.
            columns = suggested_columns(result.table_columns) | (
                previous_columns & set(result.table_columns)
            )

            def build(exclude: frozenset[str]) -> Any:
                return service.redact(
                    BytesIO(job.data),
                    result,
                    words,
                    style=style,
                    redact_images=body.redact_images,
                    exclude=exclude,
                    columns=columns,
                )

            first = build(frozenset())
            # Back from Review: keep the terms unticked there that this run
            # found again, rather than wiping the review.
            carried = carry_over_exclusions(previous_excluded, first.findings)
            built = build(carried) if carried else first
        except EncryptedPdfError:
            raise UserFacingError(ENCRYPTED) from None
        except UnreadableFileError:
            raise UserFacingError(UNREADABLE) from None
        with job.lock:
            job.state.update(
                scan=result,
                built=built,
                # Unfiltered baseline for the review list (see docx.py).
                all_findings=first.findings,
                applied=carried,
                carried=carried,
                words=words,
                columns=columns,
                style=style,
                redact_images=body.redact_images,
                fingerprint=fingerprint,
                # A new result starts with the names file off.
                names_file=False,
            )

    label = "Scanning the PDF (scanned pages take a few seconds each)..."
    return start_or_409(context, job, label, work)


def _scanned_note(state: dict[str, Any]) -> str:
    result = state["scan"]
    if not result.scanned_pages:
        return ""
    return scanned_pages_warning(
        result.scanned_pages,
        state["built"].page_count,
        state["redact_images"],
        read=result.read_pages,
    )


def _review(state: dict[str, Any]) -> PdfReviewOut:
    built = state["built"]
    all_findings = state["all_findings"]
    blackout = state["style"] == RedactionStyle.BLACKOUT
    rows, _, filters, clean = review_parts(all_findings)
    pages = built.page_count
    summary = (
        f"{plural(len(built.findings), 'match', 'matches')} on {plural(pages, 'page')}"
    )
    if built.removed_links:
        summary += f" · {plural(built.removed_links, 'link target')} removed"
    if not built.findings:
        summary = (
            "No names, emails, websites, addresses, or matching words were "
            f"found across {plural(pages, 'page')}. Any images and link "
            "targets are still removed in the download."
        )
    elif blackout:
        summary += ". Matched areas will be blacked out in the downloaded PDF."
    table_columns = state["scan"].table_columns
    review_table = pdf_review_dataframe(built.crosswalk)
    return PdfReviewOut(
        summary=summary,
        page_count=pages,
        blackout=blackout,
        scanned_note=_scanned_note(state),
        not_located=not_located_warning(built.not_located),
        rows=rows,
        applied=sorted(state["applied"]),
        carried=sorted(state["carried"]),
        words=list(state["words"]),
        table_columns=[
            TableColumnOut(key=k, header=h) for k, h in table_columns.items()
        ],
        columns=sorted(state["columns"]),
        filters=filters,
        clean=clean,
        mapping=(
            []
            if blackout
            else [
                PdfMappingRowOut(
                    label=str(r["Label"]),
                    original_name=str(r["Original name"]),
                    kind=str(r["Entity type"]),
                    internal_id=str(r["Internal ID"]),
                    flagged=str(r["Flagged"]),
                    possible_match=str(r["Possible match"]),
                )
                for r in review_table.to_dict("records")
            ]
        ),
        occurrences=text_occurrences(built.findings),
    )


@router.get("/review")
def review(job_id: str, context: Context) -> PdfReviewOut:
    """Return the Review step's data."""
    return _review(scanned_state(job_for(context, job_id, "pdf")))


@router.post("/apply")
def apply(job_id: str, body: PdfApplyIn, context: Context) -> PdfReviewOut:
    """Rebuild with the review choices. No re-detection and no OCR."""
    job = job_for(context, job_id, "pdf")
    state = scanned_state(job)
    words = checked_words(body.words)
    known = set(state["scan"].table_columns)
    columns = frozenset(body.columns)
    if columns - known:
        raise HTTPException(422, "A chosen table column is not in this PDF.")
    # Only terms already on screen can be unticked; terms a new word or
    # column brings are new, so they cannot be in the request yet.
    excluded = checked_exclusions(body.excluded, state["all_findings"])
    built = context.pdf_service().redact(
        BytesIO(job.data),
        state["scan"],
        words,
        style=state["style"],
        redact_images=state["redact_images"],
        exclude=excluded,
        columns=columns,
    )
    with job.lock:
        job.state.update(
            built=built,
            # A newly chosen column or typed word brings terms the first run
            # never found; add them so each one can still be unticked.
            all_findings=merge_findings(state["all_findings"], built.findings),
            applied=excluded,
            carried=frozenset(),
            words=words,
            columns=columns,
        )
        return _review(dict(job.state))


@router.get("/page", response_class=Response)
def page(
    job_id: str,
    context: Context,
    n: Annotated[int, Query(ge=1)] = 1,
    version: Literal["redacted", "original"] = "redacted",
) -> Response:
    """Return one page (1-based) of the redacted or original PDF as a PNG."""
    job = job_for(context, job_id, "pdf")
    state = scanned_state(job)
    data = state["built"].data if version == "redacted" else job.data
    document = context.pdf_open(BytesIO(data))
    try:
        if n > document.page_count:
            raise HTTPException(422, "That page is not in this PDF.")
        png = document.render_page(n - 1, PREVIEW_DPI)
    finally:
        document.close()
    return Response(content=png, media_type="image/png")


@router.get("/download")
def download_info(job_id: str, context: Context) -> PdfDownloadOut:
    """Return the warnings and notes for the Download step."""
    state = scanned_state(job_for(context, job_id, "pdf"))
    built = state["built"]
    blackout = state["style"] == RedactionStyle.BLACKOUT
    scanned_note = _scanned_note(state)
    notes = [scanned_note] if scanned_note else []
    if not blackout:
        notes += pdf_mapping_notes(built.crosswalk)
    return PdfDownloadOut(
        excluded=sorted(state["applied"]),
        blackout=blackout,
        removed_links=built.removed_links,
        before_share=notes,
        before_share_warn=bool(scanned_note),
        not_located=not_located_warning(built.not_located),
        has_mapping=bool(built.crosswalk) and not blackout,
        bracketed=built.source_bracketed_numbers,
        names_file=bool(state.get("names_file")),
    )


@router.post("/names-file")
def names_file(job_id: str, body: NamesFileIn, context: Context) -> dict[str, bool]:
    """Switch the Confidential names file on or off for this document."""
    job = job_for(context, job_id, "pdf")
    state = scanned_state(job)
    if body.enabled and state["style"] == RedactionStyle.BLACKOUT:
        raise HTTPException(409, "Black out leaves nothing to decode.")
    with job.lock:
        job.state["names_file"] = body.enabled
    return {"enabled": body.enabled}


def pdf_file(job: Job, kind: str) -> tuple[bytes, str, str]:
    """Return ``(bytes, file name, media type)`` for one PDF output.

    ``pdf-mapping`` is names-free (Internal). ``pdf-names`` carries names
    (Confidential), is built by its own function, and only after the user
    switched it on.
    """
    state = scanned_state(job)
    built = state["built"]
    blackout = state["style"] == RedactionStyle.BLACKOUT
    if kind == "redacted":
        name = f"{job.stem}-blackout.pdf" if blackout else f"{job.stem}.pdf"
        return built.data, name, "application/pdf"
    if kind in {"pdf-mapping", "pdf-names"} and (blackout or not built.crosswalk):
        raise HTTPException(404, "Nothing was replaced with a label, so no mapping.")
    if kind == "pdf-mapping":
        table = pdf_mapping_dataframe(built.crosswalk, state["fingerprint"])
        csv = table.to_csv(index=False).encode("utf-8")
        return csv, f"{job.stem}_mapping.csv", "text/csv"
    if kind == "pdf-names":
        if not state.get("names_file"):
            raise HTTPException(409, "Switch on the mapping with names first.")
        table = pdf_mapping_with_names_dataframe(built.crosswalk, state["fingerprint"])
        csv = table.to_csv(index=False).encode("utf-8")
        return csv, f"{job.stem}_crosswalk.csv", "text/csv"
    raise HTTPException(404, "No such file for a PDF upload.")
