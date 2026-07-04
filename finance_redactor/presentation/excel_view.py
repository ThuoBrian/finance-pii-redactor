"""Streamlit flow for Excel pseudonymization.

Thin presentation: handles session state and widgets, delegates detection and
pseudonymization to :class:`RedactExcelService`, file I/O to the Excel gateway,
and rendering to ``presenters``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

import streamlit as st

from finance_redactor.application.ports import ExcelGateway
from finance_redactor.application.redact_excel import RedactExcelService
from finance_redactor.config import Settings
from finance_redactor.presentation.crosswalk_view import render_crosswalk_section
from finance_redactor.presentation.presenters import (
    excel_findings_dataframe,
    highlighted_html,
)


def _name_list_help(counts: Mapping[str, int]) -> str:
    total = sum(counts.values())
    by_cat = ", ".join(f"{n:,} {cat}" for cat, n in sorted(counts.items())) or "none"
    return (
        f"Loaded {total:,} master-list entr(y/ies): {by_cat}. Edit "
        "`data/master_list.csv` "
        "(columns: category, name, id) and restart the app to update them."
    )


def run_excel_flow(
    uploaded: Any,
    *,
    excel_service: RedactExcelService,
    excel_gateway: ExcelGateway,
    settings: Settings,
    name_counts: Mapping[str, int],
) -> None:
    """Render the Excel pseudonymization flow in Streamlit."""
    if (
        "df" not in st.session_state
        or st.session_state.get("uploaded_name") != uploaded.name
        or st.session_state.get("file_type") != "excel"
    ):
        st.session_state.df = excel_gateway.read(uploaded)
        st.session_state.uploaded_name = uploaded.name
        st.session_state.file_type = "excel"
        for key in (
            "findings",
            "redacted_df",
            "crosswalk",
            "pdf_buffer",
            "pdf_findings",
            "pdf_pages",
            "pdf_crosswalk",
        ):
            st.session_state.pop(key, None)

    df = st.session_state.df
    text_cols = excel_gateway.text_columns(df)

    st.subheader("Configuration")
    selected_cols = st.multiselect(
        "Columns to scan for PII",
        options=list(df.columns),
        default=text_cols,
        help="Numeric and date columns are excluded by default.",
    )

    with st.expander("Advanced settings"):
        threshold = st.slider(
            "Confidence threshold",
            min_value=0.1,
            max_value=1.0,
            value=settings.default_threshold,
            step=0.05,
            help="Lower values flag more text (fewer missed names, more false positives).",
        )
        entity_options = st.multiselect(
            "Entity types to pseudonymize",
            options=list(settings.supported_entities),
            default=list(settings.supported_entities),
        )
        st.markdown("**Master list**")
        st.caption(_name_list_help(name_counts))

    if not selected_cols:
        st.warning("Select at least one column to scan.")
        st.stop()

    if st.button("Pseudonymize", type="primary", width="stretch"):
        progress = st.progress(0.0, text="Scanning for PII...")

        def _on_progress(done: int, total: int) -> None:
            progress.progress(
                done / total if total else 1.0,
                text=f"Scanning for PII... ({done:,} of {total:,} unique values)",
            )

        scan_result = excel_service.scan(
            df, selected_cols, entity_options, threshold, on_progress=_on_progress
        )
        with st.spinner("Applying pseudonyms..."):
            redacted_df, crosswalk = excel_service.redact(
                df, scan_result, selected_cols
            )
        progress.empty()
        st.session_state.findings = scan_result
        st.session_state.redacted_df = redacted_df
        st.session_state.crosswalk = crosswalk

    if "findings" not in st.session_state:
        st.stop()

    scan_result = st.session_state.findings
    redacted_df = st.session_state.redacted_df
    crosswalk = st.session_state.crosswalk
    n_cells = scan_result.cell_count
    n_entities = scan_result.entity_count
    st.success(f"Found {n_entities} PII instance(s) across {n_cells} cell(s).")

    st.subheader("Comparison")
    cell_keys = scan_result.cell_keys()
    col_orig, col_redacted = st.columns(2)
    with col_orig:
        st.markdown("**Original** (PII highlighted)")
        st.markdown(highlighted_html(df, cell_keys, "#FFA500"), unsafe_allow_html=True)
    with col_redacted:
        st.markdown("**Pseudonymized** (changed cells highlighted)")
        st.markdown(
            highlighted_html(redacted_df, cell_keys, "#90EE90"),
            unsafe_allow_html=True,
        )

    base_name = re.sub(r"[^\w\-]", "_", uploaded.name.rsplit(".", 1)[0])
    render_crosswalk_section(crosswalk, base_name, key_prefix="excel")

    with st.expander(f"Detection details ({n_entities} finding(s))"):
        if n_entities == 0:
            st.write("No PII detected.")
        else:
            st.dataframe(
                excel_findings_dataframe(scan_result),
                width="stretch",
                hide_index=True,
            )

    st.subheader("Download")
    if n_entities == 0:
        st.info("No PII was detected. The file is already clean.")
    else:
        excel_bytes = excel_gateway.write(redacted_df, cell_keys)
        st.download_button(
            label="Download pseudonymized Excel file",
            data=excel_bytes,
            file_name=f"{base_name}_pseudonymized.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            width="stretch",
        )
        st.caption(
            "Yellow-highlighted cells in the downloaded file indicate where a name "
            "was replaced with its pseudonym."
        )
