"""Excel: Options, scan, Review, preview and the files to download.

Scan and redact are separate, so applying review choices never re-runs
detection; unticked terms carry over to a new scan when it finds them again;
the crosswalk never goes inside the workbook.

Columns are addressed by position, not label: pandas labels can be numbers
or dates, and a position survives the round trip through JSON unchanged.
"""

from __future__ import annotations

from io import BytesIO
from typing import Annotated, Any, cast

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from finance_redactor.application.redact_excel import HEADER_ROW
from finance_redactor.domain.errors import UnreadableFileError
from finance_redactor.presentation.api.context import (
    AppContext,
    Context,
    job_for,
    scanned_state,
    start_or_409,
)
from finance_redactor.presentation.api.review import (
    checked_detection,
    checked_exclusions,
    crosswalk_csv,
    entity_options,
    mapping_rows,
    review_parts,
    threshold_options,
)
from finance_redactor.presentation.jobs import Job, Progress
from finance_redactor.presentation.presenters import (
    HEADER_LABEL,
    PREVIEW_MAX_ROWS,
    TAB_NAME_LABEL,
    carry_over_exclusions,
    excel_findings_dataframe,
    formatting_note,
    name_summary,
    plural,
    scan_result_findings,
    scan_size_warning,
    term_key,
)
from finance_redactor.presentation.schemas import (
    EstimateOut,
    ExcelDownloadOut,
    ExcelOptionsOut,
    ExcelPreviewOut,
    ExcelReviewOut,
    ExcelScanIn,
    ExcelSelectionIn,
    ExcelTabOut,
    ExcludeIn,
    OccurrenceOut,
)

UNREADABLE = (
    "This file could not be read as an Excel workbook. It may be corrupted, "
    "or not really an .xlsx file despite its name. Open it in Excel, save a "
    "fresh copy, and upload that instead."
)
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

router = APIRouter(prefix="/api/jobs/{job_id}/excel", tags=["excel"])


def _sheets(job: Job, context: AppContext) -> dict[str, pd.DataFrame]:
    """Return the workbook's tabs, read once per upload."""
    with job.lock:
        if "sheets" not in job.state:
            try:
                job.state["sheets"] = context.excel_gateway.read_sheets(
                    BytesIO(job.data)
                )
            except UnreadableFileError:
                raise HTTPException(422, UNREADABLE) from None
            job.state["formats"] = context.excel_gateway.read_formatting(
                BytesIO(job.data)
            )
        sheets: dict[str, pd.DataFrame] = job.state["sheets"]
        return sheets


def _selection(
    sheets: dict[str, pd.DataFrame], body: ExcelSelectionIn
) -> tuple[list[str], dict[str, list[Any]]]:
    """Validate the chosen tabs and column positions; return labels per tab."""
    tabs = [t for t in dict.fromkeys(body.tabs)]
    if not tabs:
        raise HTTPException(422, "Choose at least one tab to scan.")
    unknown = [t for t in tabs if t not in sheets]
    if unknown:
        raise HTTPException(422, "A chosen tab is not in this workbook.")
    columns: dict[str, list[Any]] = {}
    for tab in tabs:
        labels = list(sheets[tab].columns)
        positions = body.columns.get(tab, [])
        if any(not 0 <= p < len(labels) for p in positions):
            raise HTTPException(422, "A chosen column is not in this tab.")
        columns[tab] = [labels[p] for p in dict.fromkeys(positions)]
    if not any(columns.values()):
        raise HTTPException(422, "Choose at least one column to scan.")
    return tabs, columns


def _text(value: object) -> str:
    """Return a cell as the preview shows it: blank if empty, else its text."""
    if isinstance(value, str):
        return value
    # A cell is a scalar; Any picks the scalar overload of isna.
    return "" if value is None or pd.isna(cast(Any, value)) else str(value)


@router.get("/options")
def options(job_id: str, context: Context) -> ExcelOptionsOut:
    """Tabs and columns (text columns pre-picked), threshold and kinds."""
    job = job_for(context, job_id, "excel")
    sheets = _sheets(job, context)
    settings = context.settings()
    entities, entity_help = entity_options(settings)
    tab_names = list(sheets)
    n_rows = sum(len(df) for df in sheets.values())
    return ExcelOptionsOut(
        tabs=[
            ExcelTabOut(
                name=name,
                columns=[str(c) for c in df.columns],
                default_columns=[
                    i
                    for i, c in enumerate(df.columns)
                    if c in set(context.excel_gateway.text_columns(df))
                ],
            )
            for name, df in sheets.items()
        ],
        summary=(
            f"{plural(len(tab_names), 'tab')} ({name_summary(tab_names)}) · "
            f"{plural(n_rows, 'row')} · text columns are picked for you"
        ),
        threshold=threshold_options(settings),
        entities=entities,
        entity_help=entity_help,
    )


@router.post("/estimate")
def estimate(job_id: str, body: ExcelSelectionIn, context: Context) -> EstimateOut:
    """Warn before a scan that will take minutes or a lot of memory."""
    job = job_for(context, job_id, "excel")
    sheets = _sheets(job, context)
    tabs, columns = _selection(sheets, body)
    return EstimateOut(warning=scan_size_warning({t: sheets[t] for t in tabs}, columns))


@router.post("/scan", status_code=202)
def scan(job_id: str, body: ExcelScanIn, context: Context) -> dict[str, str]:
    """Start scanning and redacting in the background; poll the job for progress."""
    job = job_for(context, job_id, "excel")
    sheets = _sheets(job, context)
    tabs, columns = _selection(sheets, body)
    entities = checked_detection(context.settings(), body.entities, body.threshold)
    to_scan = {t: sheets[t] for t in tabs}

    def work(progress: Progress) -> None:
        service = context.excel_service()
        result = service.scan_workbook(
            to_scan, columns, entities, body.threshold, on_progress=progress
        )
        findings = scan_result_findings(result)
        with job.lock:
            previous = job.state.get("applied", frozenset())
        # Back from Review: keep the terms unticked there that this run found
        # again, rather than wiping the review.
        carried = carry_over_exclusions(previous, findings)
        job.task.label = "Replacing names with codes..."
        redacted, crosswalk = service.redact_workbook(
            to_scan, result, columns, exclude=carried
        )
        with job.lock:
            job.state.update(
                scan=result,
                scan_sheets=to_scan,
                scan_columns=columns,
                findings=findings,
                applied=carried,
                carried=carried,
                redacted=redacted,
                crosswalk=crosswalk,
                xlsx=None,
            )

    return start_or_409(context, job, "Scanning for names...", work)


def _place(column: str) -> dict[str, str]:
    """Return where an occurrence sits, from its Column label."""
    if column == TAB_NAME_LABEL:
        return {"place": "tab", "column_name": ""}
    suffix = f" {HEADER_LABEL}"
    if column.endswith(suffix):
        return {"place": "header", "column_name": column.removesuffix(suffix)}
    return {"place": "cell", "column_name": column}


def _review(state: dict[str, Any]) -> ExcelReviewOut:
    findings = state["findings"]
    rows, summary, filters, clean = review_parts(findings)
    occurrences = excel_findings_dataframe(state["scan"])
    return ExcelReviewOut(
        summary=summary,
        entity_count=state["scan"].entity_count,
        cell_count=state["scan"].cell_count,
        rows=rows,
        applied=sorted(state["applied"]),
        carried=sorted(state["carried"]),
        filters=filters,
        clean=clean,
        mapping=mapping_rows(state["crosswalk"]),
        occurrences=[
            OccurrenceOut(
                sheet=str(r["Sheet"]),
                row=None if pd.isna(r["Row"]) else int(r["Row"]),
                column=str(r["Column"]),
                **_place(str(r["Column"])),
                key=term_key(r["Detected text"]),
                term=str(r["Detected text"]),
            )
            for r in occurrences.to_dict("records")
        ],
        tabs=list(state["scan_sheets"]),
    )


@router.get("/review")
def review(job_id: str, context: Context) -> ExcelReviewOut:
    """Return the Review step's data."""
    return _review(scanned_state(job_for(context, job_id, "excel")))


@router.post("/apply")
def apply(job_id: str, body: ExcludeIn, context: Context) -> ExcelReviewOut:
    """Rebuild without the unticked terms. No re-detection: a pure pass."""
    job = job_for(context, job_id, "excel")
    state = scanned_state(job)
    excluded = checked_exclusions(body.excluded, state["findings"])
    redacted, crosswalk = context.excel_service().redact_workbook(
        state["scan_sheets"], state["scan"], state["scan_columns"], exclude=excluded
    )
    with job.lock:
        job.state.update(
            applied=excluded,
            carried=frozenset(),
            redacted=redacted,
            crosswalk=crosswalk,
            xlsx=None,
        )
        return _review(dict(job.state))


@router.get("/preview")
def preview(
    job_id: str,
    context: Context,
    tab: Annotated[int, Query(ge=0)] = 0,
    start: Annotated[int, Query(ge=0)] = 0,
) -> ExcelPreviewOut:
    """Return a block of one tab's rows, redacted and original, changes marked."""
    state = scanned_state(job_for(context, job_id, "excel"))
    originals = list(state["scan_sheets"].values())
    if tab >= len(originals):
        raise HTTPException(422, "That tab is not in the scan.")
    original = originals[tab]
    sheet = state["redacted"][tab]
    redacted = sheet.data
    n_rows = len(original)
    start = min(start - start % PREVIEW_MAX_ROWS, max(0, n_rows - 1))
    end = min(start + PREVIEW_MAX_ROWS, n_rows)
    col_pos = {label: i for i, label in enumerate(redacted.columns)}
    marked: list[tuple[int, int]] = []
    elsewhere = 0
    for row, col in sheet.highlighted:
        if col not in col_pos:
            continue
        if row == HEADER_ROW:
            marked.append((-1, col_pos[col]))
        elif start <= row < end:
            marked.append((row - start, col_pos[col]))
        else:
            elsewhere += 1
    return ExcelPreviewOut(
        tab=tab,
        tabs=list(state["scan_sheets"]),
        total_rows=n_rows,
        start=start,
        page_size=PREVIEW_MAX_ROWS,
        columns=[str(c) for c in redacted.columns],
        original_columns=[str(c) for c in original.columns],
        rows=[
            [_text(v) for v in r]
            for r in redacted.iloc[start:end].itertuples(index=False)
        ],
        original_rows=[
            [_text(v) for v in r]
            for r in original.iloc[start:end].itertuples(index=False)
        ],
        marked=sorted(marked),
        elsewhere=elsewhere,
    )


@router.get("/download")
def download_info(job_id: str, context: Context) -> ExcelDownloadOut:
    """Warnings and notes for the Download step."""
    job = job_for(context, job_id, "excel")
    state = scanned_state(job)
    sheets = state["sheets"]
    return ExcelDownloadOut(
        excluded=sorted(state["applied"]),
        left_out=[n for n in sheets if n not in state["scan_sheets"]],
        nothing_found=state["scan"].entity_count == 0,
        formatting_note=formatting_note(state.get("formats", {}), len(sheets)),
        has_mapping=bool(state["crosswalk"]),
    )


def excel_file(job: Job, context: AppContext, kind: str) -> tuple[bytes, str, str]:
    """``(bytes, file name, media type)`` for ``redacted`` or ``crosswalk``.

    The workbook is built once per result and cached until the result
    changes. The crosswalk holds real names, so it only ever leaves as its
    own CSV, never inside the workbook.
    """
    state = scanned_state(job)
    if kind == "redacted":
        data = state.get("xlsx")
        if data is None:
            formats = state.get("formats", {})
            data = context.excel_gateway.write(
                [(s.name, s.data, s.highlighted) for s in state["redacted"]],
                [formats.get(name) for name in state["scan_sheets"]],
            )
            with job.lock:
                if job.state.get("redacted") is state["redacted"]:
                    job.state["xlsx"] = data
        return data, f"{job.stem}.xlsx", XLSX_TYPE
    if kind == "crosswalk":
        return crosswalk_csv(job.stem, state["crosswalk"])
    raise HTTPException(404, "No such file for an Excel upload.")
