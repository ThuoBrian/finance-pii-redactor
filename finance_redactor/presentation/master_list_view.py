"""Shared rendering of the master-list status panel.

Both the Excel and PDF flows show the same panel inside their Advanced settings
expander: a one-line summary of loaded entries plus a warning for each data-quality
issue found in the workbook (duplicate names, conflicting or reused IDs, blank IDs).
The warnings are actionable — they tell the user what to fix, at whichever path
the workbook is actually being read from (``Settings.master_list_file`` -
normally the local ``data/`` folder, but ``FPR_MASTER_LIST_DIR`` can point it at
a shared location instead - see ``data/README.md``), so the IDs the tool emits
are trustworthy.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import streamlit as st

from finance_redactor.domain.quality import SEVERITY_WARNING, QualityIssue


def _name_list_help(counts: Mapping[str, int], master_list_path: Path) -> str:
    total = sum(counts.values())
    by_cat = ", ".join(f"{n:,} {cat}" for cat, n in sorted(counts.items())) or "none"
    return (
        f"Loaded {total:,} master-list entr(y/ies): {by_cat}. Edit "
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
    *,
    on_refresh: Callable[[], None] | None = None,
) -> None:
    """Render the master-list summary line plus any data-quality warnings.

    ``on_refresh``, when given, renders a "Refresh master list" button that
    calls it (expected to clear the cached master-list bundle - see
    ``app.py``'s ``_get_master_list_bundle``) and reruns the page. This is
    needed for anything *other* than the app's own first load: Streamlit only
    re-checks the workbook's modification time on a rerun (a widget
    interaction or a browser refresh), so editing the workbook - or fixing
    its location via the "Set up your shared master list" dialog - has no
    visible effect until something triggers one. Clearing the cache outright
    (rather than just rerunning) also covers the edge case where the
    modification time hasn't actually changed yet (e.g. a Box Drive sync
    still in flight), which a bare rerun would not catch.
    """
    st.markdown("**Master list**")
    st.caption(_name_list_help(name_counts, master_list_path))
    for issue in issues or ():
        _render_issue(issue)
    if on_refresh is not None and st.button(
        "🔄 Refresh master list",
        help=(
            "Re-check the master list for changes - use this after editing "
            "the workbook, or after fixing its location, instead of "
            "reloading the whole page."
        ),
    ):
        on_refresh()
        st.rerun()
