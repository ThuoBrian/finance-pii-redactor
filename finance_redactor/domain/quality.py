"""Master-list data-quality findings.

A :class:`QualityIssue` is one actionable problem (or advisory) detected in the master
list workbook at load time — duplicate names, conflicting IDs, blank IDs, reused IDs.
The repository produces them; the presentation layer renders them as warnings in the
Advanced settings panel so the IDs the tool emits are trustworthy.

Framework-free: a plain frozen dataclass, unit-testable without pandas or Streamlit.
"""

from __future__ import annotations

from dataclasses import dataclass

# Severities — mapped to Streamlit widgets by the presentation layer.
SEVERITY_WARNING = "warning"
SEVERITY_INFO = "info"


@dataclass(frozen=True)
class QualityIssue:
    """One master-list data-quality finding.

    ``examples`` is a small, already-formatted list (capped by the producer) shown as
    bullets; ``total`` is the full occurrence count, used for the "... and N more" line
    when it exceeds ``len(examples)``.
    """

    kind: str
    severity: str
    title: str
    detail: str
    examples: list[str]
    total: int


def cap_examples(items: list[str], limit: int = 5) -> tuple[list[str], int]:
    """Return ``(first-limit items, total count)`` for an examples list."""
    return items[:limit], len(items)
