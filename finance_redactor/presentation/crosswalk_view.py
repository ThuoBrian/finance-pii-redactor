"""Shared rendering of the name->pseudonym crosswalk.

Both the Excel and PDF flows show the same crosswalk: a review table plus a
download button gated behind a prominent warning, because the crosswalk is the
re-identification key (Confidential under IPA's data classification policy).
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


def render_crosswalk_section(
    crosswalk: list[Assignment], base_name: str, *, key_prefix: str
) -> None:
    """Render the crosswalk table and a guarded CSV download."""
    if not crosswalk:
        return

    n_flagged = sum(1 for a in crosswalk if a.auto)
    df = crosswalk_dataframe(crosswalk)

    with st.expander(f"Name -> pseudonym mapping ({len(crosswalk)} name(s))"):
        if n_flagged:
            st.info(
                f"{n_flagged} name(s) were not in the master list and received a "
                "flagged auto-generated ID (shown as 'yes' under Flagged). Review "
                "them and, if correct, add them to the master list with a curated ID."
            )
        st.dataframe(df, width="stretch", hide_index=True)
        st.warning(_CROSSWALK_WARNING)
        st.download_button(
            label="Download name mapping (CSV)",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name=f"{base_name}_crosswalk.csv",
            mime="text/csv",
            key=f"{key_prefix}_crosswalk_download",
            width="stretch",
        )
