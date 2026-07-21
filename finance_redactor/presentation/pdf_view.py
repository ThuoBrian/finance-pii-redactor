"""Streamlit flow for PDF pseudonymization.

Thin presentation: handles session state and widgets, delegates the whole
detect-and-pseudonymize pipeline to :class:`RedactPdfService`, and renders the
summary via ``presenters``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

import streamlit as st

from finance_redactor.application.redact_pdf import RedactionStyle, RedactPdfService
from finance_redactor.config import Settings
from finance_redactor.presentation.crosswalk_view import render_crosswalk_section
from finance_redactor.presentation.presenters import pdf_findings_dataframe


def _name_list_help(counts: Mapping[str, int]) -> str:
    total = sum(counts.values())
    by_cat = ", ".join(f"{n:,} {cat}" for cat, n in sorted(counts.items())) or "none"
    return (
        f"Loaded {total:,} master-list entr(y/ies): {by_cat}. Edit "
        "`data/Names List - Organized.xlsx` "
        "and refresh the page to update it."
    )


def run_pdf_flow(
    uploaded: Any,
    *,
    pdf_service: RedactPdfService,
    settings: Settings,
    name_counts: Mapping[str, int],
) -> None:
    """Render the PDF pseudonymization flow in Streamlit."""
    if (
        st.session_state.get("uploaded_name") != uploaded.name
        or st.session_state.get("file_type") != "pdf"
    ):
        st.session_state.uploaded_name = uploaded.name
        st.session_state.file_type = "pdf"
        for key in (
            "df",
            "findings",
            "redacted_df",
            "crosswalk",
            "pdf_buffer",
            "pdf_findings",
            "pdf_pages",
            "pdf_crosswalk",
        ):
            st.session_state.pop(key, None)

    st.subheader("Configuration")
    with st.expander("Advanced settings", expanded=True):
        style = st.radio(
            "Redaction style",
            options=[RedactionStyle.PSEUDONYMIZE, RedactionStyle.BLACKOUT],
            format_func=lambda s: (
                "Pseudonymize (replace with stable IDs)"
                if s == RedactionStyle.PSEUDONYMIZE
                else "Black out (cover with black boxes)"
            ),
            help=(
                "Pseudonymize replaces names with stable IDs like STF-91345. "
                "Black out covers detected text and images with a black shade."
            ),
            key="pdf_style",
        )
        threshold = st.slider(
            "Confidence threshold",
            min_value=0.1,
            max_value=1.0,
            value=settings.default_threshold,
            step=0.05,
            help="Lower values flag more text (fewer missed names, more false positives).",
            key="pdf_threshold",
        )
        entity_options = st.multiselect(
            "Text to redact",
            options=list(settings.supported_entities),
            default=list(settings.supported_entities),
            key="pdf_entities",
        )
        redact_images = st.checkbox(
            "Also black out images / logos",
            value=False,
            help=(
                "Covers every image on each page with a black box. Only applies "
                "when Black out is selected; in Pseudonymize mode this is ignored."
            ),
            key="pdf_redact_images",
        )
        st.markdown("**Master list**")
        st.caption(_name_list_help(name_counts))

    button_label = (
        "Black out PDF" if style == RedactionStyle.BLACKOUT else "Pseudonymize PDF"
    )
    if st.button(button_label, type="primary", width="stretch"):
        uploaded.seek(0)
        with st.spinner("Scanning PDF for PII..."):
            result = pdf_service.execute(
                uploaded,
                entity_options,
                threshold,
                style=style,
                redact_images=(redact_images and style == RedactionStyle.BLACKOUT),
            )
        st.session_state.pdf_buffer = result.data
        st.session_state.pdf_findings = result.findings
        st.session_state.pdf_pages = result.page_count
        st.session_state.pdf_crosswalk = result.crosswalk
        # The radio widget already stores pdf_style in session_state; do not
        # overwrite it after the widget has been instantiated.

    if "pdf_buffer" not in st.session_state or st.session_state.pdf_buffer is None:
        st.stop()

    pdf_findings = st.session_state.pdf_findings
    n_entities = len(pdf_findings)
    total_pages = st.session_state.pdf_pages

    if n_entities == 0:
        st.info(
            f"No PII was detected across {total_pages} page(s). The file is already clean."
        )
        st.stop()

    style_value = st.session_state.get("pdf_style", RedactionStyle.PSEUDONYMIZE.value)
    if style_value == RedactionStyle.BLACKOUT.value:
        st.success(
            f"Found {n_entities} PII instance(s) across {total_pages} page(s); "
            "detected areas will be blacked out in the downloaded PDF."
        )
    else:
        st.success(f"Found {n_entities} PII instance(s) across {total_pages} page(s).")

    base_name = re.sub(r"[^\w\-]", "_", uploaded.name.rsplit(".", 1)[0])
    render_crosswalk_section(
        st.session_state.pdf_crosswalk, base_name, key_prefix="pdf"
    )

    with st.expander(f"Detection details ({n_entities} finding(s))"):
        st.dataframe(
            pdf_findings_dataframe(pdf_findings), width="stretch", hide_index=True
        )

    st.subheader("Download")
    if style_value == RedactionStyle.BLACKOUT.value:
        label = "Download blacked-out PDF"
        file_name = f"{base_name}_blacked_out.pdf"
        caption = (
            "Detected text and selected images are covered with a black shade "
            "in the downloaded PDF."
        )
    else:
        label = "Download pseudonymized PDF"
        file_name = f"{base_name}_pseudonymized.pdf"
        caption = (
            "Detected names and organizations are replaced with their pseudonyms "
            "(e.g. STF-91345) directly in the PDF text layer."
        )
    st.download_button(
        label=label,
        data=st.session_state.pdf_buffer,
        file_name=file_name,
        mime="application/pdf",
        type="primary",
        width="stretch",
    )
    st.caption(caption)
