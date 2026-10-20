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
)
from finance_redactor.presentation.presenters import (
    ENTITY_HELP,
    PREVIEW_MAX_ROWS,
    THRESHOLD_HELP,
    entity_label,
    excel_findings_dataframe,
    formatting_note,
    plural,
    preview_hidden_count,
    preview_styler,
    review_tab_labels,
    scan_result_findings,
)
from finance_redactor.presentation.session import (
    output_stem,
    reset_on_new_upload,
)
from finance_redactor.presentation.steps import show_step


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
        f"{plural(len(tab_names), 'tab')} ({', '.join(tab_names)}) · "
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
        for name in selected_tabs:
            st.multiselect(
                "Columns to scan"
                if len(tab_names) == 1
                else f"Columns to scan: {name}",
                options=list(sheets[name].columns),
                key=f"excel_cols_{name}",
                help=(
                    "Numeric and date columns are left out by default. Add a "
                    "numeric column if it holds account or M-Pesa numbers."
                ),
            )
        st.slider(
            "Confidence threshold",
            min_value=0.1,
            max_value=1.0,
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
        col_orig, col_redacted = st.columns(2)
        with col_orig:
            st.markdown("**Original**")
            st.dataframe(
                preview_styler(df, cell_keys), width="stretch", hide_index=True
            )
        with col_redacted:
            st.markdown("**Redacted**")
            st.dataframe(
                preview_styler(redacted_df, cell_keys),
                width="stretch",
                hide_index=True,
            )
        if len(df) > PREVIEW_MAX_ROWS:
            n_hidden = preview_hidden_count(df, cell_keys)
            st.caption(
                f"Showing the first {plural(PREVIEW_MAX_ROWS, 'row')} of "
                f"{len(df):,}. Highlighted cells below that: {n_hidden:,} "
                "(listed under Occurrences). The download has every row."
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
    )


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
        st.info("Nothing was detected, so the file is already clean.")
    else:
        # Built once per result and kept in session_state: every widget click
        # reruns this script, and re-serializing the workbook each time is
        # wasted work. Cleared wherever the redacted sheets change.
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
                "such as [ACCOUNT]. Tab names are checked too."
            )
            note = formatting_note(state.get("formats", {}), len(sheets))
            if note:
                st.caption(note)
        with private:
            render_crosswalk_download(crosswalk, base_name, key_prefix="excel")

    wizard.nav(back=("Back to review", wizard.REVIEW), finish=True)
