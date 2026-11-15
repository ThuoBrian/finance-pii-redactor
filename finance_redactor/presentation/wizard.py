"""One step on screen at a time: Upload, Options, Review, Download.

The app is still a single Streamlit page; session state says which step to
draw. Two Streamlit behaviours shape this module:

- A widget that is not drawn on a run loses its value. The option widgets
  are only drawn on step 2, so :func:`keep_option_choices` re-stores their
  values on every run; going back to Options then shows what the user chose,
  not the defaults. Only the keys listed here are touched: re-storing a
  button's value through session state raises.
- The uploaded file lives in the uploader widget, so the uploader is drawn on
  every step (folded away after step 1), and :func:`start_over` changes its
  key to empty it.
"""

from __future__ import annotations

from typing import Any

import streamlit as st

STEP_KEY = "wizard_step"
UPLOAD, OPTIONS, REVIEW, DOWNLOAD = 1, 2, 3, 4
_ROUND_KEY = "upload_round"
_START_OVER_CONFIRM_KEY = "start_over_confirm_pending"

# Option widgets whose values must survive steps where they are not drawn.
_OPTION_KEYS = (
    "excel_tabs",
    "excel_threshold",
    "excel_entities",
    "pdf_style",
    "pdf_custom_words",
    "pdf_redact_images",
    "pdf_read_scans",
    "docx_custom_words",
    "docx_threshold",
    "docx_entities",
)
_OPTION_PREFIXES = ("excel_cols_",)


def current() -> int:
    """Return the step being shown (1 to 4)."""
    return int(st.session_state.get(STEP_KEY, UPLOAD))


def go(step: int) -> None:
    """Show ``step`` from the next run on."""
    st.session_state[STEP_KEY] = step
    st.rerun()


def set_step(step: int) -> None:
    """Record ``step`` without rerunning (for use during a run that continues)."""
    st.session_state[STEP_KEY] = step


def keep_option_choices() -> None:
    """Re-store the option widgets' values so they survive the other steps."""
    state = st.session_state
    for key in list(state.keys()):
        if key in _OPTION_KEYS or str(key).startswith(_OPTION_PREFIXES):
            state[key] = state[key]


def upload_key() -> str:
    """Return the uploader's key; it changes on Start over, which empties it."""
    return f"upload_{st.session_state.get(_ROUND_KEY, 0)}"


def start_over() -> None:
    """Forget the file, the results and the choices, and go back to Upload.

    Clearing the session also drops the document and its findings from
    memory, which is the point for a tool that handles real names.
    """
    _clear_session()
    st.rerun()


def _clear_session() -> None:
    next_round = int(st.session_state.get(_ROUND_KEY, 0)) + 1
    st.session_state.clear()
    st.session_state[_ROUND_KEY] = next_round
    st.session_state[STEP_KEY] = UPLOAD


def _ask_start_over(asking: bool) -> None:
    st.session_state[_START_OVER_CONFIRM_KEY] = asking


def render_start_over() -> None:
    """Draw the sidebar's Start over button, with one confirm step.

    Start over throws away the findings, every review choice and the files
    built for download, so one misclick must not do it (the same two-step
    pattern as ``shutdown.render_quit_control``).

    The buttons act through ``on_click`` callbacks, never ``st.rerun()``: the
    sidebar is drawn before the uploader, and a rerun from here would end the
    run before the uploader is drawn, which makes Streamlit drop the file.
    """
    if st.session_state.get(_START_OVER_CONFIRM_KEY):
        st.warning(
            "Start over? This file's findings, your review choices and the "
            "downloads built from them will be lost. Download anything you "
            "need first."
        )
        yes, cancel = st.columns(2)
        yes.button(
            "Yes, start over",
            type="primary",
            width="stretch",
            key="start_over_yes",
            on_click=_clear_session,
        )
        cancel.button(
            "Cancel",
            width="stretch",
            key="start_over_cancel",
            on_click=_ask_start_over,
            args=(False,),
        )
        return
    st.button(
        "Start over",
        width="stretch",
        key="sidebar_start_over",
        on_click=_ask_start_over,
        args=(True,),
    )


def nav(
    *,
    back: tuple[str, int] | None = None,
    forward: tuple[str, int] | None = None,
    finish: bool = False,
    hold: str | None = None,
) -> None:
    """Draw the Back / Continue row under a step.

    ``finish`` puts "Redact another file" where Continue would be, for the
    last step. ``hold`` disables Continue and says why, above the row.
    """
    if hold:
        st.info(hold)
    left, _, right = st.columns([2, 3, 2])
    if back is not None and left.button(
        f"← {back[0]}", width="stretch", key=f"nav_back_{back[1]}"
    ):
        go(back[1])
    if forward is not None and right.button(
        f"{forward[0]} →",
        type="primary",
        width="stretch",
        key=f"nav_forward_{forward[1]}",
        disabled=bool(hold),
    ):
        go(forward[1])
    if finish and right.button(
        "Redact another file", width="stretch", key="nav_finish"
    ):
        start_over()


def download_cards() -> tuple[Any, Any]:
    """Draw the two Download cards and return them (safe to share, keep private).

    Sorting the files by who may see them is the point of the Download step:
    the classification is the card a file sits in, not a paragraph to read.
    """
    left, right = st.columns(2)
    safe = left.container(border=True)
    safe.markdown("**Safe to share** :green-badge[Internal]")
    private = right.container(border=True)
    private.markdown("**Keep private** :red-badge[Confidential]")
    return safe, private
