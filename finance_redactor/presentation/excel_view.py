"""Streamlit flow for Excel pseudonymization.

Thin presentation: handles session state and widgets, delegates detection and
pseudonymization to :class:`RedactExcelService`, file I/O to the Excel gateway,
and rendering to ``presenters``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal

import pandas as pd
import streamlit as st

from finance_redactor.application.ports import ExcelGateway
from finance_redactor.application.redact_excel import RedactExcelService
from finance_redactor.config import Settings
from finance_redactor.domain.errors import UnreadableFileError
from finance_redactor.domain.quality import QualityIssue
from finance_redactor.presentation.crosswalk_view import render_crosswalk_section
from finance_redactor.presentation.exclusion_view import (
    render_deselect_editor,
    render_exclusion_warning,
)
from finance_redactor.presentation.master_list_view import render_master_list_status
from finance_redactor.presentation.presenters import (
    ENTITY_HELP,
    PREVIEW_MAX_ROWS,
    THRESHOLD_HELP,
    crosswalk_dataframe,
    entity_label,
    excel_findings_dataframe,
    plural,
    preview_hidden_count,
    preview_styler,
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
    name_counts: Mapping[str, int],
    quality_issues: Sequence[QualityIssue] | None = None,
    on_refresh_master_list: Callable[[], None] | None = None,
    steps: Any,
) -> None:
    """Render the Excel pseudonymization flow in Streamlit."""
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
        except UnreadableFileError:
            st.error(
                "This file could not be read as an Excel workbook. It may be "
                "corrupted, or not really an .xlsx/.xls file despite its "
                "name. Open it in Excel, save a fresh copy, and upload that "
                "instead."
            )
            st.stop()

    sheets: dict[str, pd.DataFrame] = st.session_state.sheets
    tab_names = list(sheets)

    show_step(steps, 2)
    with st.container(border=True):
        st.subheader("2. Set options")
        if len(tab_names) > 1:
            selected_tabs = st.multiselect(
                "Tabs to scan for PII",
                options=tab_names,
                default=tab_names,
                help=(
                    "Tabs you leave out are not scanned, and they are not in "
                    "the downloaded file either."
                ),
            )
        else:
            selected_tabs = tab_names
        if not selected_tabs:
            st.warning("Select at least one tab to scan.")
            st.stop()

        columns_by_sheet = _choose_columns(selected_tabs, sheets, excel_gateway)

        # Above the expander, not inside it: a data-quality warning about the
        # master list changes how far the IDs can be trusted, so it must not
        # sit behind a collapsed panel.
        render_master_list_status(
            name_counts,
            quality_issues,
            settings.master_list_file,
            on_refresh=on_refresh_master_list,
        )

        with st.expander("Advanced settings"):
            threshold = st.slider(
                "Confidence threshold",
                min_value=0.1,
                max_value=1.0,
                value=settings.default_threshold,
                step=0.05,
                help=THRESHOLD_HELP,
            )
            entity_options = st.multiselect(
                "Kinds of information to hide",
                options=list(settings.supported_entities),
                default=list(settings.supported_entities),
                format_func=entity_label,
                help=ENTITY_HELP,
            )

        if not any(columns_by_sheet.values()):
            st.warning("Select at least one column to scan.")
            st.stop()

        # Red/primary only before the first run - once a result exists, the
        # download button below becomes the one action that matters.
        main_button_type: Literal["primary", "secondary"] = (
            "secondary" if "findings" in st.session_state else "primary"
        )
        if st.button("Pseudonymize", type=main_button_type, width="stretch"):
            with st.status("Scanning for PII...", expanded=True) as status:
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
                    entity_options,
                    threshold,
                    on_progress=_on_progress,
                )
                status.update(label="Applying pseudonyms...")
                redacted_sheets, crosswalk = excel_service.redact_workbook(
                    to_scan, scan_result, columns_by_sheet
                )
                status.update(label="Scan complete", state="complete", expanded=False)
            st.session_state.findings = scan_result
            st.session_state.scan_sheets = to_scan
            st.session_state.scan_columns = columns_by_sheet
            st.session_state.redacted_sheets = redacted_sheets
            st.session_state.crosswalk = crosswalk
            st.session_state.excel_excluded_applied = frozenset()
            st.session_state.excel_bytes = None

        if "findings" not in st.session_state:
            st.caption(
                "Click the button above to run it. Your results and download "
                "will appear here."
            )
            st.stop()

    scan_result = st.session_state.findings
    scan_sheets: dict[str, pd.DataFrame] = st.session_state.scan_sheets
    scan_columns: dict[str, list[str]] = st.session_state.scan_columns
    redacted_sheets = st.session_state.redacted_sheets
    crosswalk = st.session_state.crosswalk
    n_cells = scan_result.cell_count
    n_entities = scan_result.entity_count
    base_name = output_stem()

    show_step(steps, 3)
    with st.container(border=True):
        st.subheader("3. Review the results")
        found_col, cells_col = st.columns(2)
        found_col.metric("PII instances found", f"{n_entities:,}")
        cells_col.metric("Cells affected", f"{n_cells:,}")

        tab_preview, tab_mapping, tab_details = st.tabs(
            ["Preview", "Mapping", "Details"]
        )
        with tab_preview:
            st.caption(
                "Cells with PII are filled yellow and start with », the "
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
                st.markdown("**Pseudonymized**")
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
                    "(listed under Details). The download has every row."
                )
        with tab_mapping:
            render_crosswalk_section(
                crosswalk, base_name, key_prefix="excel", download_separately=False
            )
        with tab_details:
            excluded = render_deselect_editor(
                scan_result_findings(scan_result),
                key_prefix="excel",
                excluded=st.session_state.get("excel_excluded_applied", frozenset()),
            )
            st.markdown(f"**All detections ({plural(n_entities, 'finding')})**")
            if n_entities == 0:
                st.write("No PII detected.")
            else:
                st.dataframe(
                    excel_findings_dataframe(scan_result),
                    width="stretch",
                    hide_index=True,
                )

        if excluded != st.session_state.get("excel_excluded_applied", frozenset()):
            # Cheap by construction: scan and redact are separate, so
            # re-applying is a pure pass over the ScanResult already in
            # session state. No re-detection, and the spaCy model is never
            # touched.
            with st.spinner("Reapplying pseudonyms without those terms..."):
                redacted_sheets, crosswalk = excel_service.redact_workbook(
                    scan_sheets, scan_result, scan_columns, exclude=excluded
                )
            st.session_state.redacted_sheets = redacted_sheets
            st.session_state.crosswalk = crosswalk
            st.session_state.excel_excluded_applied = excluded
            st.session_state.excel_bytes = None
            st.rerun()

    show_step(steps, 4)
    with st.container(border=True):
        st.subheader("4. Download")
        render_exclusion_warning(
            st.session_state.get("excel_excluded_applied", frozenset())
        )
        left_out = [name for name in sheets if name not in scan_sheets]
        if left_out:
            st.warning(
                f"{plural(len(left_out), 'tab')} you did not select "
                f"({', '.join(left_out)}) {'is' if len(left_out) == 1 else 'are'} "
                "not in the download."
            )
        if n_entities == 0:
            st.info("No PII was detected. The file is already clean.")
            return
        if crosswalk:
            st.warning(
                "This workbook includes a **Crosswalk** sheet mapping names to "
                "pseudonyms. The downloaded file is therefore **Confidential** "
                "as a whole under IPA's data classification policy - not just "
                "Internal - so store and share it accordingly."
            )
        # Built once per result and kept in session_state, like the Word and
        # PDF bytes: every widget click reruns this script, and re-serializing
        # the workbook each time is wasted work. Cleared wherever redacted_df
        # or crosswalk change (the scan and the exclusion re-apply above).
        if st.session_state.get("excel_bytes") is None:
            st.session_state.excel_bytes = excel_gateway.write(
                [(s.name, s.data, s.highlighted) for s in redacted_sheets],
                crosswalk_dataframe(crosswalk),
            )
        st.download_button(
            label="Download pseudonymized Excel file",
            data=st.session_state.excel_bytes,
            file_name=f"{base_name}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            width="stretch",
        )
        st.caption(
            "Yellow-highlighted cells indicate where a name was replaced with "
            'its pseudonym; the workbook\'s last sheet, "Crosswalk", lists '
            "the full name-to-pseudonym mapping. Tab names are checked too, "
            "so a tab named after someone is renamed. Bank and payment details "
            "show as a fixed mask such as [ACCOUNT] or [CARD], with nothing "
            "to decode."
        )


def _choose_columns(
    selected_tabs: list[str],
    sheets: Mapping[str, pd.DataFrame],
    excel_gateway: ExcelGateway,
) -> dict[str, list[str]]:
    """One column picker per tab, defaulting to its free-text columns."""
    help_text = (
        "Numeric and date columns are excluded by default. Add a "
        "numeric column here if it holds account or M-Pesa numbers."
    )

    def pick(name: str, label: str) -> list[str]:
        df = sheets[name]
        return st.multiselect(
            label,
            options=list(df.columns),
            default=excel_gateway.text_columns(df),
            key=f"excel_cols_{name}",
            help=help_text,
        )

    if len(selected_tabs) == 1:
        return {selected_tabs[0]: pick(selected_tabs[0], "Columns to scan for PII")}
    with st.expander(f"Columns to scan, tab by tab ({len(selected_tabs)} tabs)"):
        return {name: pick(name, name) for name in selected_tabs}
