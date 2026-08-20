"""Streamlit flow for Word (.docx) pseudonymization.

Thin presentation: handles session state and widgets, delegates the whole
detect-and-pseudonymize pipeline to :class:`RedactDocxService`, and renders the
summary via ``presenters``. Pseudonymize-only (no blackout mode) - Word text
stays fully editable, matching the Excel flow rather than the PDF flow.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import streamlit as st

from finance_redactor.application.redact_docx import RedactDocxService
from finance_redactor.config import Settings
from finance_redactor.domain.quality import QualityIssue
from finance_redactor.presentation.crosswalk_view import render_crosswalk_section
from finance_redactor.presentation.master_list_view import render_master_list_status
from finance_redactor.presentation.presenters import docx_findings_dataframe


def run_docx_flow(
    uploaded: Any,
    *,
    docx_service: RedactDocxService,
    settings: Settings,
    name_counts: Mapping[str, int],
    quality_issues: Sequence[QualityIssue] | None = None,
    on_refresh_master_list: Callable[[], None] | None = None,
) -> None:
    """Render the Word (.docx) pseudonymization flow in Streamlit."""
    if (
        st.session_state.get("uploaded_name") != uploaded.name
        or st.session_state.get("file_type") != "docx"
    ):
        st.session_state.uploaded_name = uploaded.name
        st.session_state.file_type = "docx"
        for key in (
            "df",
            "findings",
            "redacted_df",
            "crosswalk",
            "docx_buffer",
            "docx_findings",
            "docx_blocks",
            "docx_crosswalk",
        ):
            st.session_state.pop(key, None)

    st.subheader("Configuration")
    with st.expander("Advanced settings", expanded=True):
        threshold = st.slider(
            "Confidence threshold",
            min_value=0.1,
            max_value=1.0,
            value=settings.default_threshold,
            step=0.05,
            help="Lower values flag more text (fewer missed names, more false positives).",
            key="docx_threshold",
        )
        entity_options = st.multiselect(
            "Entity types to pseudonymize",
            options=list(settings.supported_entities),
            default=list(settings.supported_entities),
            key="docx_entities",
        )
        custom_words_input = st.text_area(
            "Additional words/phrases to redact (optional)",
            help=(
                "One per line. Redacted in addition to detected "
                "names/organizations/emails, even if not in the master list - "
                "useful for a one-off sensitive term (e.g. a project codename). "
                "Not saved anywhere; re-enter next time if needed."
            ),
            key="docx_custom_words",
        )
        render_master_list_status(
            name_counts,
            quality_issues,
            settings.master_list_file,
            on_refresh=on_refresh_master_list,
        )

    if st.button("Pseudonymize Word document", type="primary", width="stretch"):
        uploaded.seek(0)
        custom_words = [w.strip() for w in custom_words_input.splitlines() if w.strip()]
        with st.spinner("Scanning document for PII..."):
            result = docx_service.execute(
                uploaded, entity_options, threshold, custom_words=custom_words
            )
        st.session_state.docx_buffer = result.data
        st.session_state.docx_findings = result.findings
        st.session_state.docx_blocks = result.block_count
        st.session_state.docx_crosswalk = result.crosswalk

    if "docx_buffer" not in st.session_state or st.session_state.docx_buffer is None:
        st.stop()

    docx_findings = st.session_state.docx_findings
    n_entities = len(docx_findings)

    if n_entities == 0:
        st.info("No PII was detected in this document. The file is already clean.")
        st.stop()

    st.success(f"Found {n_entities} PII instance(s) in this document.")

    base_name = re.sub(r"[^\w\-]", "_", uploaded.name.rsplit(".", 1)[0])
    render_crosswalk_section(
        st.session_state.docx_crosswalk, base_name, key_prefix="docx"
    )

    with st.expander(f"Detection details ({n_entities} finding(s))"):
        st.dataframe(
            docx_findings_dataframe(docx_findings), width="stretch", hide_index=True
        )

    st.subheader("Download")
    st.download_button(
        label="Download pseudonymized Word document",
        data=st.session_state.docx_buffer,
        file_name=f"{base_name}_pseudonymized.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        type="primary",
        width="stretch",
    )
    st.caption(
        "Detected names and organizations are replaced with their pseudonyms "
        "(e.g. STF-91345) directly in the document text."
    )
