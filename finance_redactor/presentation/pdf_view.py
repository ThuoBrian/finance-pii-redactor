"""Streamlit flow for PDF pseudonymization.

Thin presentation: handles session state and widgets, delegates the whole
pseudonymize pipeline to :class:`RedactPdfService`, and renders the summary
via ``presenters``. PDF detects everything that can be matched
deterministically - emails and websites by regex, curated master-list names
by exact automaton match (see
``infrastructure/detection/pattern_detector.py``) - and by default blacks out
embedded images/logos. What stays removed is the spaCy model, whose
statistical guessing is unreliable on scanned financial PDFs, so the words
box below covers anything not yet on the master list (a new name, a
codename, a case number), the same role it plays in Word.

This flow still has no entity multiselect and no confidence threshold:
neither applies to exact matching. It *does* show the master-list status
panel, because the master list now drives detection here too - a PDF
redacted against an empty or unsynced list would silently leave curated
names in place, and that panel is what makes it visible.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import streamlit as st

from finance_redactor.application.redact_pdf import RedactionStyle, RedactPdfService
from finance_redactor.config import Settings
from finance_redactor.domain.errors import EncryptedPdfError
from finance_redactor.domain.quality import QualityIssue
from finance_redactor.presentation.crosswalk_view import render_pdf_mapping_section
from finance_redactor.presentation.exclusion_view import (
    render_deselect_editor,
    render_exclusion_warning,
)
from finance_redactor.presentation.master_list_view import render_master_list_status
from finance_redactor.presentation.presenters import findings_dataframe
from finance_redactor.presentation.session import (
    reset_on_new_upload,
    sanitize_base_name,
)
from finance_redactor.presentation.steps import show_step

# A typed word that is itself a label, e.g. "[001]". Redacting it would mean
# redacting this tool's own output on a second pass.
_LABEL_SHAPED = re.compile(r"^\[\d+\]$")


def run_pdf_flow(
    uploaded: Any,
    *,
    pdf_service: RedactPdfService,
    settings: Settings,
    name_counts: Mapping[str, int],
    quality_issues: Sequence[QualityIssue] | None = None,
    on_refresh_master_list: Callable[[], None] | None = None,
    master_list_fingerprint: str = "",
    steps: Any,
) -> None:
    """Render the PDF pseudonymization flow in Streamlit.

    ``master_list_fingerprint`` identifies which master list the mapping
    decodes against, and is stamped into the downloaded CSV. See
    ``presenters.pdf_mapping_dataframe``.
    """
    reset_on_new_upload(
        uploaded,
        "pdf",
        (
            "df",
            "findings",
            "redacted_df",
            "crosswalk",
            "pdf_buffer",
            "pdf_findings",
            "pdf_pages",
            "pdf_crosswalk",
            "pdf_bracketed",
            "pdf_all_findings",
            "pdf_excluded_applied",
        ),
    )

    show_step(steps, 2)
    st.subheader("2. Set options")
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
                "Pseudonymize replaces matched text with a short label like "
                "[001], and gives you a separate file saying which Internal ID "
                "each label stands for. Black out covers matched text and "
                "images with a black shade instead, with nothing to decode."
            ),
            key="pdf_style",
        )
        custom_words_input = st.text_area(
            "Additional words/phrases to redact (optional)",
            help=(
                "One per line. Email addresses, websites, and any name already "
                "on the master list are caught automatically - you don't need "
                "to list those. Use this for anything else: a name not yet on "
                "the master list, a project codename, a case number. Not saved "
                "anywhere; re-enter next time if needed."
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
        render_master_list_status(
            name_counts,
            quality_issues,
            settings.master_list_file,
            on_refresh=on_refresh_master_list,
        )

    custom_words = [w.strip() for w in custom_words_input.splitlines() if w.strip()]
    if any(_LABEL_SHAPED.match(w) for w in custom_words):
        st.warning(
            "One of your words to redact looks like a redaction label (e.g. "
            "`[001]`). That is the shape this tool writes into the PDF, so "
            "redacting it would redact the tool's own output. Remove it unless "
            "the document genuinely contains that text for another reason."
        )

    button_label = (
        "Black out PDF" if style == RedactionStyle.BLACKOUT else "Pseudonymize PDF"
    )
    if st.button(button_label, type="primary", width="stretch"):
        uploaded.seek(0)
        try:
            with st.spinner("Scanning PDF..."):
                result = pdf_service.execute(
                    uploaded,
                    custom_words,
                    style=style,
                    redact_images=redact_images,
                )
        except EncryptedPdfError:
            st.error(
                "This PDF is password-protected, so its pages can't be read. "
                "Open it in a PDF reader, enter the password, save an "
                "unlocked copy, and upload that copy instead."
            )
            st.stop()
        st.session_state.pdf_buffer = result.data
        st.session_state.pdf_findings = result.findings
        st.session_state.pdf_pages = result.page_count
        st.session_state.pdf_crosswalk = result.crosswalk
        st.session_state.pdf_bracketed = result.source_bracketed_numbers
        # The unfiltered detections, kept as the deselect editor's stable row
        # list. Never overwritten by a re-run below, so a term can be unticked
        # and re-ticked; refiltering it would take the tick box away with the
        # row and strand the decision.
        st.session_state.pdf_all_findings = result.findings
        st.session_state.pdf_excluded_applied = frozenset()
        # The radio widget already stores pdf_style in session_state; do not
        # overwrite it after the widget has been instantiated.

    if "pdf_buffer" not in st.session_state or st.session_state.pdf_buffer is None:
        st.caption(
            "Click the button above to run it. Your results and download will "
            "appear here."
        )
        st.stop()

    pdf_findings = st.session_state.pdf_findings
    n_entities = len(pdf_findings)
    total_pages = st.session_state.pdf_pages
    show_step(steps, 3)
    st.subheader("3. Review the results")

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

    base_name = sanitize_base_name(uploaded.name)
    if style_value != RedactionStyle.BLACKOUT.value:
        bracketed = st.session_state.get("pdf_bracketed", 0)
        if bracketed:
            st.warning(
                f"This document already contained {bracketed} bracketed "
                "number(s) of its own, such as footnote markers or line-item "
                "numbers. Redaction labels look the same ([001]), so a reader "
                "of the output may not be able to tell which brackets are "
                "redactions. The label mapping below lists every label this "
                "tool actually inserted."
            )
        render_pdf_mapping_section(
            st.session_state.pdf_crosswalk,
            base_name,
            master_list_fingerprint=master_list_fingerprint,
        )

    excluded = render_deselect_editor(
        st.session_state.get("pdf_all_findings", []),
        key_prefix="pdf",
        excluded=st.session_state.get("pdf_excluded_applied", frozenset()),
    )
    if excluded != st.session_state.get("pdf_excluded_applied", frozenset()):
        # Re-redacting is the whole cost of a tick change here, and it is
        # cheap: the PDF detector never loads spaCy (see
        # infrastructure/detection/pattern_detector.py's _NullNlpEngine).
        uploaded.seek(0)
        with st.spinner("Rebuilding the file without those terms..."):
            rerun = pdf_service.execute(
                uploaded,
                custom_words,
                style=style,
                redact_images=redact_images,
                exclude=excluded,
            )
        st.session_state.pdf_buffer = rerun.data
        st.session_state.pdf_findings = rerun.findings
        st.session_state.pdf_crosswalk = rerun.crosswalk
        st.session_state.pdf_excluded_applied = excluded
        st.rerun()

    with st.expander(f"Detection details ({n_entities} finding(s))"):
        st.dataframe(
            findings_dataframe(pdf_findings, "Page"), width="stretch", hide_index=True
        )

    show_step(steps, 4)
    st.subheader("4. Download")
    render_exclusion_warning(st.session_state.get("pdf_excluded_applied", frozenset()))
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
            "Matched words/phrases are replaced with a short label (e.g. "
            "[001]) directly in the PDF text layer. The label means nothing "
            "on its own - keep the label mapping above to decode it."
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
