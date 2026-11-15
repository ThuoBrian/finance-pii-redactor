"""Streamlit flow for Excel pseudonymization.

Thin presentation: handles session state and widgets, delegates detection and
pseudonymization to :class:`RedactExcelService`, file I/O to the Excel gateway,
and rendering to ``presenters``.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from finance_redactor.application.ports import ExcelGateway
from finance_redactor.application.redact_excel import RedactExcelService
from finance_redactor.config import Settings
from finance_redactor.domain.errors import UnreadableFileError
from finance_redactor.presentation import wizard
from finance_redactor.presentation.crosswalk_view import (
    render_crosswalk_download,
    render_crosswalk_section,
)
from finance_redactor.presentation.exclusion_view import (
    render_deselect_editor,
    render_exclusion_warning,
    unapplied_changes_note,
)
from finance_redactor.presentation.presenters import (
    ENTITY_HELP,
    PREVIEW_MAX_ROWS,
    THRESHOLD_HELP,
    entity_label,
    excel_findings_dataframe,
    formatting_note,
    plural,
    preview_styler,
    review_tab_labels,
    scan_result_findings,
)
from finance_redactor.presentation.session import (
    output_stem,
    reset_on_new_upload,
)
from finance_redactor.presentation.steps import show_step

# Scan-size warning (see scan_size_warning). About a minute of scanning, or a
# workbook big enough that holding it twice in memory starts to drag.
_SLOW_SCAN_VALUES = 3_000
_BIG_WORKBOOK_CELLS = 500_000
_FAST_VALUES_PER_SECOND = 60
_SLOW_VALUES_PER_SECOND = 30


def run_excel_flow(
    uploaded: Any,
    *,
    excel_service: RedactExcelService,
    excel_gateway: ExcelGateway,
    settings: Settings,
    steps: Any,
) -> None:
    """Render the Excel flow: Options, Review and Download (see ``wizard``)."""
    is_new = reset_on_new_upload(
        uploaded,
        "excel",
        (
            "findings",
            "redacted_sheets",
            "scan_sheets",
            "scan_columns",
            "crosswalk",
            "pdf_buffer",
            "pdf_findings",
            "pdf_pages",
            "pdf_crosswalk",
            "excel_excluded_applied",
            "excel_bytes",
        ),
        force="sheets" not in st.session_state,
    )
    if is_new:
        try:
            st.session_state.sheets = excel_gateway.read_sheets(uploaded)
            st.session_state.formats = excel_gateway.read_formatting(uploaded)
        except UnreadableFileError:
            st.error(
                "This file could not be read as an Excel workbook. It may be "
                "corrupted, or not really an .xlsx/.xls file despite its "
                "name. Open it in Excel, save a fresh copy, and upload that "
                "instead."
            )
            st.stop()

    sheets: dict[str, pd.DataFrame] = st.session_state.sheets
    if wizard.current() == wizard.OPTIONS or "findings" not in st.session_state:
        _options_step(sheets, excel_service, excel_gateway, settings, steps)
        return
    if wizard.current() == wizard.REVIEW:
        _review_step(excel_service, steps)
        return
    _download_step(sheets, excel_gateway, steps)


def scan_size_warning(
    sheets: dict[str, pd.DataFrame], columns_by_sheet: dict[str, list[str]]
) -> str | None:
    """Warn before a scan that will take minutes or a lot of memory, else None.

    The scan analyzes each distinct value once, so its time follows the
    distinct values in the chosen columns, not the row count. The rate range
    is rough: the real engine checked about 48 values a second on a
    development laptop, and the master list and longer cells slow it down.
    lean-dev: a warning only, no chunking or abort.
    """
    n_cells = sum(df.size for df in sheets.values())
    distinct = len(
        {
            value
            for name, df in sheets.items()
            for col in columns_by_sheet.get(name, [])
            if col in df.columns
            for value in df[col].dropna().unique()
        }
    )
    slow = distinct >= _SLOW_SCAN_VALUES
    big = n_cells >= _BIG_WORKBOOK_CELLS
    if not (slow or big):
        return None
    parts = [
        f"This is a large job: {n_cells:,} cells, with {distinct:,} distinct "
        "values in the chosen columns."
    ]
    if slow:
        low = max(1, round(distinct / _FAST_VALUES_PER_SECOND / 60))
        high = max(low + 1, round(distinct / _SLOW_VALUES_PER_SECOND / 60))
        parts.append(f"Expect the scan to take roughly {low:,} to {high:,} minutes.")
    if big:
        parts.append(
            "The whole workbook is held in memory while you work, so the "
            "app may be slow to respond."
        )
    parts.append(
        "Keep this page open while it runs. To make it quicker, choose fewer "
        "tabs or columns under Customize."
    )
    return " ".join(parts)


def name_summary(names: list[str], shown: int = 2) -> str:
    """``"Jan, Feb + 8 more"``: the first few names, then a count of the rest."""
    head = ", ".join(names[:shown])
    rest = len(names) - shown
    return f"{head} + {rest:,} more" if rest > 0 else head


def _options_step(
    sheets: dict[str, pd.DataFrame],
    excel_service: RedactExcelService,
    excel_gateway: ExcelGateway,
    settings: Settings,
    steps: Any,
) -> None:
    show_step(steps, 2)
    st.subheader("Options")
    tab_names = list(sheets)
    n_rows = sum(len(df) for df in sheets.values())
    st.caption(
        f"{plural(len(tab_names), 'tab')} ({name_summary(tab_names)}) · "
        f"{plural(n_rows, 'row')} · text columns are picked for you"
    )

    # Values live in session state (seeded here, kept by wizard.keep_option_
    # choices), never in a widget default: passing both raises a warning.
    state = st.session_state
    state.setdefault("excel_tabs", tab_names)
    for name, df in sheets.items():
        state.setdefault(f"excel_cols_{name}", excel_gateway.text_columns(df))
    state.setdefault("excel_threshold", settings.default_threshold)
    state.setdefault("excel_entities", list(settings.supported_entities))

    with st.expander("Customize: tabs and columns, kinds of information, confidence"):
        if len(tab_names) > 1:
            st.multiselect(
                "Tabs to scan",
                options=tab_names,
                key="excel_tabs",
                help=(
                    "Tabs you leave out are not scanned, and they are not in "
                    "the downloaded file either."
                ),
            )
        selected_tabs = (
            [t for t in state["excel_tabs"] if t in sheets]
            if len(tab_names) > 1
            else tab_names
        )
        # One column picker, pointed at one tab at a time. Each tab's choice
        # stays in its own excel_cols_{name} key (kept by keep_option_choices
        # while its picker is not drawn), which the scan below reads.
        tab = (
            st.selectbox("Which tab's columns?", options=selected_tabs)
            if len(selected_tabs) > 1
            else next(iter(selected_tabs), None)
        )
        if tab is not None:
            st.multiselect(
                "Columns to scan",
                options=list(sheets[tab].columns),
                key=f"excel_cols_{tab}",
                help=(
                    "Numeric and date columns are left out by default. Add a "
                    "numeric column if it holds account or M-Pesa numbers. "
                    "Column headers are always checked."
                ),
            )
        no_columns = [t for t in selected_tabs if not state[f"excel_cols_{t}"]]
        if no_columns and len(no_columns) < len(selected_tabs):
            st.caption(
                f"No columns chosen in {name_summary(no_columns)}: only the "
                "headers and tab name are checked there, and its cells go "
                "into the download as they are."
            )
        # The detection threshold, not the fuzzy-match one. Capped at the
        # score master-list matches get: anything higher drops every one.
        st.slider(
            "Confidence threshold",
            min_value=0.1,
            max_value=settings.custom_match_score,
            step=0.05,
            help=THRESHOLD_HELP,
            key="excel_threshold",
        )
        st.multiselect(
            "Kinds of information to hide",
            options=list(settings.supported_entities),
            format_func=entity_label,
            help=ENTITY_HELP,
            key="excel_entities",
        )

    columns_by_sheet = {
        name: list(state[f"excel_cols_{name}"]) for name in selected_tabs
    }
    if not selected_tabs:
        st.warning("Choose at least one tab to scan, under Customize.")
        return
    if not any(columns_by_sheet.values()):
        st.warning("Choose at least one column to scan, under Customize.")
        return
    estimate = scan_size_warning(
        {name: sheets[name] for name in selected_tabs}, columns_by_sheet
    )
    if estimate:
        st.warning(estimate)

    if st.button("Redact my file", type="primary", width="stretch"):
        with st.status("Scanning for names...", expanded=True) as status:
            progress = st.progress(0.0)

            def _on_progress(done: int, total: int) -> None:
                progress.progress(
                    done / total if total else 1.0,
                    text=f"{done:,} of {total:,} unique values checked",
                )

            to_scan = {name: sheets[name] for name in selected_tabs}
            scan_result = excel_service.scan_workbook(
                to_scan,
                columns_by_sheet,
                list(state["excel_entities"]),
                float(state["excel_threshold"]),
                on_progress=_on_progress,
            )
            status.update(label="Replacing names with codes...")
            redacted_sheets, crosswalk = excel_service.redact_workbook(
                to_scan, scan_result, columns_by_sheet
            )
        state.findings = scan_result
        state.scan_sheets = to_scan
        state.scan_columns = columns_by_sheet
        state.redacted_sheets = redacted_sheets
        state.crosswalk = crosswalk
        state.excel_excluded_applied = frozenset()
        state.excel_bytes = None
        wizard.go(wizard.REVIEW)


def _review_step(excel_service: RedactExcelService, steps: Any) -> None:
    state = st.session_state
    scan_result = state.findings
    scan_sheets: dict[str, pd.DataFrame] = state.scan_sheets
    scan_columns: dict[str, list[str]] = state.scan_columns
    redacted_sheets = state.redacted_sheets
    n_entities = scan_result.entity_count

    show_step(steps, 3)
    st.subheader("Review what was found")
    st.caption(
        f"{plural(n_entities, 'term')} found in "
        f"{plural(scan_result.cell_count, 'cell')}"
    )
    review_findings = scan_result_findings(scan_result)
    tab_review, tab_preview, tab_mapping, tab_occurrences = st.tabs(
        review_tab_labels(review_findings, preview=True)
    )
    with tab_preview:
        st.caption(
            "Cells with names are filled yellow and start with », the "
            "same yellow as in the downloaded Excel file."
        )
        shown = 0
        if len(scan_sheets) > 1:
            shown = st.selectbox(
                "Tab to preview",
                options=range(len(scan_sheets)),
                format_func=lambda i: list(scan_sheets)[i],
            )
        df = list(scan_sheets.values())[shown]
        redacted_df = redacted_sheets[shown].data
        cell_keys = redacted_sheets[shown].highlighted
        # A big tab is shown a block of rows at a time; a page of the whole
        # sheet would only slow the browser. Keys are row positions, and
        # read_excel gives a 0..n-1 index, so a slice keeps them lined up.
        start = _preview_rows(len(df), cell_keys, shown)
        rows = slice(start, start + PREVIEW_MAX_ROWS)
        # One table at a time: the redacted one, or the original when the
        # toggle is on. Rows and columns line up 1:1, so switching loses
        # nothing, and the page is half as long as two stacked tables.
        if st.toggle("Compare with original", key="excel_preview_original"):
            # A redacted header renames its column; columns keep their order,
            # so map each highlighted key back to the original by position.
            original_keys = {
                (row, df.columns[redacted_df.columns.get_loc(col)])
                for row, col in cell_keys
                if col in redacted_df.columns
            }
            st.markdown("**Original** (not redacted)")
            st.dataframe(
                preview_styler(df.iloc[rows], original_keys),
                width="stretch",
                hide_index=True,
            )
        else:
            st.markdown("**Redacted**")
            st.dataframe(
                preview_styler(redacted_df.iloc[rows], cell_keys),
                width="stretch",
                hide_index=True,
            )
    with tab_mapping:
        render_crosswalk_section(state.crosswalk)
    with tab_review:
        excluded = render_deselect_editor(
            review_findings,
            key_prefix="excel",
            excluded=state.get("excel_excluded_applied", frozenset()),
        )
    with tab_occurrences:
        st.markdown(f"**All detections ({plural(n_entities, 'finding')})**")
        if n_entities == 0:
            st.write("Nothing was detected.")
        else:
            st.dataframe(
                excel_findings_dataframe(scan_result),
                width="stretch",
                hide_index=True,
            )

    if excluded != state.get("excel_excluded_applied", frozenset()):
        # Cheap by construction: scan and redact are separate, so
        # re-applying is a pure pass over the ScanResult already in
        # session state. No re-detection, and the spaCy model is never
        # touched.
        with st.spinner("Rebuilding without those terms..."):
            redacted_sheets, crosswalk = excel_service.redact_workbook(
                scan_sheets, scan_result, scan_columns, exclude=excluded
            )
        state.redacted_sheets = redacted_sheets
        state.crosswalk = crosswalk
        state.excel_excluded_applied = excluded
        state.excel_bytes = None
        st.rerun()

    wizard.nav(
        back=("Back to options", wizard.OPTIONS),
        forward=("Continue to download", wizard.DOWNLOAD),
        hold=unapplied_changes_note(
            "excel", state.get("excel_excluded_applied", frozenset())
        ),
    )


def _preview_rows(n_rows: int, cell_keys: set[tuple[int, str]], tab: int) -> int:
    """Pick which block of rows to preview, and say plainly what is not shown.

    Returns the first row of the block. A tab that fits on one page needs no
    choice and gets 0.
    """
    if n_rows <= PREVIEW_MAX_ROWS:
        return 0
    start: int = st.selectbox(
        "Rows to preview",
        options=range(0, n_rows, PREVIEW_MAX_ROWS),
        format_func=lambda s: f"Rows {s + 1:,} to {min(s + PREVIEW_MAX_ROWS, n_rows):,}",
        key=f"excel_preview_rows_{tab}",
    )
    end = min(start + PREVIEW_MAX_ROWS, n_rows)
    elsewhere = sum(1 for row, _ in cell_keys if row >= 0 and not start <= row < end)
    st.info(
        f"This tab has {n_rows:,} rows. Showing rows {start + 1:,} to {end:,}, "
        f"so {n_rows - (end - start):,} rows are not on screen, with "
        f"{plural(elsewhere, 'highlighted cell')} among them. Pick other rows "
        "above to check them. The download has every row."
    )
    return start


def _download_step(
    sheets: dict[str, pd.DataFrame], excel_gateway: ExcelGateway, steps: Any
) -> None:
    state = st.session_state
    scan_sheets: dict[str, pd.DataFrame] = state.scan_sheets
    redacted_sheets = state.redacted_sheets
    crosswalk = state.crosswalk
    base_name = output_stem()

    show_step(steps, 4)
    st.subheader("Download")
    render_exclusion_warning(state.get("excel_excluded_applied", frozenset()))
    left_out = [name for name in sheets if name not in scan_sheets]
    if left_out:
        st.warning(
            f"{plural(len(left_out), 'tab')} you did not select "
            f"({', '.join(left_out)}) {'is' if len(left_out) == 1 else 'are'} "
            "not in the download."
        )
    if state.findings.entity_count == 0:
        # Not "the file is clean": only the chosen columns were scanned.
        st.info(
            "Nothing was detected in the columns you chose, so no cell was "
            "changed. The workbook is still rebuilt from cell values, so you "
            "can download it below."
        )
    # Built once per result and kept in session_state: every widget click
    # reruns this script, and re-serializing the workbook each time is
    # wasted work. Cleared wherever the redacted sheets change. Always built,
    # even with nothing found: the user may want the trimmed tabs, and the
    # rebuilt file leaves comments, formulas and properties behind.
    if state.get("excel_bytes") is None:
        formats = state.get("formats", {})
        state.excel_bytes = excel_gateway.write(
            [(s.name, s.data, s.highlighted) for s in redacted_sheets],
            None,  # the crosswalk leaves as its own Confidential file
            [formats.get(name) for name in scan_sheets],
        )
    safe, private = wizard.download_cards()
    with safe:
        st.download_button(
            label="Download redacted workbook",
            data=state.excel_bytes,
            file_name=f"{base_name}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            width="stretch",
        )
        st.caption(
            "Names are replaced with codes such as STF-10010, and changed "
            "cells are yellow. Bank and payment details show as a mask "
            "such as [ACCOUNT]. Tab names and column headers are checked "
            "too."
        )
        note = formatting_note(state.get("formats", {}), len(sheets))
        if note:
            st.caption(note)
    with private:
        render_crosswalk_download(crosswalk, base_name, key_prefix="excel")

    wizard.nav(back=("Back to review", wizard.REVIEW), finish=True)
