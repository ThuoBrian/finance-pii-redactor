"""Shared UI for rejecting a false positive.

The tool detects generously on purpose - a missed name is unrecoverable, an
extra one is not - so over-redaction is the expected failure and a reviewer is
meant to catch it. Until now there was nothing to catch it *with*: every
pipeline stage only ever added detections, and no flow had a way to say "not
that one". The nearest levers were the confidence threshold (which cannot
touch an exact master-list match, and at 0.95 disables every curated name at
once) and, for Excel only, deselecting a whole column.

This module is that missing control: a tick box per detected term, applied for
this document only once "Apply changes" is clicked. Nothing persists between
documents. A term ticked off here is dropped before the pseudonymizer sees it,
so it is neither replaced in the output nor recorded in the crosswalk.

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
    plural,
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

    Not wrapped in a form, so the Apply button can show a pending count and
    turn primary the moment a tick changes. A review pass still costs one
    rebuild, not one per tick: ``st.data_editor`` reruns the script on every
    toggle, but the returned set only changes on the Apply click.
    """
    if not findings:
        return frozenset()

    table = detection_editor_dataframe(findings, excluded)
    n_terms = len(table)

    # Rendered in the review step's "Details" tab, so no expander of its own.
    with st.container():
        st.markdown(f"**Check what was detected ({plural(n_terms, 'distinct term')})**")
        st.caption(
            "Each row is one term the tool found. Untick **Hide in output?** "
            "for anything that is not really a name or a bank/payment "
            "detail, then click **Apply changes**. Nothing is rebuilt until "
            "you click it, so tick and untick as many rows as you like "
            "first. An unticked term is left as-is in the file you download. "
            "**Source** tells you why it matched, and what the lasting fix "
            "is: *master list* means a row in the workbook matches this "
            "word, so unticking it patches this one document while editing "
            "the workbook fixes every future one."
        )
        # The only editable widget in this codebase. Everything else is
        # st.dataframe, deliberately: those tables are read-only records.
        # This one has to be editable, because the whole point is letting the
        # operator overrule a detection, and a tick box beside the offending
        # row is where they will look for it.
        #
        edited = st.data_editor(
            table,
            width="stretch",
            hide_index=True,
            key=f"{key_prefix}_deselect_editor",
            column_config={
                REDACT_COLUMN: st.column_config.CheckboxColumn(
                    REDACT_COLUMN,
                    help="Untick to leave this term visible in this document.",
                    default=True,
                )
            },
            disabled=[c for c in table.columns if c != REDACT_COLUMN],
        )
        pending = excluded_terms(edited)
        n_changes = len(pending ^ excluded)
        if n_changes:
            applied = st.button(
                f"Apply changes ({n_changes} pending)",
                type="primary",
                width="stretch",
                key=f"{key_prefix}_deselect_apply",
            )
        else:
            applied = False
            st.button(
                "Apply changes",
                disabled=True,
                width="stretch",
                key=f"{key_prefix}_deselect_apply_idle",
            )

    # Ticks reach the script on every toggle, so the returned set must stay
    # the *applied* one until Apply is clicked: callers rebuild the output
    # whenever it changes. Only the click's own rerun returns the pending set.
    return pending if applied else excluded


def render_exclusion_warning(excluded: frozenset[str]) -> None:
    """Warn, above the download, about terms that will not be redacted."""
    if not excluded:
        return

    terms = ", ".join(f"`{term}`" for term in sorted(excluded))
    st.warning(
        f"**{plural(len(excluded), 'term')} will not be hidden**, at your request: "
        f"{terms}. They appear in the downloaded file exactly as they do in "
        "the original. Re-tick them above and click **Apply changes** if "
        "that is not what you meant."
    )
