"""Rendering of the mapping between what was redacted and what replaced it.

Two schemes live here, because PDF and Excel/Word differ in what they write
into a document. Each has a review table (the Review step's Mapping tab) and
downloads (the Download step, sorted into an Internal and a Confidential card).

PDF stamps a document-local ``[001]`` label. :func:`render_pdf_mapping_download`
gives ``label -> Internal ID`` with **no names**, which is what makes that file
Internal. :func:`render_pdf_names_download` is the opt-in, Confidential file
with names, off by default.

Excel and Word stamp ``STF-10010``-style codes. Their crosswalk maps real names
to those codes, so it is the re-identification key and Confidential; it always
leaves the app as its own CSV (:func:`render_crosswalk_download`), never inside
the redacted file.

The names-free and names-bearing paths are separate functions on purpose. They
disagree about whether a name may reach a file, and that is not a difference to
express as a flag on one shared code path.
"""

from __future__ import annotations

import streamlit as st

from finance_redactor.domain.pseudonyms import Assignment
from finance_redactor.presentation.presenters import (
    crosswalk_dataframe,
    pdf_mapping_dataframe,
    pdf_mapping_with_names_dataframe,
    pdf_review_dataframe,
    plural,
)

# Session key of the opt-in toggle; the PDF flow clears it on a new upload so a
# names file is never offered by default for the next document.
PDF_NAMES_TOGGLE_KEY = "pdf_names_mapping_toggle"

_PDF_MAPPING_NOTICE = (
    "No names inside, only rows like `[001] = 17728`, so it is safe to keep "
    "with the PDF. Keep it: without it the labels cannot be decoded. Decoding "
    "also needs the master list, which stays access-controlled."
)

_CROSSWALK_WARNING = (
    "Lists real names next to their codes, so it can re-identify everyone in "
    "the file. Store it somewhere secure, apart from the redacted file, and "
    "never send the two together."
)


def render_pdf_mapping_warnings(crosswalk: list[Assignment]) -> None:
    """Warn about PDF items that cannot be decoded later. Call above the tabs.

    These stay outside the mapping tab on purpose: in the Excel and Word flows
    a flagged row is a nudge to tidy the master list, because the CSV still
    carries the name. Here the download has no names, so an unresolved row is
    genuinely undecodable later - that deserves to be seen without opening
    anything.
    """
    unresolved = [a for a in crosswalk if a.internal_id is None]
    ambiguous = [a for a in unresolved if a.ambiguous]
    missing = [a for a in unresolved if not a.ambiguous]

    if missing:
        st.warning(
            f"Not in the master list: {plural(len(missing), 'redacted item')}. "
            "They were still redacted, but their mapping rows carry a "
            "placeholder token instead of an Internal ID, so **they cannot be "
            "decoded from the master list later**. Add them to the master list "
            "and re-run if you need them identifiable."
        )
    if ambiguous:
        st.warning(
            "Ambiguous master-list match: "
            f"{plural(len(ambiguous), 'redacted item')}. Each matched more than "
            "one master-list row with conflicting IDs, so no Internal ID was "
            "recorded rather than guessing one. Fix the duplicate rows (the "
            "master-list card in the sidebar lists them) and re-run."
        )


def render_pdf_mapping_section(crosswalk: list[Assignment]) -> None:
    """Render the PDF label mapping for review on screen (names shown, never saved)."""
    if not crosswalk:
        st.caption("Nothing was replaced with a label, so there is no mapping.")
        return
    n_suggested = sum(1 for a in crosswalk if a.suggested_pseudonym)
    st.markdown(f"**Label -> Internal ID mapping ({plural(len(crosswalk), 'item')})**")
    if n_suggested:
        st.info(
            f"Close master-list match for {plural(n_suggested, 'unresolved item')}"
            " - see 'Possible match' (e.g. a likely typo). "
            "This is a hint only; it was **not** applied automatically."
        )
    st.caption(
        "Names are shown here for your review only. The mapping file on the "
        "Download step contains no names."
    )
    st.dataframe(pdf_review_dataframe(crosswalk), width="stretch", hide_index=True)


def render_pdf_mapping_download(
    crosswalk: list[Assignment], base_name: str, master_list_fingerprint: str
) -> None:
    """Offer the names-free label mapping (Internal). Nothing to offer if empty."""
    if not crosswalk:
        return
    mapping_df = pdf_mapping_dataframe(crosswalk, master_list_fingerprint)
    st.download_button(
        label="Download label mapping (CSV, no names)",
        data=mapping_df.to_csv(index=False).encode("utf-8"),
        file_name=f"{base_name}_mapping.csv",
        mime="text/csv",
        key="pdf_mapping_download",
        width="stretch",
    )
    st.caption(_PDF_MAPPING_NOTICE)


def render_pdf_names_download(
    crosswalk: list[Assignment], base_name: str, master_list_fingerprint: str
) -> None:
    """Offer the opt-in mapping with names (Confidential), off by default."""
    if not crosswalk:
        st.caption("Nothing was replaced with a label, so there is no mapping.")
        return
    # Off by default, and nothing with names is built unless it is switched on.
    if st.toggle(
        "Also prepare a mapping with names",
        key=PDF_NAMES_TOGGLE_KEY,
        help="For when you need to read the mapping without the master list. "
        "The label mapping stays names-free.",
    ):
        st.download_button(
            label="Download name mapping (CSV)",
            data=pdf_mapping_with_names_dataframe(crosswalk, master_list_fingerprint)
            .to_csv(index=False)
            .encode("utf-8"),
            file_name=f"{base_name}_crosswalk.csv",
            mime="text/csv",
            key="pdf_names_mapping_download",
            width="stretch",
        )
        st.caption(_CROSSWALK_WARNING)
    else:
        st.caption(
            "Not needed in most cases: the label mapping and the master list decode every label."
        )


def render_crosswalk_section(crosswalk: list[Assignment]) -> None:
    """Render the Excel/Word name -> code mapping for review on screen."""
    if not crosswalk:
        st.caption("No names were replaced, so there is no mapping.")
        return
    n_flagged = sum(1 for a in crosswalk if a.auto)
    n_suggested = sum(1 for a in crosswalk if a.suggested_pseudonym)
    st.markdown(f"**Name -> code mapping ({plural(len(crosswalk), 'name')})**")
    if n_flagged:
        st.info(
            f"Not in the master list: {plural(n_flagged, 'name')}. Each received "
            "a flagged auto-generated ID (shown as 'yes' under Flagged). Review "
            "them and, if correct, add them to the master list with a curated ID."
        )
    if n_suggested:
        st.info(
            f"Close master-list match for {plural(n_suggested, 'flagged name')}"
            " - see 'Possible match' (e.g. a likely typo). This is a "
            "hint only; it was **not** applied automatically. Fix the source "
            "document or add an alias, then re-run."
        )
    st.dataframe(crosswalk_dataframe(crosswalk), width="stretch", hide_index=True)


def render_crosswalk_download(
    crosswalk: list[Assignment], base_name: str, *, key_prefix: str
) -> None:
    """Offer the Excel/Word crosswalk (real names, Confidential) as its own CSV."""
    if not crosswalk:
        st.caption("No names were replaced, so there is no mapping file.")
        return
    st.download_button(
        label="Download name mapping (CSV)",
        data=crosswalk_dataframe(crosswalk).to_csv(index=False).encode("utf-8"),
        file_name=f"{base_name}_crosswalk.csv",
        mime="text/csv",
        key=f"{key_prefix}_crosswalk_download",
        width="stretch",
    )
    st.caption(_CROSSWALK_WARNING)
