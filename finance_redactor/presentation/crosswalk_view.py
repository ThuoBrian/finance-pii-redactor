"""Shared rendering of the name->pseudonym crosswalk.

Both the Excel and PDF flows show the same review table, because the
crosswalk is the re-identification key (Confidential under IPA's data
classification policy). They differ on what happens after that: PDF has no
sheet concept, so its crosswalk only ever leaves the app as a separate,
warning-gated CSV download (``download_separately=True``, the default).
Excel's pseudonymized workbook already embeds the crosswalk as a "Crosswalk"
sheet (see ``OpenpyxlExcelGateway.write``), so its call passes
``download_separately=False`` to skip the redundant CSV button and point the
warning at the sheet that's already in the file.
"""

from __future__ import annotations

import streamlit as st

from finance_redactor.domain.pseudonyms import Assignment
from finance_redactor.presentation.presenters import crosswalk_dataframe

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
