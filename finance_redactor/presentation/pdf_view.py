"""Streamlit flow for PDF pseudonymization.

Thin presentation: handles session state and widgets, delegates the whole
pseudonymize pipeline to :class:`RedactPdfService`, and renders the summary
via ``presenters``. PDF uses the same spaCy-backed engine as Excel and Word:
names and organizations (curated or not), emails, websites, bank/payment
details and addresses. It also blacks out embedded images/logos by default
and removes external link targets. The words box below covers anything the
model misses (a codename, a case number), the same role it plays in Word.

This flow has no entity multiselect and no confidence threshold: PDF runs
with fixed settings, and false positives are unticked in the review table.
The master-list card in the sidebar shows whether the list is loaded: a PDF
redacted against an empty or unsynced list would leave curated names with
flagged IDs only.
"""

from __future__ import annotations

import re
from typing import Any

import streamlit as st

from finance_redactor.application.redact_pdf import RedactionStyle, RedactPdfService
from finance_redactor.domain.errors import EncryptedPdfError, UnreadableFileError
from finance_redactor.presentation import wizard
from finance_redactor.presentation.crosswalk_view import (
    PDF_NAMES_TOGGLE_KEY,
    render_pdf_mapping_download,
    render_pdf_mapping_section,
    render_pdf_mapping_warnings,
    render_pdf_names_download,
)
from finance_redactor.presentation.exclusion_view import (
    render_deselect_editor,
    render_exclusion_warning,
)
from finance_redactor.presentation.presenters import (
    findings_dataframe,
    plural,
    review_tab_labels,
    scanned_pages_warning,
)
from finance_redactor.presentation.session import (
    output_stem,
    reset_on_new_upload,
)
from finance_redactor.presentation.steps import show_step

# A typed word that is itself a label, e.g. "[001]". Redacting it would mean
# redacting this tool's own output on a second pass.
_LABEL_SHAPED = re.compile(r"^\[\d+\]$")


def run_pdf_flow(
    uploaded: Any,
    *,
    pdf_service: RedactPdfService,
    master_list_fingerprint: str = "",
    steps: Any,
) -> None:
    """Render the PDF flow: Options, Review and Download (see ``wizard``).

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
            PDF_NAMES_TOGGLE_KEY,
            "pdf_bracketed",
            "pdf_links",
            "pdf_all_findings",
            "pdf_excluded_applied",
            "pdf_scan_result",
            "pdf_run",
            "excel_bytes",
        ),
    )
    if wizard.current() == wizard.OPTIONS or st.session_state.get("pdf_buffer") is None:
        _options_step(uploaded, pdf_service, steps)
        return
    if wizard.current() == wizard.REVIEW:
        _review_step(uploaded, pdf_service, steps)
        return
    _download_step(master_list_fingerprint, steps)


def _options_step(uploaded: Any, pdf_service: RedactPdfService, steps: Any) -> None:
    show_step(steps, 2)
    st.subheader("Options")
    st.caption(
        "Names, organizations, emails, websites, bank details and addresses "
        "are found automatically. Images are blacked out."
    )
    # Values live in session state (seeded here, kept by wizard.keep_option_
    # choices), never in a widget default: passing both raises a warning.
    state = st.session_state
    state.setdefault("pdf_style", RedactionStyle.PSEUDONYMIZE)
    state.setdefault("pdf_custom_words", "")
    state.setdefault("pdf_redact_images", True)
    state.setdefault("pdf_read_scans", True)

    with st.expander("Customize: labels or black boxes, words to add, images"):
        st.radio(
            "Redaction style",
            options=[RedactionStyle.PSEUDONYMIZE, RedactionStyle.BLACKOUT],
            format_func=lambda s: (
                "Replace with labels such as [001]"
                if s == RedactionStyle.PSEUDONYMIZE
                else "Black out (cover with black boxes)"
            ),
            help=(
                "Labels replace matched text with [001], [002] and so on, with "
                "a separate mapping file saying which Internal ID each label "
                "stands for. Black out covers matched text and images with a "
                "black box instead, with nothing to decode."
            ),
            key="pdf_style",
        )
        st.text_area(
            "Words or phrases to add (optional)",
            help=(
                "One per line. Email addresses, websites, and any name already "
                "on the master list are caught automatically - you don't need "
                "to list those. Use this for anything else: a name not yet on "
                "the master list, a project codename, a case number. Not saved "
                "anywhere; re-enter next time if needed."
            ),
            key="pdf_custom_words",
        )
        st.checkbox(
            "Also black out images / logos",
            help=(
                "Covers every image on each page with a black box, in either "
                "redaction style. Only embedded raster images count as "
                '"logos" - a logo drawn as vector art (lines/shapes, not a '
                "picture) won't be caught."
            ),
            key="pdf_redact_images",
        )
        st.checkbox(
            "Read the text on scanned pages (OCR)",
            disabled=not pdf_service.can_read_scans,
            help=(
                "A scanned page is a picture of text. With this on, the printed "
                "text is read, names in it are redacted, and anything that could "
                "not be read with confidence (signatures, handwriting, stamps) "
                "is blacked out when 'black out images' is on. Slower: about two "
                "seconds a page."
                if pdf_service.can_read_scans
                else "OCR is not installed on this computer; re-run the installer."
            ),
            key="pdf_read_scans",
        )

    style = state["pdf_style"]
    redact_images = bool(state["pdf_redact_images"])
    custom_words = [
        w.strip() for w in state["pdf_custom_words"].splitlines() if w.strip()
    ]
    if any(_LABEL_SHAPED.match(w) for w in custom_words):
        st.warning(
            "One of your words to redact looks like a redaction label (e.g. "
            "`[001]`). That is the shape this tool writes into the PDF, so "
            "redacting it would redact the tool's own output. Remove it "
            "unless the document genuinely contains that text for another "
            "reason."
        )

    if st.button("Redact my file", type="primary", width="stretch"):
        uploaded.seek(0)
        try:
            with st.status(
                "Scanning the PDF (scanned pages take a few seconds each)...",
                expanded=False,
            ) as status:
                scan_result = pdf_service.scan(
                    uploaded, read_scans=bool(state["pdf_read_scans"])
                )
                uploaded.seek(0)
                status.update(label="Building the redacted PDF...")
                result = pdf_service.redact(
                    uploaded,
                    scan_result,
                    custom_words,
                    style=style,
                    redact_images=redact_images,
                )
        except EncryptedPdfError:
            st.error(
                "This PDF is password-protected, so its pages can't be "
                "read. Open it in a PDF reader, enter the password, save an "
                "unlocked copy, and upload that copy instead."
            )
            return
        except UnreadableFileError:
            st.error(
                "This file could not be read as a PDF. It may be corrupted, "
                "or not really a .pdf file despite its name. Open it in a "
                "PDF reader, save a fresh copy, and upload that instead."
            )
            return
        state.pdf_scan_result = scan_result
        state.pdf_buffer = result.data
        state.pdf_findings = result.findings
        state.pdf_pages = result.page_count
        state.pdf_crosswalk = result.crosswalk
        state.pdf_bracketed = result.source_bracketed_numbers
        state.pdf_links = result.removed_links
        # The unfiltered detections, kept as the deselect editor's stable
        # row list. Never overwritten by a re-run below, so a term can be
        # unticked and re-ticked; refiltering it would take the tick box
        # away with the row and strand the decision.
        state.pdf_all_findings = result.findings
        state.pdf_excluded_applied = frozenset()
        # The settings this result was built with. The later steps read
        # these, not the option widgets, which are only drawn on Options.
        state.pdf_run = {
            "custom_words": custom_words,
            "style": style,
            "redact_images": redact_images,
        }
        wizard.go(wizard.REVIEW)


def _review_step(uploaded: Any, pdf_service: RedactPdfService, steps: Any) -> None:
    state = st.session_state
    run = state.pdf_run
    pdf_findings = state.pdf_findings
    n_entities = len(pdf_findings)
    total_pages = state.pdf_pages
    removed_links = state.get("pdf_links", 0)
    blackout = run["style"] == RedactionStyle.BLACKOUT

    show_step(steps, 3)
    st.subheader("Review what was found")
    st.caption(
        f"{plural(n_entities, 'match', 'matches')} on "
        f"{plural(total_pages, 'page')}"
        + (
            f" · {plural(removed_links, 'link target')} removed"
            if removed_links
            else ""
        )
    )
    if n_entities == 0:
        st.info(
            "No names, emails, websites, addresses, or matching words were "
            f"found across {plural(total_pages, 'page')}. Any images and link "
            "targets are still removed in the download."
        )
    elif blackout:
        st.caption("Matched areas will be blacked out in the downloaded PDF.")

    # Warnings stay above the tabs: an unresolved item is undecodable later,
    # and a scanned page was not read at all; both deserve to be seen without
    # opening anything.
    scanned = state.pdf_scan_result.scanned_pages
    if scanned:
        st.warning(
            scanned_pages_warning(
                scanned,
                total_pages,
                run["redact_images"],
                read=state.pdf_scan_result.read_pages,
            )
        )
    if not blackout:
        bracketed = state.get("pdf_bracketed", 0)
        if bracketed:
            st.warning(
                "This document already contained "
                f"{plural(bracketed, 'bracketed number')} of its own, such "
                "as footnote markers or line-item numbers. Redaction labels "
                "look the same ([001]), so a reader of the output may not "
                "be able to tell which brackets are redactions. The label "
                "mapping lists every label this tool actually inserted."
            )
        render_pdf_mapping_warnings(state.pdf_crosswalk)

    review_findings = state.get("pdf_all_findings", [])
    tab_review, tab_mapping, tab_occurrences = st.tabs(
        review_tab_labels(review_findings)
    )
    with tab_mapping:
        if blackout:
            st.caption("Black out leaves nothing to decode, so there is no mapping.")
        else:
            render_pdf_mapping_section(state.pdf_crosswalk)
    with tab_review:
        excluded = render_deselect_editor(
            review_findings,
            key_prefix="pdf",
            excluded=state.get("pdf_excluded_applied", frozenset()),
        )
    with tab_occurrences:
        st.markdown(f"**All detections ({plural(n_entities, 'finding')})**")
        st.dataframe(
            findings_dataframe(pdf_findings, "Page"),
            width="stretch",
            hide_index=True,
        )

    if excluded != state.get("pdf_excluded_applied", frozenset()):
        # No detector call happens here at all: ``pdf_scan_result`` was
        # computed once, on the Redact click, and this just reruns the
        # cheap, detector-free redaction-building/apply step over it with
        # the new exclude set.
        uploaded.seek(0)
        with st.spinner("Rebuilding without those terms..."):
            rerun = pdf_service.redact(
                uploaded,
                state.pdf_scan_result,
                run["custom_words"],
                style=run["style"],
                redact_images=run["redact_images"],
                exclude=excluded,
            )
        state.pdf_buffer = rerun.data
        state.pdf_findings = rerun.findings
        state.pdf_crosswalk = rerun.crosswalk
        state.pdf_excluded_applied = excluded
        st.rerun()

    wizard.nav(
        back=("Back to options", wizard.OPTIONS),
        forward=("Continue to download", wizard.DOWNLOAD),
    )


def _download_step(master_list_fingerprint: str, steps: Any) -> None:
    state = st.session_state
    run = state.pdf_run
    blackout = run["style"] == RedactionStyle.BLACKOUT
    removed_links = state.get("pdf_links", 0)
    base_name = output_stem()

    show_step(steps, 4)
    st.subheader("Download")
    render_exclusion_warning(state.get("pdf_excluded_applied", frozenset()))
    safe, private = wizard.download_cards()
    with safe:
        st.download_button(
            label="Download blacked-out PDF" if blackout else "Download redacted PDF",
            data=state.pdf_buffer,
            file_name=f"{base_name}-blackout.pdf" if blackout else f"{base_name}.pdf",
            mime="application/pdf",
            type="primary",
            width="stretch",
        )
        caption = (
            "Matched text and images are covered with black boxes."
            if blackout
            else "Matched text is replaced with labels such as [001]. Bank and "
            "payment details and addresses show as a mask such as [ACCOUNT]."
        )
        if removed_links:
            caption += (
                f" {plural(removed_links, 'link target')} (websites, email "
                "addresses, files) removed; the link text stays, redacted "
                "where it matched."
            )
        st.caption(caption)
        if not blackout:
            render_pdf_mapping_download(
                state.pdf_crosswalk, base_name, master_list_fingerprint
            )
    with private:
        if blackout:
            st.caption("Black out leaves nothing to decode, so there is no file here.")
        else:
            render_pdf_names_download(
                state.pdf_crosswalk, base_name, master_list_fingerprint
            )

    wizard.nav(back=("Back to review", wizard.REVIEW), finish=True)
