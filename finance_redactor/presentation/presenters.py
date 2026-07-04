"""View formatters: turn domain results into UI-ready artifacts.

These were previously private helpers scattered inside the UI and PDF modules
(``_make_highlighted_html``, ``_build_findings_table``, ``_findings_to_dataframe``).
Collected here, they are the presentation layer's single rendering vocabulary.
The HTML/markup is byte-for-byte identical to the original.
"""

from __future__ import annotations

import pandas as pd

from finance_redactor.application.results import ExcelScanResult
from finance_redactor.domain.entities import Finding
from finance_redactor.domain.pseudonyms import Assignment

_EXCEL_COLUMNS = [
    "Row",
    "Column",
    "Detected text",
    "Entity type",
    "Confidence",
    "Source",
]

_CROSSWALK_COLUMNS = [
    "Original name",
    "Entity type",
    "Category",
    "Pseudonym",
    "Flagged",
]


def highlighted_html(df: pd.DataFrame, cell_keys: set[tuple[int, str]], bg: str) -> str:
    """Render ``df`` as an HTML table, shading the given cells with ``bg``."""
    highlighted = {(r, c) for r, c in cell_keys if c in df.columns and r in df.index}
    rows_html = []
    for row_idx, row in df.iterrows():
        cells = []
        for col in df.columns:
            val = "" if pd.isna(row[col]) else str(row[col])
            style = (
                f' style="background:{bg};padding:4px 8px"'
                if (row_idx, col) in highlighted
                else ' style="padding:4px 8px"'
            )
            cells.append(f"<td{style}>{val}</td>")
        rows_html.append("<tr>" + "".join(cells) + "</tr>")
    headers = "".join(
        f'<th style="padding:4px 8px;text-align:left;border-bottom:1px solid #ccc">{c}</th>'
        for c in df.columns
    )
    return (
        '<div style="overflow-x:auto"><table style="border-collapse:collapse;'
        f'font-size:0.85em;width:100%"><thead><tr>{headers}</tr></thead>'
        f"<tbody>{''.join(rows_html)}</tbody></table></div>"
    )


def excel_findings_dataframe(scan_result: ExcelScanResult) -> pd.DataFrame:
    """Flatten an Excel scan result into a per-detection findings table."""
    rows = [
        {
            "Row": cell.row + 1,
            "Column": cell.column,
            "Detected text": detection.text,
            "Entity type": detection.entity_type,
            "Confidence": round(detection.score, 2),
            "Source": detection.source.value,
        }
        for cell in scan_result.findings
        for detection in cell.detections
    ]
    return pd.DataFrame(rows, columns=_EXCEL_COLUMNS)


def crosswalk_dataframe(crosswalk: list[Assignment]) -> pd.DataFrame:
    """Render the name->pseudonym crosswalk as a UI/download DataFrame.

    ``Flagged`` marks auto-generated placeholders (names not in the master list)
    that a reviewer should confirm and ideally add to the master list.
    """
    rows = [
        {
            "Original name": a.original_name,
            "Entity type": a.entity_type,
            "Category": a.category or "(unknown)",
            "Pseudonym": a.pseudonym,
            "Flagged": "yes" if a.auto else "",
        }
        for a in crosswalk
    ]
    return pd.DataFrame(rows, columns=_CROSSWALK_COLUMNS)


def pdf_findings_dataframe(findings: list[Finding]) -> pd.DataFrame:
    """Render PDF findings as a readable DataFrame for the UI."""
    return pd.DataFrame(
        [
            {
                "Page": f.page + 1,
                "Detected text": f.detected_text,
                "Entity type": f.entity_type,
                "Confidence": round(f.score, 2),
                "Source": f.source.value,
            }
            for f in findings
        ]
    )
