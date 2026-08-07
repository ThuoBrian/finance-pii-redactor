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

from collections.abc import Mapping, Sequence
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
) -> None:
    """Render the master-list summary line plus any data-quality warnings."""
    st.markdown("**Master list**")
    st.caption(_name_list_help(name_counts, master_list_path))
    for issue in issues or ():
        _render_issue(issue)
