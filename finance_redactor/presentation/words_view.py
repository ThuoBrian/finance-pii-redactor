"""The "words to add" box, shown on the Review step of the PDF and Word flows.

It used to sit on Options, before anything had been found, so the user had to
guess what the scan would miss. On Review the findings are on screen, and a
name the master list and the model both missed can be typed in right there.
Typed words are matched while the file is rebuilt, not during the scan, so
adding one costs a quick rebuild and never a rescan (or another OCR pass).

The box keeps its old session key (``<prefix>_custom_words``), so words still
carry over to the next file uploaded in the same session, and the first build
of that file uses them.
"""

from __future__ import annotations

import re

import streamlit as st

# A typed word that is itself a label, e.g. "[001]". Redacting it would mean
# redacting this tool's own output on a second pass.
_LABEL_SHAPED = re.compile(r"^\[\d+\]$")


def parse_words(text: str) -> list[str]:
    """Return the non-blank lines of ``text``, stripped, in order."""
    return [line.strip() for line in text.splitlines() if line.strip()]


def typed_words(key_prefix: str) -> list[str]:
    """Return the words currently in the box (used for a file's first build)."""
    return parse_words(str(st.session_state.get(_key(key_prefix), "")))


def render_words_box(
    key_prefix: str, applied: list[str], *, warn_label_shaped: bool = False
) -> list[str]:
    """Draw the box and its button; return the words the file should use.

    That is the box's words on the click that adds them, and ``applied`` on
    every other run. ``warn_label_shaped`` is for PDF, whose labels look like
    ``[001]``.
    """
    key = _key(key_prefix)
    st.session_state.setdefault(key, "\n".join(applied))
    pending = parse_words(str(st.session_state[key]))
    with st.expander(
        "Missed something? Add words or phrases",
        expanded=bool(applied) or pending != applied,
    ):
        st.text_area(
            "Words or phrases to add",
            help=(
                "One per line: a name that is not on the master list and the "
                "model missed, a project codename, a case number. Each is "
                "redacted everywhere it appears, like a found name. Names on "
                "the master list, emails and websites are caught already. Not "
                "saved anywhere once you start over."
            ),
            key=key,
        )
        pending = parse_words(str(st.session_state[key]))
        if warn_label_shaped and any(_LABEL_SHAPED.match(w) for w in pending):
            st.warning(
                "One of your words looks like a redaction label (e.g. `[001]`). "
                "That is the shape this tool writes into the PDF, so redacting "
                "it would redact the tool's own output. Remove it unless the "
                "document genuinely contains that text for another reason."
            )
        changed = pending != applied
        clicked = st.button(
            "Add and rebuild",
            type="primary" if changed else "secondary",
            disabled=not changed,
            width="stretch",
            key=f"{key_prefix}_words_apply",
        )
    return pending if clicked else applied


def unapplied_words_note(key_prefix: str, applied: list[str]) -> str | None:
    """Return why Continue must wait, or ``None`` if the box matches the file.

    Continuing with words typed but not added would download a file that
    still shows them.
    """
    if typed_words(key_prefix) == applied:
        return None
    return (
        "You have typed words that are not in the file yet. Click **Add and "
        "rebuild** first, or remove them, then continue."
    )


def _key(key_prefix: str) -> str:
    return f"{key_prefix}_custom_words"
