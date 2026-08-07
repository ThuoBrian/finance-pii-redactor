"""Shared rendering of the master-list status panel.

Both the Excel and PDF flows show the same panel inside their Advanced settings
expander: a one-line summary of loaded entries (plus when the workbook was last
modified - the giveaway for "did a teammate's edit actually land yet?" that a
raw entry count alone can miss, e.g. someone fixing a typo in an existing row
without adding/removing one) and a warning for each data-quality issue found in
the workbook (duplicate names, conflicting or reused IDs, blank IDs). The
warnings are actionable — they tell the user what to fix, at whichever path the
workbook is actually being read from (``Settings.master_list_file`` - normally
the local ``data/`` folder, but ``FPR_MASTER_LIST_DIR`` can point it at a shared
location instead - see ``data/README.md``), so the IDs the tool emits are
trustworthy.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path

import streamlit as st

from finance_redactor.domain.quality import SEVERITY_WARNING, QualityIssue

_MONTH_ABBR = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


def _format_absolute(dt: datetime) -> str:
    """Format a naive-local datetime without relying on platform strftime quirks.

    ``%-d``/``%-I`` (no leading zero) are GNU extensions Windows' C runtime
    doesn't reliably support, so this builds the string by hand instead -
    portable across Windows, macOS, and Linux.
    """
    hour12 = dt.hour % 12 or 12
    period = "AM" if dt.hour < 12 else "PM"
    return f"{_MONTH_ABBR[dt.month - 1]} {dt.day}, {dt.year} at {hour12}:{dt.minute:02d} {period}"


def _relative_time(seconds_ago: float) -> str:
    """Return a short 'N unit(s) ago' clause for a non-negative age in seconds."""
    seconds_ago = max(seconds_ago, 0)
    if seconds_ago < 60:
        return "just now"
    minutes = int(seconds_ago // 60)
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''} ago"
    days = hours // 24
    return f"{days} day{'s' if days != 1 else ''} ago"


def _name_list_help(
    counts: Mapping[str, int],
    master_list_path: Path,
    last_updated: datetime | None,
    now: datetime,
) -> str:
    total = sum(counts.values())
    by_cat = ", ".join(f"{n:,} {cat}" for cat, n in sorted(counts.items())) or "none"
    updated_clause = ""
    if last_updated is not None:
        age = (now - last_updated).total_seconds()
        updated_clause = (
            f" Last updated {_format_absolute(last_updated)} ({_relative_time(age)})."
        )
    return (
        f"Loaded {total:,} master-list entr(y/ies): {by_cat}.{updated_clause} Edit "
        f"`{master_list_path}` "
        "and refresh the page to update it."
    )


def _render_issue(issue: QualityIssue) -> None:
    """Render one quality issue as a warning or info box with bulleted examples."""
    lines = "\n".join(f"- {example}" for example in issue.examples)
    remaining = issue.total - len(issue.examples)
    if remaining > 0:
        lines += f"\n- ... and {remaining} more"
    body = f"**{issue.title}.** {issue.detail}\n\n{lines}"
    if issue.severity == SEVERITY_WARNING:
        st.warning(body)
    else:
        st.info(body)


def render_master_list_status(
    name_counts: Mapping[str, int],
    issues: Sequence[QualityIssue] | None,
    master_list_path: Path,
    last_updated: datetime | None,
) -> None:
    """Render the master-list summary line plus any data-quality warnings."""
    st.markdown("**Master list**")
    st.caption(
        _name_list_help(name_counts, master_list_path, last_updated, datetime.now())
    )
    for issue in issues or ():
        _render_issue(issue)
