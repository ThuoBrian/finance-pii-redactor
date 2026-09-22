"""Rendering of the mapping between what was redacted and what replaced it.

Two schemes live here, because PDF and Excel/Word now differ in what they
write into a document.

:func:`render_pdf_mapping_section` serves PDF, which stamps a document-local
``[001]`` label. Its download carries ``label -> Internal ID`` and **no
names**, which is what makes that file Internal rather than Confidential.

:func:`render_crosswalk_section` serves Excel and Word, which still stamp
``STF-10010``-style pseudonyms. Their crosswalk maps real names to those
pseudonyms, so it remains the re-identification key and Confidential. Excel's
workbook already embeds it as a "Crosswalk" sheet (see
``OpenpyxlExcelGateway.write``), so it passes ``download_separately=False``
to skip a redundant CSV and point the warning at the sheet already in the
file; Word passes the default and gets its own guarded CSV.

The two are separate functions on purpose. They disagree about whether a name
may reach a file, and that is not a difference to express as a flag on one
shared code path.
"""

from __future__ import annotations

import streamlit as st

from finance_redactor.domain.pseudonyms import Assignment
from finance_redactor.presentation.presenters import (
    crosswalk_dataframe,
    pdf_mapping_dataframe,
    pdf_review_dataframe,
)

_PDF_MAPPING_NOTICE = (
    "This file contains **no names** - only `[001] = 17728` style rows. On its "
    "own it cannot identify anyone, so it is **Internal**, and it is safe to "
    "keep with the redacted PDF. Turning an Internal ID back into a name needs "
    "the master list, which stays access-controlled in Box. Keep this file: "
    "without it the labels in the PDF cannot be decoded at all."
)

_CROSSWALK_WARNING = (
    "This crosswalk maps real names to their pseudonyms - it is the "
    "**re-identification key**. Store it separately and securely, and **never** "
    "share it alongside the pseudonymized file. It is **Confidential** under "
    "IPA's data classification policy."
)

_CROSSWALK_EMBEDDED_NOTICE = (
    "This review table matches the **Crosswalk** sheet already included in "
    "your downloaded Excel file - there is no separate CSV to keep track of "
    "for this file. The workbook as a whole is **Confidential** under IPA's "
    "data classification policy because it now carries the re-identification "
    "key; see the warning above the download button."
)


def render_pdf_mapping_section(
    crosswalk: list[Assignment],
    base_name: str,
    *,
    master_list_fingerprint: str = "",
) -> None:
    """Render the PDF label->Internal ID mapping: review on screen, names-free download.

    Kept separate from :func:`render_crosswalk_section` rather than added to it
    as a flag. The two differ in the one way that matters - what ends up in a
    file - and a shared function with a switch is exactly how a name
    eventually reaches a download that promised not to have any.

    Unresolved entities are warned about **above** the expander, not inside
    it. In the Excel and Word flows a flagged row is a nudge to tidy the
    master list, because the CSV still carries the name. Here the download has
    no names, so an unresolved row is genuinely undecodable later - that
    deserves to be seen without opening anything.
    """
    if not crosswalk:
        return

    unresolved = [a for a in crosswalk if a.internal_id is None]
    ambiguous = [a for a in unresolved if a.ambiguous]
    missing = [a for a in unresolved if not a.ambiguous]

    if missing:
        st.warning(
            f"{len(missing)} redacted item(s) are not in the master list. They "
            "were still redacted, but their mapping rows carry a placeholder "
            "token instead of an Internal ID, so **they cannot be decoded from "
            "the master list later**. Add them to the master list and re-run if "
            "you need them identifiable."
        )
    if ambiguous:
        st.warning(
            f"{len(ambiguous)} redacted item(s) matched more than one master-list "
            "row with conflicting IDs, so no Internal ID was recorded rather "
            "than guessing one. Fix the duplicate rows (see the master-list "
            "data-quality panel in Advanced settings) and re-run."
        )

    n_suggested = sum(1 for a in crosswalk if a.suggested_pseudonym)
    mapping_df = pdf_mapping_dataframe(crosswalk, master_list_fingerprint)

    with st.expander(f"Label -> Internal ID mapping ({len(crosswalk)} item(s))"):
        if n_suggested:
            st.info(
                f"{n_suggested} unresolved item(s) closely resemble a curated "
                "master-list name - see 'Possible match' (e.g. a likely typo). "
                "This is a hint only; it was **not** applied automatically."
            )
        st.caption(
            "Names are shown here for your review only. The downloaded file "
            "below contains no names."
        )
        st.dataframe(pdf_review_dataframe(crosswalk), width="stretch", hide_index=True)
        st.info(_PDF_MAPPING_NOTICE)
        st.download_button(
            label="Download label mapping (CSV, no names)",
            data=mapping_df.to_csv(index=False).encode("utf-8"),
            file_name=f"{base_name}_mapping.csv",
            mime="text/csv",
            key="pdf_mapping_download",
            width="stretch",
        )


def render_crosswalk_section(
    crosswalk: list[Assignment],
    base_name: str,
    *,
    key_prefix: str,
    download_separately: bool = True,
) -> None:
    """Render the crosswalk review table, plus a guarded CSV download.

    ``download_separately`` is True for flows (PDF) where the crosswalk only
    ever leaves the app as its own CSV file, so it must stay separate from
    the pseudonymized output. Excel passes ``download_separately=False``: the
    crosswalk is already embedded as a sheet in the downloaded workbook (see
    ``OpenpyxlExcelGateway.write``), so no second download button is offered
    here and the warning instead points at the sheet that's already there.
    """
    if not crosswalk:
        return

    n_flagged = sum(1 for a in crosswalk if a.auto)
    n_suggested = sum(1 for a in crosswalk if a.suggested_pseudonym)
    df = crosswalk_dataframe(crosswalk)

    with st.expander(f"Name -> pseudonym mapping ({len(crosswalk)} name(s))"):
        if n_flagged:
            st.info(
                f"{n_flagged} name(s) were not in the master list and received a "
                "flagged auto-generated ID (shown as 'yes' under Flagged). Review "
                "them and, if correct, add them to the master list with a curated ID."
            )
        if n_suggested:
            st.info(
                f"{n_suggested} flagged name(s) closely resemble a curated master-"
                "list name - see 'Possible match' (e.g. a likely typo). This is a "
                "hint only; it was **not** applied automatically. Fix the source "
                "document or add an alias, then re-run."
            )
        st.dataframe(df, width="stretch", hide_index=True)
        if download_separately:
            st.warning(_CROSSWALK_WARNING)
            st.download_button(
                label="Download name mapping (CSV)",
                data=df.to_csv(index=False).encode("utf-8"),
                file_name=f"{base_name}_crosswalk.csv",
                mime="text/csv",
                key=f"{key_prefix}_crosswalk_download",
                width="stretch",
            )
        else:
            st.info(_CROSSWALK_EMBEDDED_NOTICE)
