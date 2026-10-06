"""Streamlit flow for Word (.docx) pseudonymization.

Thin presentation: handles session state and widgets, delegates the whole
detect-and-pseudonymize pipeline to :class:`RedactDocxService`, and renders the
summary via ``presenters``. Pseudonymize-only (no blackout mode) - Word text
stays fully editable, matching the Excel flow rather than the PDF flow.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal

import streamlit as st

from finance_redactor.application.redact_docx import RedactDocxService
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
    THRESHOLD_HELP,
    entity_label,
    findings_dataframe,
    plural,
)
from finance_redactor.presentation.session import (
    reset_on_new_upload,
    sanitize_base_name,
)
from finance_redactor.presentation.steps import show_step


def run_docx_flow(
    uploaded: Any,
    *,
    docx_service: RedactDocxService,
    settings: Settings,
    name_counts: Mapping[str, int],
    quality_issues: Sequence[QualityIssue] | None = None,
    on_refresh_master_list: Callable[[], None] | None = None,
    steps: Any,
) -> None:
    """Render the Word (.docx) pseudonymization flow in Streamlit."""
    reset_on_new_upload(
        uploaded,
        "docx",
        (
            "df",
            "findings",
            "redacted_df",
            "crosswalk",
            "docx_buffer",
            "docx_findings",
            "docx_blocks",
            "docx_crosswalk",
            "docx_links",
            "docx_all_findings",
            "docx_excluded_applied",
            "docx_scan_result",
            "excel_bytes",
        ),
    )

    show_step(steps, 2)
    with st.container(border=True):
        st.subheader("2. Set options")
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
        # Above the expander so a master-list data-quality warning is never
        # hidden behind a collapsed panel.
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
                key="docx_threshold",
            )
            entity_options = st.multiselect(
                "Kinds of information to hide",
                options=list(settings.supported_entities),
                default=list(settings.supported_entities),
                format_func=entity_label,
                help=ENTITY_HELP,
                key="docx_entities",
            )

        custom_words = [w.strip() for w in custom_words_input.splitlines() if w.strip()]

        # Red/primary only before the first run - once a result exists, the
        # download button below becomes the one action that matters.
        main_button_type: Literal["primary", "secondary"] = (
            "secondary"
            if st.session_state.get("docx_buffer") is not None
            else "primary"
        )
        if st.button(
            "Pseudonymize Word document", type=main_button_type, width="stretch"
        ):
            uploaded.seek(0)
            try:
                with st.status(
                    "Scanning document for PII...", expanded=False
                ) as status:
                    scan_result = docx_service.scan(uploaded, entity_options, threshold)
                    uploaded.seek(0)
                    status.update(label="Applying pseudonyms...")
                    result = docx_service.redact(uploaded, scan_result, custom_words)
                    status.update(label="Scan complete", state="complete")
            except UnreadableFileError:
                st.error(
                    "This file could not be read as a Word document. It may be "
                    "corrupted, or not really a .docx file despite its name. "
                    "Open it in Word, save a fresh copy, and upload that "
                    "instead."
                )
                st.stop()
            st.session_state.docx_scan_result = scan_result
            st.session_state.docx_buffer = result.data
            st.session_state.docx_findings = result.findings
            st.session_state.docx_blocks = result.block_count
            st.session_state.docx_crosswalk = result.crosswalk
            st.session_state.docx_links = result.removed_links
            # Unfiltered baseline for the deselect editor - see pdf_view for
            # why this must not be refiltered on a re-run.
            st.session_state.docx_all_findings = result.findings
            st.session_state.docx_excluded_applied = frozenset()

        if (
            "docx_buffer" not in st.session_state
            or st.session_state.docx_buffer is None
        ):
            st.caption(
                "Click the button above to run it. Your results and download "
                "will appear here."
            )
            st.stop()

    docx_findings = st.session_state.docx_findings
    n_entities = len(docx_findings)
    removed_links = st.session_state.get("docx_links", 0)
    base_name = sanitize_base_name(uploaded.name)

    show_step(steps, 3)
    with st.container(border=True):
        st.subheader("3. Review the results")
        if n_entities == 0 and not removed_links:
            st.info("No PII was detected in this document. The file is already clean.")
            st.stop()

        found_col, links_col = st.columns(2)
        found_col.metric("PII instances found", f"{n_entities:,}")
        links_col.metric("Hyperlink targets removed", f"{removed_links:,}")
        if n_entities == 0:
            # The original still carries the link targets, so it is not clean.
            st.info(
                "No PII was detected in the text, but the document had "
                f"{plural(removed_links, 'hyperlink target')}. Download the "
                "copy below, which has them removed."
            )

        tab_mapping, tab_details = st.tabs(["Mapping", "Details"])
        with tab_mapping:
            render_crosswalk_section(
                st.session_state.docx_crosswalk, base_name, key_prefix="docx"
            )
        with tab_details:
            excluded = render_deselect_editor(
                st.session_state.get("docx_all_findings", []),
                key_prefix="docx",
                excluded=st.session_state.get("docx_excluded_applied", frozenset()),
            )
            st.markdown(f"**All detections ({plural(n_entities, 'finding')})**")
            st.dataframe(
                findings_dataframe(docx_findings, "Paragraph"),
                width="stretch",
                hide_index=True,
            )

        if excluded != st.session_state.get("docx_excluded_applied", frozenset()):
            # Now the cheap case: the scan/redact split (see redact_docx.py)
            # means this never re-runs spaCy - only the per-block
            # dedupe/exclude/assign/apply step reruns, over the cached
            # DocxScanResult from the button handler above.
            uploaded.seek(0)
            with st.spinner("Re-scanning the document without those terms..."):
                rerun = docx_service.redact(
                    uploaded,
                    st.session_state.docx_scan_result,
                    custom_words,
                    exclude=excluded,
                )
            st.session_state.docx_buffer = rerun.data
            st.session_state.docx_findings = rerun.findings
            st.session_state.docx_crosswalk = rerun.crosswalk
            st.session_state.docx_excluded_applied = excluded
            st.rerun()

    show_step(steps, 4)
    with st.container(border=True):
        st.subheader("4. Download")
        render_exclusion_warning(
            st.session_state.get("docx_excluded_applied", frozenset())
        )
        st.download_button(
            label="Download pseudonymized Word document",
            data=st.session_state.docx_buffer,
            file_name=f"{base_name}_pseudonymized.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            type="primary",
            width="stretch",
        )
        caption = (
            "Detected names and organizations are replaced with their "
            "pseudonyms (e.g. STF-10010) directly in the document text. Bank "
            "and payment details and addresses show as a fixed mask such as "
            "[ACCOUNT] or [ADDRESS], with nothing to decode."
        )
        if removed_links:
            caption += (
                f" {plural(removed_links, 'hyperlink target')} removed; the "
                "link text stays, pseudonymized where it matched."
            )
        st.caption(caption)
