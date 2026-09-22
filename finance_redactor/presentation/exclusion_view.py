"""Shared UI for rejecting a false positive.

The tool detects generously on purpose - a missed name is unrecoverable, an
extra one is not - so over-redaction is the expected failure and a reviewer is
meant to catch it. Until now there was nothing to catch it *with*: every
pipeline stage only ever added detections, and no flow had a way to say "not
that one". The nearest levers were the confidence threshold (which cannot
touch an exact master-list match, and at 0.95 disables every curated name at
once) and, for Excel only, deselecting a whole column.

This module is that missing control: a tick box per detected term, applied for
this document only. Nothing persists. A term ticked off here is dropped before
the pseudonymizer sees it, so it is neither replaced in the output nor recorded
in the crosswalk.

Unticking is a deliberate under-redaction, and the term then appears in the
downloaded file in plain text. That is correct for an ordinary word like
"salaries" and a mistake for a real name, so :func:`render_exclusion_warning`
states it plainly rather than letting it pass quietly. Names are shown on
screen only - the operator reading their own screen is fine - and nothing here
is logged.
"""

from __future__ import annotations

from collections.abc import Sequence

import streamlit as st

from finance_redactor.domain.entities import Finding
from finance_redactor.presentation.presenters import (
    REDACT_COLUMN,
    detection_editor_dataframe,
    excluded_terms,
)


def render_deselect_editor(
    findings: Sequence[Finding],
    *,
    key_prefix: str,
    excluded: frozenset[str] = frozenset(),
) -> frozenset[str]:
    """Render the tickable detections table and return the terms to exclude.

    ``findings`` must be the **unfiltered** detections from the first run, kept
    in session state and not recomputed when only the tick boxes change. If it
    were refiltered, an unticked row would disappear along with its own tick
    box and could never be re-ticked.
    """
    if not findings:
        return frozenset()

    table = detection_editor_dataframe(findings, excluded)
    n_terms = len(table)

    with st.expander(f"Check what was detected ({n_terms} distinct term(s))"):
        st.caption(
            "Untick anything that is not really a name. It will be left as-is "
            "in the file you download, and the file is rebuilt as soon as you "
            "change a tick. **Source** tells you why it matched, and what the "
            "lasting fix is: *master list* means a row in the workbook matches "
            "this word, so unticking it patches this one document while "
            "editing the workbook fixes every future one."
        )
        # The only editable widget in this codebase. Everything else is
        # st.dataframe, deliberately: those tables are read-only records.
        # This one has to be editable, because the whole point is letting the
        # operator overrule a detection, and a tick box beside the offending
        # row is where they will look for it.
        edited = st.data_editor(
            table,
            width="stretch",
            hide_index=True,
            key=f"{key_prefix}_deselect_editor",
            column_config={
                REDACT_COLUMN: st.column_config.CheckboxColumn(
                    REDACT_COLUMN,
                    help="Untick to leave this term un-redacted in this document.",
                    default=True,
                )
            },
            disabled=[c for c in table.columns if c != REDACT_COLUMN],
        )

    return excluded_terms(edited)


def render_exclusion_warning(excluded: frozenset[str]) -> None:
    """Warn, above the download, about terms that will not be redacted."""
    if not excluded:
        return

    terms = ", ".join(f"`{term}`" for term in sorted(excluded))
    st.warning(
        f"**{len(excluded)} term(s) will not be redacted**, at your request: "
        f"{terms}. They appear in the downloaded file exactly as they do in "
        "the original. Re-tick them above if that is not what you meant."
    )
