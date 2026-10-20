"""The master-list card in the sidebar.

Every format depends on the master list, so its state sits in the sidebar on
every step instead of inside each format's options: how many names are loaded,
by category, when the workbook last changed, how many data-quality issues it
has, and a Refresh button. The issues themselves open from a badge that says
how many there are, so a list that needs tidying is visible at a glance even
with the details folded away.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import streamlit as st

from finance_redactor.domain.quality import SEVERITY_WARNING, QualityIssue
from finance_redactor.presentation.presenters import plural


def _counts_line(counts: Mapping[str, int]) -> str:
    """Return e.g. ``"1 Funder · 3 Staff · 2 Vendor"``, or ``"none"``."""
    return " · ".join(f"{n:,} {cat}" for cat, n in sorted(counts.items())) or "none"


def time_ago(seconds: float) -> str:
    """Return a rough, plain age such as ``"just now"`` or ``"3 hours ago"``."""
    if seconds < 90:
        return "just now"
    for unit, size in (("day", 86400), ("hour", 3600), ("minute", 60)):
        if seconds >= size:
            return f"{plural(int(seconds // size), unit)} ago"
    return "just now"  # unreachable, keeps mypy happy


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


def render_master_list_card(
    name_counts: Mapping[str, int],
    issues: Sequence[QualityIssue] | None,
    master_list_path: Path,
    *,
    age_seconds: float | None = None,
    on_refresh: Callable[[], None] | None = None,
) -> None:
    """Render the master-list card: size, freshness, issues, Refresh.

    ``on_refresh`` clears the cached master-list bundle (see ``app.py``'s
    ``_get_master_list_bundle``) and reruns. Streamlit only re-checks the
    workbook's modification time on a rerun, and a Box Drive sync can land
    the new version without changing it yet, so an explicit clear is the
    reliable way to pick up an edit.
    """
    total = sum(name_counts.values())
    issues = list(issues or ())
    with st.container(border=True):
        st.markdown("**Master list**")
        if total:
            st.markdown(f"**{plural(total, 'name')}** :green-badge[ready]")
        else:
            st.markdown(":red-badge[no names loaded]")
        line = _counts_line(name_counts)
        if age_seconds is not None:
            line += f" · updated {time_ago(age_seconds)}"
        st.caption(line)
        if issues:
            n_warn = sum(1 for i in issues if i.severity == SEVERITY_WARNING)
            badge = ":orange-badge" if n_warn else ":blue-badge"
            with st.expander(f"{badge}[{plural(len(issues), 'thing')} to tidy]"):
                for issue in issues:
                    _render_issue(issue)
        with st.expander("Where is it?"):
            st.caption(f"`{master_list_path}`")
            st.caption("Save and close the workbook in Excel, then Refresh.")
        if on_refresh is not None and st.button(
            "Refresh",
            key="master_list_refresh",
            width="stretch",
            help="Re-read the master list after editing it or changing its folder.",
        ):
            on_refresh()
            st.rerun()
