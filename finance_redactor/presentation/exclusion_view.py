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
    ALL_SOURCES,
    REDACT_COLUMN,
    SOURCE_FILTERS,
    apply_notice,
    detection_editor_dataframe,
    filter_editor_rows,
    merge_pending,
    model_guess_count,
    plural,
    review_status,
    search_editor_rows,
    term_key,
)

_HOW_TO_READ = (
    "Each row is one term the tool found, with the likeliest false positives "
    "at the top and your master-list names at the bottom. Untick **Hide in "
    "output?** for anything that is not really a name or a bank/payment "
    "detail, then click **Apply changes**. Nothing is rebuilt until you click "
    "it, so tick and untick as many rows as you like first. An unticked term "
    "is left as-is in the file you download. **Source** tells you why it "
    "matched, and what the lasting fix is: *master list* means a row in the "
    "workbook matches this word, so unticking it patches this one document "
    "while editing the workbook fixes every future one."
)
_CLEAN_RUN = (
    "Nothing here is a guess. Every term came from your master list, words "
    "you typed, or a strict pattern such as an email or account number."
)
# Rows the editor shows before it scrolls inside itself, so the Apply button
# under it is never far away.
_EDITOR_ROWS = 12
_ROW_PX, _HEADER_PX = 35, 38


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

    The table is built to be quick to get through, not just to be correct:
    likely false positives come first and curated master-list names last, a
    status line says how big the job is, a filter narrows the list, and a
    few bulk buttons clear whole groups at once. Nothing here ever unticks a
    row on its own. Every ticked-off row is something the reviewer chose,
    and each bulk button says how many rows it will touch.

    The unticked set lives in ``st.session_state`` (``pending``), not in the
    editor widget, because a filter or a bulk button changes which rows the
    editor holds and an editor's own edit state does not survive that. The
    editor is re-keyed (``version``) whenever the rows or ticks change under
    it. ``excluded`` is the *applied* set; a change of it, or of the
    findings, resets the pending set to it.

    Not wrapped in a form, so the Apply button can show a pending count and
    turn primary the moment a tick changes. A review pass still costs one
    rebuild, not one per tick: ``st.data_editor`` reruns the script on every
    toggle, but the returned set only changes on the Apply click.
    """
    if not findings:
        return frozenset()

    state = st.session_state
    pending_key = f"{key_prefix}_review_pending"
    version_key = f"{key_prefix}_review_version"
    signature_key = f"{key_prefix}_review_signature"
    filter_key = f"{key_prefix}_review_filter"
    search_key = f"{key_prefix}_review_search"
    notice_key = f"{key_prefix}_review_notice"

    overview = detection_editor_dataframe(findings, excluded)
    signature = (frozenset(term_key(t) for t in overview["Detected text"]), excluded)
    if state.get(signature_key) != signature:
        state[signature_key] = signature
        state[pending_key] = excluded
        state[version_key] = state.get(version_key, 0) + 1
        state.pop(filter_key, None)
        state.pop(search_key, None)
    pending: frozenset[str] = state[pending_key]

    # Rendered in the review step's "Review" tab, so no expander of its own.
    with st.container():
        notice = state.pop(notice_key, None)
        if notice:
            st.success(notice)
        st.markdown(
            f"**Check what was detected ({plural(len(overview), 'distinct term')})**"
        )
        # Filled at the end, once this run's ticks are known; drawn here so
        # the line sits at the top where the reviewer looks first.
        status_slot = st.empty()
        with st.expander("How to read this table"):
            st.markdown(_HOW_TO_READ)

        clean = model_guess_count(overview) == 0
        if clean:
            st.success(_CLEAN_RUN)
        body = st.expander("Review anyway") if clean else st.container()

    with body:
        counts = {
            label: int((overview["Source"] == source).sum())
            for label, source in SOURCE_FILTERS.items()
        }
        filter_col, search_col = st.columns([3, 2])
        with filter_col:
            choice = st.segmented_control(
                "Show",
                options=[ALL_SOURCES, *(label for label, n in counts.items() if n)],
                default=ALL_SOURCES,
                format_func=lambda label: (
                    f"{label} ({counts[label]})" if label in counts else label
                ),
                key=filter_key,
            )
        with search_col:
            search = st.text_input(
                "Find a term", key=search_key, placeholder="e.g. total"
            )
        view = (choice, search)
        if view != state.get(f"{filter_key}_last"):
            state[f"{filter_key}_last"] = view
            state[version_key] += 1

        shown_all = search_editor_rows(filter_editor_rows(overview, choice), search)
        shown_keys = frozenset(term_key(t) for t in shown_all["Detected text"])
        untick_col, tick_col = st.columns(2)
        changed = False
        if untick_col.button(
            f"Untick all shown ({len(shown_keys)})",
            disabled=not shown_keys,
            width="stretch",
            key=f"{key_prefix}_review_untick_shown",
        ):
            pending, changed = pending | shown_keys, True
        if tick_col.button(
            f"Tick all shown ({len(shown_keys)})",
            disabled=not shown_keys,
            width="stretch",
            key=f"{key_prefix}_review_tick_shown",
        ):
            pending, changed = pending - shown_keys, True
        if changed:
            state[pending_key] = pending
            state[version_key] += 1

        # The only editable widget in this codebase. Everything else is
        # st.dataframe, deliberately: those tables are read-only records.
        # This one has to be editable, because the whole point is letting the
        # operator overrule a detection, and a tick box beside the offending
        # row is where they will look for it.
        table = search_editor_rows(
            filter_editor_rows(detection_editor_dataframe(findings, pending), choice),
            search,
        )
        edited = st.data_editor(
            table,
            width="stretch",
            hide_index=True,
            height=_HEADER_PX + _ROW_PX * max(1, min(len(table), _EDITOR_ROWS)),
            key=f"{key_prefix}_deselect_editor_{state[version_key]}",
            column_config={
                REDACT_COLUMN: st.column_config.CheckboxColumn(
                    REDACT_COLUMN,
                    help="Untick to leave this term visible in this document.",
                    default=True,
                ),
                "Confidence": st.column_config.NumberColumn(
                    "Confidence", format="%.2f"
                ),
                "Hint": st.column_config.TextColumn(
                    "Hint",
                    help="Why a model guess is worth a second look. Blank means "
                    "no particular reason; it does not mean the term is right.",
                ),
            },
            disabled=[c for c in table.columns if c != REDACT_COLUMN],
        )
        pending = merge_pending(pending, table, edited)
        state[pending_key] = pending
        clicked = _apply_button(f"{key_prefix}_apply", len(pending ^ excluded))

    status_slot.caption(review_status(overview, excluded, pending))
    if clicked:
        state[notice_key] = apply_notice(pending)

    # Ticks reach the script on every toggle, so the returned set must stay
    # the *applied* one until Apply is clicked: callers rebuild the output
    # whenever it changes. Only the click's own rerun returns the pending set.
    return pending if clicked else excluded


def _apply_button(key: str, n_changes: int) -> bool:
    """Draw the Apply button: primary with a count, or idle when nothing changed."""
    if n_changes:
        return st.button(
            f"Apply changes ({n_changes} pending)",
            type="primary",
            width="stretch",
            key=key,
        )
    st.button("Apply changes", disabled=True, width="stretch", key=f"{key}_idle")
    return False


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
