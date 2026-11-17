"""Step tracker shown under the page title.

The tracker lives in a placeholder created at the top of the page, but each
flow only learns which step the user has reached further down (a button click
in this same rerun, or an early ``st.stop()``). Filling the placeholder again
replaces its content, so the last ``show_step`` call before the script ends is
what the user sees.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import streamlit as st

from finance_redactor.presentation.presenters import plural

STEPS = ("Upload", "Options", "Review", "Download")
_REVIEW = 3


def steps_markdown(current: int) -> str:
    """Render the tracker as Streamlit badges; ``current`` is the 1-based step.

    Uses Streamlit's own ``:color-badge[...]`` markdown directive (no HTML):
    green with a tick for done, blue for the active step, gray for upcoming.
    """
    parts = []
    for number, name in enumerate(STEPS, start=1):
        label = f"{number}. {name}"
        if number < current:
            parts.append(f":green-badge[:material/check: {label}]")
        elif number == current:
            parts.append(f":blue-badge[:material/arrow_forward: {label}]")
        else:
            parts.append(f":gray-badge[{label}]")
    return " ".join(parts)


def progress_bar(unit: str) -> Callable[[int, int], None]:
    """Draw a progress bar and return the ``(done, total)`` callback that moves it.

    For a scan's ``on_progress``, so a long run (OCR above all) shows how far
    it has got instead of looking frozen. ``unit`` names what is counted.
    """
    bar = st.progress(0.0)

    def update(done: int, total: int) -> None:
        bar.progress(
            done / total if total else 1.0,
            text=f"{done:,} of {plural(total, unit)} checked",
        )

    return update


def show_step(placeholder: Any, current: int) -> None:
    """Draw the tracker into ``placeholder`` (an ``st.empty()``), and set the layout.

    Review gets the wide layout: in the centered column a 10-column Excel
    preview showed 4 columns, and the review table's details view hid 3 of
    its 8. The prose steps stay centered. The pinned Streamlit allows
    ``st.set_page_config`` to be called again in a run, and the last call
    wins, as the tracker's does.
    """
    st.set_page_config(layout="wide" if current == _REVIEW else "centered")
    placeholder.markdown(steps_markdown(current), text_alignment="center")
