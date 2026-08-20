"""Streamlit flow for PDF pseudonymization.

Thin presentation: handles session state and widgets, delegates the whole
pseudonymize pipeline to :class:`RedactPdfService`, and renders the summary
via ``presenters``. Unlike Excel/Word, PDF has no spaCy-model or
master-list-based name/organization detection - that stays removed (a
deliberate team decision: unreliable guessing on scanned financial PDFs).
It does automatically detect email addresses and websites (deterministic
regex, not a guess - see ``infrastructure/detection/pattern_detector.py``)
and, by default, blacks out embedded images/logos; the words box below is a
supplement for anything else (names, codenames, case numbers), same role it
plays in Word. This flow still has no entity multiselect, no confidence
threshold, and no master-list status panel - none of that applies here.
"""

from __future__ import annotations

import re
from typing import Any

import streamlit as st

from finance_redactor.application.redact_pdf import RedactionStyle, RedactPdfService
from finance_redactor.presentation.crosswalk_view import render_crosswalk_section
from finance_redactor.presentation.presenters import pdf_findings_dataframe


def run_pdf_flow(uploaded: Any, *, pdf_service: RedactPdfService) -> None:
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
                "Pseudonymize replaces matched text with stable IDs like "
                "CST-AUTO-3F9A1. Black out covers matched text and images "
                "with a black shade."
            ),
            key="pdf_style",
        )
        custom_words_input = st.text_area(
            "Additional words/phrases to redact (optional)",
            help=(
                "One per line. Email addresses and websites are already caught "
                "automatically. Add anything else you want covered too - e.g. a "
                "name, a project codename, a case number. Not saved anywhere; "
                "re-enter next time if needed."
            ),
            key="pdf_custom_words",
        )
        redact_images = st.checkbox(
            "Also black out images / logos",
            value=True,
            help=(
                "Covers every image on each page with a black box, in either "
                "redaction style. Only embedded raster images count as "
                '"logos" - a logo drawn as vector art (lines/shapes, not a '
                "picture) won't be caught."
            ),
            key="pdf_redact_images",
        )

    custom_words = [w.strip() for w in custom_words_input.splitlines() if w.strip()]

    button_label = (
        "Black out PDF" if style == RedactionStyle.BLACKOUT else "Pseudonymize PDF"
    )
    if st.button(button_label, type="primary", width="stretch"):
        uploaded.seek(0)
        with st.spinner("Scanning PDF..."):
            result = pdf_service.execute(
                uploaded,
                custom_words,
                style=style,
                redact_images=redact_images,
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

    images_requested = st.session_state.get("pdf_redact_images", True)
    if n_entities == 0 and not images_requested:
        st.info(
            "No emails, websites, or matching words/phrases were found across "
            f"{total_pages} page(s)."
        )
        st.stop()

    style_value = st.session_state.get("pdf_style", RedactionStyle.PSEUDONYMIZE.value)
    if n_entities == 0:
        # Nothing text-based to report, but images may still have been
        # blacked out below (image redactions aren't tracked as findings).
        st.info(
            "No emails, websites, or matching words/phrases were found across "
            f"{total_pages} page(s). Any images on the page(s) were still "
            "blacked out in the downloaded PDF."
        )
    elif style_value == RedactionStyle.BLACKOUT.value:
        st.success(
            f"Found {n_entities} match(es) across {total_pages} page(s); "
            "matched areas will be blacked out in the downloaded PDF."
        )
    else:
        st.success(f"Found {n_entities} match(es) across {total_pages} page(s).")

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
            "Matched text and selected images are covered with a black shade "
            "in the downloaded PDF."
        )
    else:
        label = "Download pseudonymized PDF"
        file_name = f"{base_name}_pseudonymized.pdf"
        caption = (
            "Matched words/phrases are replaced with their pseudonyms "
            "(e.g. CST-AUTO-3F9A1) directly in the PDF text layer."
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
