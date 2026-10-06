"""Step tracker shown under the page title.

The tracker lives in a placeholder created at the top of the page, but each
flow only learns which step the user has reached further down (a button click
in this same rerun, or an early ``st.stop()``). Filling the placeholder again
replaces its content, so the last ``show_step`` call before the script ends is
what the user sees.
"""

from __future__ import annotations

from typing import Any

STEPS = ("Upload", "Set options", "Review", "Download")


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


def show_step(placeholder: Any, current: int) -> None:
    """Draw the tracker into ``placeholder`` (an ``st.empty()``)."""
    placeholder.markdown(steps_markdown(current), text_alignment="center")
