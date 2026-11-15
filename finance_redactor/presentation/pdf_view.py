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

from typing import Any

import streamlit as st

from finance_redactor.application.redact_pdf import (
    LARGE_PDF_PAGES,
    OCR_SECONDS_PER_PAGE,
    RedactionStyle,
    RedactPdfService,
)
from finance_redactor.domain.errors import EncryptedPdfError, UnreadableFileError
from finance_redactor.domain.tables import suggested_columns
from finance_redactor.presentation import wizard
from finance_redactor.presentation.crosswalk_view import (
    render_pdf_mapping_download,
    render_pdf_mapping_section,
    render_pdf_names_download,
)
from finance_redactor.presentation.exclusion_view import (
    carried_key,
    render_deselect_editor,
    render_exclusion_warning,
    render_where_found,
    unapplied_changes_note,
)
from finance_redactor.presentation.presenters import (
    carry_over_exclusions,
    findings_dataframe,
    merge_findings,
    not_located_warning,
    pdf_job_size_note,
    pdf_mapping_notes,
    plural,
    review_tab_labels,
    scanned_pages_warning,
)
from finance_redactor.presentation.session import (
    PDF_COLUMNS_KEY,
    output_stem,
    reset_on_new_upload,
)
from finance_redactor.presentation.steps import show_step
from finance_redactor.presentation.words_view import (
    additions_expander,
    render_words_box,
    typed_words,
    unapplied_words_note,
)

_COLUMNS_KEY = PDF_COLUMNS_KEY


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
    reset_on_new_upload(uploaded, "pdf")
    if wizard.current() == wizard.OPTIONS or st.session_state.get("pdf_buffer") is None:
        _options_step(uploaded, pdf_service, steps)
        wizard.nav(back=("Back to upload", wizard.UPLOAD))
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
        "are found automatically. Images are blacked out. Missed a name? "
        "You can add it on the next step."
    )
    # Values live in session state (seeded here, kept by wizard.keep_option_
    # choices), never in a widget default: passing both raises a warning.
    state = st.session_state
    state.setdefault("pdf_style", RedactionStyle.PSEUDONYMIZE)
    state.setdefault("pdf_redact_images", True)
    state.setdefault("pdf_read_scans", True)

    with st.expander("Customize: labels or black boxes, images, scanned pages"):
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
                "is blacked out when 'black out images' is on. Slower: several "
                "seconds a page."
                if pdf_service.can_read_scans
                else "OCR is not installed on this computer; re-run the installer."
            ),
            key="pdf_read_scans",
        )

    style = state["pdf_style"]
    redact_images = bool(state["pdf_redact_images"])
    reading_scans = bool(state["pdf_read_scans"]) and pdf_service.can_read_scans
    scanned, total = _job_size(uploaded, pdf_service)
    size_note = pdf_job_size_note(
        scanned,
        total,
        reading_scans=reading_scans,
        seconds_per_page=OCR_SECONDS_PER_PAGE,
        large_pages=LARGE_PDF_PAGES,
    )
    if size_note:
        st.warning(size_note)
    # Words typed for an earlier file in this session carry over.
    custom_words = typed_words("pdf")

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
                # Name-, account- and contact-like columns start chosen, plus
                # any the user added on an earlier run of this file.
                columns = suggested_columns(scan_result.table_columns) | (
                    state.get("pdf_columns_applied", frozenset())
                    & set(scan_result.table_columns)
                )
                result = pdf_service.redact(
                    uploaded,
                    scan_result,
                    custom_words,
                    style=style,
                    redact_images=redact_images,
                    columns=columns,
                )
                # Back from Review: keep the terms unticked there that this
                # run found again, rather than wiping the review.
                carried = carry_over_exclusions(
                    state.get("pdf_excluded_applied", frozenset()), result.findings
                )
                built = result
                if carried:
                    uploaded.seek(0)
                    built = pdf_service.redact(
                        uploaded,
                        scan_result,
                        custom_words,
                        style=style,
                        redact_images=redact_images,
                        exclude=carried,
                        columns=columns,
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
        state.pdf_buffer = built.data
        state.pdf_findings = built.findings
        state.pdf_pages = built.page_count
        state.pdf_crosswalk = built.crosswalk
        state.pdf_bracketed = built.source_bracketed_numbers
        state.pdf_links = built.removed_links
        state.pdf_not_located = built.not_located
        # The unfiltered detections, kept as the deselect editor's stable
        # row list. Never overwritten by a re-run below, so a term can be
        # unticked and re-ticked; refiltering it would take the tick box
        # away with the row and strand the decision.
        state.pdf_all_findings = result.findings
        state.pdf_excluded_applied = carried
        state[carried_key("pdf")] = carried
        state.pdf_columns_applied = columns
        state[_COLUMNS_KEY] = sorted(columns)
        # The settings this result was built with. The later steps read
        # these, not the option widgets, which are only drawn on Options.
        state.pdf_run = {
            "custom_words": custom_words,
            "style": style,
            "redact_images": redact_images,
        }
        wizard.go(wizard.REVIEW)


def _job_size(uploaded: Any, pdf_service: RedactPdfService) -> tuple[int, int]:
    """Return ``(scanned pages, total pages)``, counted once per upload.

    ``(0, 0)`` for a file that cannot be opened: the Redact click reports
    that properly.
    """
    state = st.session_state
    if "pdf_job_size" not in state:
        uploaded.seek(0)
        try:
            state.pdf_job_size = pdf_service.count_scanned_pages(uploaded)
        except (EncryptedPdfError, UnreadableFileError):
            state.pdf_job_size = (0, 0)
        uploaded.seek(0)
    scanned, total = state.pdf_job_size
    return scanned, total


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

    # Only the warnings that change what to review stay here: scanned pages
    # to check by eye, and terms nothing covers. The notes about sharing the
    # file are on Download, next to the file.
    scanned_note = _scanned_note()
    if scanned_note:
        st.warning(scanned_note)
    not_located = state.get("pdf_not_located", ())
    if not_located:
        st.warning(not_located_warning(not_located))

    review_findings = state.get("pdf_all_findings", [])
    tab_review, tab_mapping = st.tabs(review_tab_labels(review_findings))
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
            not_located=len(not_located),
        )

    columns_applied = state.get("pdf_columns_applied", frozenset())
    words_applied: list[str] = run["custom_words"]
    with additions_expander("pdf", words_applied):
        columns = _column_picker(state.pdf_scan_result.table_columns, columns_applied)
        words = render_words_box("pdf", words_applied, warn_label_shaped=True)
    render_where_found(findings_dataframe(pdf_findings, "Page"))

    if (
        excluded != state.get("pdf_excluded_applied", frozenset())
        or columns != columns_applied
        or words != words_applied
    ):
        # No detector call happens here at all: ``pdf_scan_result`` was
        # computed once, on the Redact click, and this just reruns the
        # cheap, detector-free redaction-building/apply step over it with
        # the new exclude set, column choice and typed words.
        uploaded.seek(0)
        with st.spinner("Rebuilding with your changes..."):
            rerun = pdf_service.redact(
                uploaded,
                state.pdf_scan_result,
                words,
                style=run["style"],
                redact_images=run["redact_images"],
                exclude=excluded,
                columns=columns,
            )
        state.pdf_buffer = rerun.data
        state.pdf_findings = rerun.findings
        state.pdf_crosswalk = rerun.crosswalk
        state.pdf_not_located = rerun.not_located
        state.pdf_excluded_applied = excluded
        if columns != columns_applied or words != words_applied:
            # A newly chosen column or typed word brings terms the first run
            # never found; add them so each one can still be unticked.
            state.pdf_all_findings = merge_findings(
                state.get("pdf_all_findings", []), rerun.findings
            )
            state.pdf_columns_applied = columns
            run["custom_words"] = words
        st.rerun()

    wizard.nav(
        back=("Back to options", wizard.OPTIONS),
        forward=("Continue to download", wizard.DOWNLOAD),
        hold=unapplied_changes_note(
            "pdf", state.get("pdf_excluded_applied", frozenset())
        )
        or unapplied_words_note("pdf", run["custom_words"]),
    )


def _scanned_note() -> str:
    """Return the scanned-pages warning for this result, or "" if none is a scan."""
    state = st.session_state
    scan = state.pdf_scan_result
    if not scan.scanned_pages:
        return ""
    return scanned_pages_warning(
        scan.scanned_pages,
        state.pdf_pages,
        state.pdf_run["redact_images"],
        read=scan.read_pages,
    )


def _before_you_share(blackout: bool) -> None:
    """Draw what to know before the PDF goes anywhere, above the downloads.

    One box, not a stack: scanned pages, and items the mapping can't decode
    later. Yellow only when something may show. Terms nothing covers keep
    their own warning, as on Review, so it can't be read past.
    """
    state = st.session_state
    scanned_note = _scanned_note()
    notes = [scanned_note] if scanned_note else []
    if not blackout:
        notes += pdf_mapping_notes(state.pdf_crosswalk)
    if notes:
        box = st.warning if scanned_note else st.info
        box("**Before you share this PDF**\n\n" + "\n\n".join(notes))
    not_located = state.get("pdf_not_located", ())
    if not_located:
        st.warning(not_located_warning(not_located))


def _column_picker(
    table_columns: dict[str, str], applied: frozenset[str]
) -> frozenset[str]:
    """Draw the table-column picker and return the columns now chosen.

    Shown only when the scan found a table. A change applies at once (the
    rebuild is cheap); the caller compares the result with ``applied``.
    """
    if not table_columns:
        return applied
    st.session_state.setdefault(_COLUMNS_KEY, sorted(applied))
    chosen = st.multiselect(
        "Table columns to redact in full",
        options=list(table_columns),
        format_func=lambda key: table_columns[key],
        key=_COLUMNS_KEY,
        help=(
            "Every entry in a chosen column is replaced with a label, and the "
            "same value is replaced anywhere else on that page too. Columns "
            "that look like names, accounts or contact details start chosen. "
            "The header row stays."
        ),
    )
    return frozenset(chosen)


def _download_step(master_list_fingerprint: str, steps: Any) -> None:
    state = st.session_state
    run = state.pdf_run
    blackout = run["style"] == RedactionStyle.BLACKOUT
    removed_links = state.get("pdf_links", 0)
    base_name = output_stem()

    show_step(steps, 4)
    st.subheader("Download")
    render_exclusion_warning(state.get("pdf_excluded_applied", frozenset()))
    _before_you_share(blackout)
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
            bracketed = state.get("pdf_bracketed", 0)
            if bracketed:
                # Moved here from Review: it is about reading the output,
                # next to the file that tells the labels apart.
                st.caption(
                    "This PDF already had "
                    f"{plural(bracketed, 'bracketed number')} of its own (such "
                    "as footnote markers) that look like the [001] labels. "
                    "The code list names every label this tool added."
                )
    with private:
        if blackout:
            st.caption("Black out leaves nothing to decode, so there is no file here.")
        else:
            render_pdf_names_download(
                state.pdf_crosswalk, base_name, master_list_fingerprint
            )

    wizard.nav(back=("Back to review", wizard.REVIEW), finish=True)
