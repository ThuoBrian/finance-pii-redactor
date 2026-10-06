"""Streamlit flow for PDF pseudonymization.

Thin presentation: handles session state and widgets, delegates the whole
pseudonymize pipeline to :class:`RedactPdfService`, and renders the summary
via ``presenters``. PDF uses the same spaCy-backed engine as Excel and Word:
names and organizations (curated or not), emails, websites, bank/payment
details and addresses. It also blacks out embedded images/logos by default
and removes external link targets. The words box below covers anything the
model misses (a codename, a case number), the same role it plays in Word.

This flow has no entity multiselect and no confidence threshold (so no
Advanced settings panel): PDF runs with fixed settings, and false positives are unticked in the review table.
It shows the master-list status panel, because a PDF redacted against an
empty or unsynced list would leave curated names with flagged IDs only.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Literal

import streamlit as st

from finance_redactor.application.redact_pdf import RedactionStyle, RedactPdfService
from finance_redactor.config import Settings
from finance_redactor.domain.errors import EncryptedPdfError, UnreadableFileError
from finance_redactor.domain.quality import QualityIssue
from finance_redactor.presentation.crosswalk_view import (
    render_pdf_mapping_section,
    render_pdf_mapping_warnings,
)
from finance_redactor.presentation.exclusion_view import (
    render_deselect_editor,
    render_exclusion_warning,
)
from finance_redactor.presentation.master_list_view import render_master_list_status
from finance_redactor.presentation.presenters import findings_dataframe, plural
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
            "pdf_links",
            "pdf_all_findings",
            "pdf_excluded_applied",
            "pdf_scan_result",
            "excel_bytes",
        ),
    )

    show_step(steps, 2)
    with st.container(border=True):
        st.subheader("2. Set options")
        # No "Advanced settings" here: PDF has no threshold or entity picker,
        # so everything left is a primary choice and stays visible.
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
                "redacting it would redact the tool's own output. Remove it "
                "unless the document genuinely contains that text for another "
                "reason."
            )

        button_label = (
            "Black out PDF" if style == RedactionStyle.BLACKOUT else "Pseudonymize PDF"
        )
        # Red/primary only before the first run - once a result exists, the
        # download button below becomes the one action that matters.
        main_button_type: Literal["primary", "secondary"] = (
            "secondary" if st.session_state.get("pdf_buffer") is not None else "primary"
        )
        if st.button(button_label, type=main_button_type, width="stretch"):
            uploaded.seek(0)
            try:
                with st.status("Scanning PDF...", expanded=False) as status:
                    scan_result = pdf_service.scan(uploaded)
                    uploaded.seek(0)
                    status.update(label="Building redacted PDF...")
                    result = pdf_service.redact(
                        uploaded,
                        scan_result,
                        custom_words,
                        style=style,
                        redact_images=redact_images,
                    )
                    status.update(label="Scan complete", state="complete")
            except EncryptedPdfError:
                st.error(
                    "This PDF is password-protected, so its pages can't be "
                    "read. Open it in a PDF reader, enter the password, save an "
                    "unlocked copy, and upload that copy instead."
                )
                st.stop()
            except UnreadableFileError:
                st.error(
                    "This file could not be read as a PDF. It may be corrupted, "
                    "or not really a .pdf file despite its name. Open it in a "
                    "PDF reader, save a fresh copy, and upload that instead."
                )
                st.stop()
            st.session_state.pdf_scan_result = scan_result
            st.session_state.pdf_buffer = result.data
            st.session_state.pdf_findings = result.findings
            st.session_state.pdf_pages = result.page_count
            st.session_state.pdf_crosswalk = result.crosswalk
            st.session_state.pdf_bracketed = result.source_bracketed_numbers
            st.session_state.pdf_links = result.removed_links
            # The unfiltered detections, kept as the deselect editor's stable
            # row list. Never overwritten by a re-run below, so a term can be
            # unticked and re-ticked; refiltering it would take the tick box
            # away with the row and strand the decision.
            st.session_state.pdf_all_findings = result.findings
            st.session_state.pdf_excluded_applied = frozenset()
            # The radio widget already stores pdf_style in session_state; do
            # not overwrite it after the widget has been instantiated.

        if "pdf_buffer" not in st.session_state or st.session_state.pdf_buffer is None:
            st.caption(
                "Click the button above to run it. Your results and download "
                "will appear here."
            )
            st.stop()

    pdf_findings = st.session_state.pdf_findings
    n_entities = len(pdf_findings)
    total_pages = st.session_state.pdf_pages
    removed_links = st.session_state.get("pdf_links", 0)
    base_name = sanitize_base_name(uploaded.name)
    style_value = st.session_state.get("pdf_style", RedactionStyle.PSEUDONYMIZE.value)

    show_step(steps, 3)
    with st.container(border=True):
        st.subheader("3. Review the results")

        images_requested = st.session_state.get("pdf_redact_images", True)
        if n_entities == 0 and not images_requested and not removed_links:
            st.info(
                "No names, emails, websites, addresses, or matching "
                f"words/phrases were found across {plural(total_pages, 'page')}."
            )
            st.stop()

        found_col, pages_col, links_col = st.columns(3)
        found_col.metric("Matches found", f"{n_entities:,}")
        pages_col.metric("Pages", f"{total_pages:,}")
        links_col.metric("Link targets removed", f"{removed_links:,}")
        if n_entities == 0:
            # Nothing text-based to report, but images may still have been
            # blacked out below (image redactions aren't tracked as findings).
            st.info(
                "No names, emails, websites, addresses, or matching "
                f"words/phrases were found across {plural(total_pages, 'page')}. "
                "Any images and link targets were still removed in the "
                "downloaded PDF."
            )
        elif style_value == RedactionStyle.BLACKOUT.value:
            st.caption("Matched areas will be blacked out in the downloaded PDF.")

        # Warnings stay above the tabs: an unresolved item is undecodable
        # later, which deserves to be seen without opening anything.
        if style_value != RedactionStyle.BLACKOUT.value:
            bracketed = st.session_state.get("pdf_bracketed", 0)
            if bracketed:
                st.warning(
                    "This document already contained "
                    f"{plural(bracketed, 'bracketed number')} of its own, such "
                    "as footnote markers or line-item numbers. Redaction labels "
                    "look the same ([001]), so a reader of the output may not "
                    "be able to tell which brackets are redactions. The label "
                    "mapping (Mapping tab) lists every label this tool "
                    "actually inserted."
                )
            render_pdf_mapping_warnings(st.session_state.pdf_crosswalk)

        tab_mapping, tab_details = st.tabs(["Mapping", "Details"])
        with tab_mapping:
            if style_value == RedactionStyle.BLACKOUT.value:
                st.caption(
                    "Black out leaves nothing to decode, so there is no mapping."
                )
            else:
                render_pdf_mapping_section(
                    st.session_state.pdf_crosswalk,
                    base_name,
                    master_list_fingerprint=master_list_fingerprint,
                )
        with tab_details:
            excluded = render_deselect_editor(
                st.session_state.get("pdf_all_findings", []),
                key_prefix="pdf",
                excluded=st.session_state.get("pdf_excluded_applied", frozenset()),
            )
            st.markdown(f"**All detections ({plural(n_entities, 'finding')})**")
            st.dataframe(
                findings_dataframe(pdf_findings, "Page"),
                width="stretch",
                hide_index=True,
            )

        if excluded != st.session_state.get("pdf_excluded_applied", frozenset()):
            # No detector call happens here at all: ``pdf_scan_result`` was
            # computed once, on the button click above, and this just reruns
            # the cheap, detector-free redaction-building/apply step over it
            # with the new exclude set.
            uploaded.seek(0)
            with st.spinner("Rebuilding the file without those terms..."):
                rerun = pdf_service.redact(
                    uploaded,
                    st.session_state.pdf_scan_result,
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

    show_step(steps, 4)
    with st.container(border=True):
        st.subheader("4. Download")
        render_exclusion_warning(
            st.session_state.get("pdf_excluded_applied", frozenset())
        )
        if style_value == RedactionStyle.BLACKOUT.value:
            label = "Download blacked-out PDF"
            file_name = f"{base_name}_blacked_out.pdf"
            caption = (
                "Matched text and selected images are covered with a black "
                "shade in the downloaded PDF."
            )
        else:
            label = "Download pseudonymized PDF"
            file_name = f"{base_name}_pseudonymized.pdf"
            caption = (
                "Matched words/phrases are replaced with a short label (e.g. "
                "[001]) directly in the PDF text layer."
            )
            if st.session_state.pdf_crosswalk:
                caption += (
                    " The label means nothing on its own - keep the label "
                    "mapping (Mapping tab) to decode it."
                )
            caption += (
                " Bank and payment details and addresses show as a fixed mask "
                "such as [ACCOUNT] or [ADDRESS], with nothing to decode."
            )
        if removed_links:
            caption += (
                f" {plural(removed_links, 'link target')} (websites, email "
                "addresses, files) removed; the link text stays, redacted "
                "where it matched."
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
