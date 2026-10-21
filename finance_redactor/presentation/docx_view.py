"""Streamlit flow for Word (.docx) pseudonymization.

Thin presentation: handles session state and widgets, delegates the whole
detect-and-pseudonymize pipeline to :class:`RedactDocxService`, and renders the
summary via ``presenters``. Pseudonymize-only (no blackout mode) - Word text
stays fully editable, matching the Excel flow rather than the PDF flow.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

from finance_redactor.application.redact_docx import RedactDocxService
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
    THRESHOLD_HELP,
    entity_label,
    findings_dataframe,
    plural,
    review_tab_labels,
)
from finance_redactor.presentation.session import (
    output_stem,
    reset_on_new_upload,
)
from finance_redactor.presentation.steps import show_step


def run_docx_flow(
    uploaded: Any,
    *,
    docx_service: RedactDocxService,
    settings: Settings,
    steps: Any,
) -> None:
    """Render the Word flow: Options, Review and Download (see ``wizard``)."""
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
            "docx_run_words",
            "excel_bytes",
        ),
    )
    if (
        wizard.current() == wizard.OPTIONS
        or st.session_state.get("docx_buffer") is None
    ):
        _options_step(uploaded, docx_service, settings, steps)
        return
    if wizard.current() == wizard.REVIEW:
        _review_step(uploaded, docx_service, steps)
        return
    _download_step(steps)


def _options_step(
    uploaded: Any, docx_service: RedactDocxService, settings: Settings, steps: Any
) -> None:
    show_step(steps, 2)
    st.subheader("Options")
    st.caption(
        "Names, organizations, emails, websites, bank details and addresses "
        "are found automatically."
    )
    # Values live in session state (seeded here, kept by wizard.keep_option_
    # choices), never in a widget default: passing both raises a warning.
    state = st.session_state
    state.setdefault("docx_custom_words", "")
    state.setdefault("docx_threshold", settings.default_threshold)
    state.setdefault("docx_entities", list(settings.supported_entities))

    with st.expander("Customize: words to add, kinds of information, confidence"):
        st.text_area(
            "Words or phrases to add (optional)",
            help=(
                "One per line. Redacted in addition to detected "
                "names/organizations/emails, even if not in the master list - "
                "useful for a one-off sensitive term (e.g. a project codename). "
                "Not saved anywhere; re-enter next time if needed."
            ),
            key="docx_custom_words",
        )
        st.slider(
            "Confidence threshold",
            min_value=0.1,
            max_value=1.0,
            step=0.05,
            help=THRESHOLD_HELP,
            key="docx_threshold",
        )
        st.multiselect(
            "Kinds of information to hide",
            options=list(settings.supported_entities),
            format_func=entity_label,
            help=ENTITY_HELP,
            key="docx_entities",
        )

    custom_words = [
        w.strip() for w in state["docx_custom_words"].splitlines() if w.strip()
    ]
    if st.button("Redact my file", type="primary", width="stretch"):
        uploaded.seek(0)
        try:
            with st.status("Scanning the document...", expanded=False) as status:
                scan_result = docx_service.scan(
                    uploaded,
                    list(state["docx_entities"]),
                    float(state["docx_threshold"]),
                )
                uploaded.seek(0)
                status.update(label="Replacing names with codes...")
                result = docx_service.redact(uploaded, scan_result, custom_words)
        except UnreadableFileError:
            st.error(
                "This file could not be read as a Word document. It may be "
                "corrupted, or not really a .docx file despite its name. "
                "Open it in Word, save a fresh copy, and upload that "
                "instead."
            )
            return
        state.docx_scan_result = scan_result
        state.docx_buffer = result.data
        state.docx_findings = result.findings
        state.docx_blocks = result.block_count
        state.docx_crosswalk = result.crosswalk
        state.docx_links = result.removed_links
        # Unfiltered baseline for the deselect editor - see pdf_view for
        # why this must not be refiltered on a re-run.
        state.docx_all_findings = result.findings
        state.docx_excluded_applied = frozenset()
        # The words this result was built with; the later steps read these,
        # not the text box, which is only drawn on Options.
        state.docx_run_words = custom_words
        wizard.go(wizard.REVIEW)


def _review_step(uploaded: Any, docx_service: RedactDocxService, steps: Any) -> None:
    state = st.session_state
    docx_findings = state.docx_findings
    n_entities = len(docx_findings)
    removed_links = state.get("docx_links", 0)

    show_step(steps, 3)
    st.subheader("Review what was found")
    st.caption(
        f"{plural(n_entities, 'term')} found"
        + (
            f" · {plural(removed_links, 'hyperlink target')} removed"
            if removed_links
            else ""
        )
    )
    if n_entities == 0:
        st.info(
            "Nothing was detected in the text."
            + (
                " The download still has the hyperlink targets removed."
                if removed_links
                else ""
            )
        )

    review_findings = state.get("docx_all_findings", [])
    tab_review, tab_mapping, tab_occurrences = st.tabs(
        review_tab_labels(review_findings)
    )
    with tab_mapping:
        render_crosswalk_section(state.docx_crosswalk)
    with tab_review:
        excluded = render_deselect_editor(
            review_findings,
            key_prefix="docx",
            excluded=state.get("docx_excluded_applied", frozenset()),
        )
    with tab_occurrences:
        st.markdown(f"**All detections ({plural(n_entities, 'finding')})**")
        st.dataframe(
            findings_dataframe(docx_findings, "Paragraph"),
            width="stretch",
            hide_index=True,
        )

    if excluded != state.get("docx_excluded_applied", frozenset()):
        # The scan/redact split (see redact_docx.py) means this never re-runs
        # spaCy - only the per-block dedupe/exclude/assign/apply step reruns,
        # over the cached DocxScanResult from the Redact click.
        uploaded.seek(0)
        with st.spinner("Rebuilding without those terms..."):
            rerun = docx_service.redact(
                uploaded,
                state.docx_scan_result,
                state.docx_run_words,
                exclude=excluded,
            )
        state.docx_buffer = rerun.data
        state.docx_findings = rerun.findings
        state.docx_crosswalk = rerun.crosswalk
        state.docx_excluded_applied = excluded
        st.rerun()

    wizard.nav(
        back=("Back to options", wizard.OPTIONS),
        forward=("Continue to download", wizard.DOWNLOAD),
        hold=unapplied_changes_note(
            "docx", state.get("docx_excluded_applied", frozenset())
        ),
    )


def _download_step(steps: Any) -> None:
    state = st.session_state
    removed_links = state.get("docx_links", 0)
    base_name = output_stem()

    show_step(steps, 4)
    st.subheader("Download")
    render_exclusion_warning(state.get("docx_excluded_applied", frozenset()))
    safe, private = wizard.download_cards()
    with safe:
        st.download_button(
            label="Download redacted Word document",
            data=state.docx_buffer,
            file_name=f"{base_name}.docx",
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            type="primary",
            width="stretch",
        )
        caption = (
            "Names are replaced with codes such as STF-10010. Bank and payment "
            "details and addresses show as a mask such as [ACCOUNT]."
        )
        if removed_links:
            caption += (
                f" {plural(removed_links, 'hyperlink target')} removed; the "
                "link text stays, redacted where it matched."
            )
        st.caption(caption)
    with private:
        render_crosswalk_download(state.docx_crosswalk, base_name, key_prefix="docx")

    wizard.nav(back=("Back to review", wizard.REVIEW), finish=True)
