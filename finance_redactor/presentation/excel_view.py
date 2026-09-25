"""Streamlit flow for Excel pseudonymization.

Thin presentation: handles session state and widgets, delegates detection and
pseudonymization to :class:`RedactExcelService`, file I/O to the Excel gateway,
and rendering to ``presenters``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import streamlit as st

from finance_redactor.application.ports import ExcelGateway
from finance_redactor.application.redact_excel import RedactExcelService
from finance_redactor.config import Settings
from finance_redactor.domain.quality import QualityIssue
from finance_redactor.presentation.crosswalk_view import render_crosswalk_section
from finance_redactor.presentation.exclusion_view import (
    render_deselect_editor,
    render_exclusion_warning,
)
from finance_redactor.presentation.master_list_view import render_master_list_status
from finance_redactor.presentation.presenters import (
    crosswalk_dataframe,
    excel_findings_dataframe,
    highlighted_html,
    scan_result_findings,
)
from finance_redactor.presentation.session import (
    reset_on_new_upload,
    sanitize_base_name,
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
            "redacted_df",
            "crosswalk",
            "pdf_buffer",
            "pdf_findings",
            "pdf_pages",
            "pdf_crosswalk",
            "excel_excluded_applied",
        ),
        force="df" not in st.session_state,
    )
    if is_new:
        st.session_state.df = excel_gateway.read(uploaded)

    df = st.session_state.df
    text_cols = excel_gateway.text_columns(df)

    show_step(steps, 2)
    st.subheader("2. Set options")
    selected_cols = st.multiselect(
        "Columns to scan for PII",
        options=list(df.columns),
        default=text_cols,
        help=(
            "Numeric and date columns are excluded by default. Add a numeric "
            "column here if it holds account or M-Pesa numbers."
        ),
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
        render_master_list_status(
            name_counts,
            quality_issues,
            settings.master_list_file,
            on_refresh=on_refresh_master_list,
        )

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
        st.session_state.excel_excluded_applied = frozenset()

    if "findings" not in st.session_state:
        st.caption(
            "Click the button above to run it. Your results and download will "
            "appear here."
        )
        st.stop()

    scan_result = st.session_state.findings
    redacted_df = st.session_state.redacted_df
    crosswalk = st.session_state.crosswalk
    n_cells = scan_result.cell_count
    n_entities = scan_result.entity_count
    show_step(steps, 3)
    st.subheader("3. Review the results")
    st.success(f"Found {n_entities} PII instance(s) across {n_cells} cell(s).")

    st.markdown("**Comparison**")
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

    base_name = sanitize_base_name(uploaded.name)
    render_crosswalk_section(
        crosswalk, base_name, key_prefix="excel", download_separately=False
    )

    excluded = render_deselect_editor(
        scan_result_findings(scan_result),
        key_prefix="excel",
        excluded=st.session_state.get("excel_excluded_applied", frozenset()),
    )
    if excluded != st.session_state.get("excel_excluded_applied", frozenset()):
        # Cheap by construction: scan and redact are separate, so re-applying
        # is a pure pass over the ScanResult already in session state. No
        # re-detection, and the spaCy model is never touched.
        with st.spinner("Reapplying pseudonyms without those terms..."):
            redacted_df, crosswalk = excel_service.redact(
                df, scan_result, selected_cols, exclude=excluded
            )
        st.session_state.redacted_df = redacted_df
        st.session_state.crosswalk = crosswalk
        st.session_state.excel_excluded_applied = excluded
        st.rerun()

    with st.expander(f"Detection details ({n_entities} finding(s))"):
        if n_entities == 0:
            st.write("No PII detected.")
        else:
            st.dataframe(
                excel_findings_dataframe(scan_result),
                width="stretch",
                hide_index=True,
            )

    show_step(steps, 4)
    st.subheader("4. Download")
    render_exclusion_warning(
        st.session_state.get("excel_excluded_applied", frozenset())
    )
    if n_entities == 0:
        st.info("No PII was detected. The file is already clean.")
    else:
        if crosswalk:
            st.warning(
                "This workbook includes a **Crosswalk** sheet mapping names to "
                "pseudonyms. The downloaded file is therefore **Confidential** as "
                "a whole under IPA's data classification policy - not just "
                "Internal - so store and share it accordingly."
            )
        excel_bytes = excel_gateway.write(
            redacted_df, cell_keys, crosswalk_dataframe(crosswalk)
        )
        st.download_button(
            label="Download pseudonymized Excel file",
            data=excel_bytes,
            file_name=f"{base_name}_pseudonymized.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
            width="stretch",
        )
        st.caption(
            "Yellow-highlighted cells indicate where a name was replaced with "
            'its pseudonym; the workbook\'s second sheet, "Crosswalk", lists '
            "the full name-to-pseudonym mapping. Bank and payment details "
            "show as a fixed mask such as [ACCOUNT] or [CARD], with nothing "
            "to decode."
        )
