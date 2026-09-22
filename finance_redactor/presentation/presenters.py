"""View formatters: turn domain results into UI-ready artifacts.

These were previously private helpers scattered inside the UI and PDF modules
(``_make_highlighted_html``, ``_build_findings_table``, ``_findings_to_dataframe``).
Collected here, they are the presentation layer's single rendering vocabulary.
The HTML/markup is byte-for-byte identical to the original.
"""

from __future__ import annotations

import html
from collections import Counter
from collections.abc import Sequence

import pandas as pd

from finance_redactor.application.results import ExcelScanResult
from finance_redactor.domain.entities import Finding
from finance_redactor.domain.pseudonyms import Assignment, normalize

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
    "Possible match",
]

# The PDF mapping file. Deliberately has no name column - see
# :func:`pdf_mapping_dataframe`.
_PDF_MAPPING_COLUMNS = [
    "Label",
    "Internal ID",
    "Category",
    "Entity type",
    "Flagged",
    "Master list",
]

# The PDF on-screen review table. Shows names; never written to a file.
_PDF_REVIEW_COLUMNS = [
    "Label",
    "Original name",
    "Entity type",
    "Category",
    "Internal ID",
    "Flagged",
    "Possible match",
]

_FLAG_NOT_CURATED = "not in master list"
_FLAG_AMBIGUOUS = "ambiguous - matched several master-list rows"


def highlighted_html(df: pd.DataFrame, cell_keys: set[tuple[int, str]], bg: str) -> str:
    """Render ``df`` as an HTML table, shading the given cells with ``bg``.

    Cell and header text is HTML-escaped: the values come from user-uploaded
    files (often authored by a third party, e.g. a vendor's spreadsheet), so an
    unescaped cell containing markup would otherwise render/execute in the
    browser via the ``unsafe_allow_html=True`` call at the render site.
    """
    highlighted = {(r, c) for r, c in cell_keys if c in df.columns and r in df.index}
    rows_html = []
    for row_idx, row in df.iterrows():
        cells = []
        for col in df.columns:
            val = "" if pd.isna(row[col]) else html.escape(str(row[col]))
            style = (
                f' style="background:{bg};padding:4px 8px"'
                if (row_idx, col) in highlighted
                else ' style="padding:4px 8px"'
            )
            cells.append(f"<td{style}>{val}</td>")
        rows_html.append("<tr>" + "".join(cells) + "</tr>")
    headers = "".join(
        f'<th style="padding:4px 8px;text-align:left;border-bottom:1px solid #ccc">'
        f"{html.escape(str(c))}</th>"
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


def scan_result_findings(scan_result: ExcelScanResult) -> list[Finding]:
    """Flatten an Excel scan result into :class:`Finding` objects.

    Only so Excel can share :func:`detection_editor_dataframe` with the PDF
    and Word flows, which already work in ``Finding``. ``page`` carries the
    row index here, the same way it carries a paragraph ordinal in the Word
    flow - see :func:`findings_dataframe`.
    """
    return [
        Finding(
            page=cell.row,
            detected_text=detection.text,
            entity_type=detection.entity_type,
            score=detection.score,
            source=detection.source,
        )
        for cell in scan_result.findings
        for detection in cell.detections
    ]


def crosswalk_dataframe(crosswalk: list[Assignment]) -> pd.DataFrame:
    """Render the name->pseudonym crosswalk as a UI/download DataFrame.

    ``Flagged`` marks auto-generated placeholders (names not in the master list)
    that a reviewer should confirm and ideally add to the master list.
    ``Possible match`` is a typo-tolerant hint (see ``domain/fuzzy.py``) for
    flagged rows only - a nearby curated name the reviewer may want to check,
    never applied automatically.
    """
    rows = [
        {
            "Original name": a.original_name,
            "Entity type": a.entity_type,
            "Category": a.category or "(unknown)",
            "Pseudonym": a.pseudonym,
            "Flagged": "yes" if a.auto else "",
            "Possible match": (
                f"{a.suggested_name} ({a.suggested_pseudonym}, "
                f"{a.suggested_score:.0%} match)"
                if a.suggested_pseudonym
                else ""
            ),
        }
        for a in crosswalk
    ]
    return pd.DataFrame(rows, columns=_CROSSWALK_COLUMNS)


def pdf_review_dataframe(crosswalk: list[Assignment]) -> pd.DataFrame:
    """Render the PDF crosswalk for the on-screen review table only.

    Includes ``Original name`` so the operator can check that ``[001]`` really
    is who they think it is, and the ``Internal ID`` it resolved to. This is a
    screen-only frame: it is never written to a file. The downloadable frame
    is :func:`pdf_mapping_dataframe`, which has no name column at all - they
    are separate functions precisely so that editing the review table cannot
    put names into the download.
    """
    rows = [
        {
            "Label": a.label,
            "Original name": a.original_name,
            "Entity type": a.entity_type,
            "Category": a.category or "(unknown)",
            "Internal ID": a.internal_id or "",
            "Flagged": (
                _FLAG_AMBIGUOUS if a.ambiguous else _FLAG_NOT_CURATED if a.auto else ""
            ),
            "Possible match": (
                f"{a.suggested_name} ({a.suggested_pseudonym}, "
                f"{a.suggested_score:.0%} match)"
                if a.suggested_pseudonym
                else ""
            ),
        }
        for a in crosswalk
    ]
    return pd.DataFrame(rows, columns=_PDF_REVIEW_COLUMNS)


def pdf_mapping_dataframe(
    crosswalk: list[Assignment], master_list_fingerprint: str = ""
) -> pd.DataFrame:
    """Render the PDF label->Internal ID mapping for download.

    **This frame must never contain a name.** It is the reason the two-hop
    scheme exists: the redacted PDF shows only ``[001]``, this file says
    ``[001] = 17728``, and only the access-controlled master list turns 17728
    into a person or organization. Because it carries no names it is
    *Internal* rather than *Confidential*, so it can travel with the redacted
    PDF. Add a name column here and that property is gone, along with the
    point of the whole design. ``crosswalk_dataframe`` is the names-bearing
    frame, for the on-screen review table and for the Excel/Word flows.

    Rows that resolved against the master list carry its raw ``Internal ID``.
    Rows that did not carry their deterministic auto-pseudonym instead (e.g.
    ``CST-AUTO-3F9A1``) - a hash of the name, not the name, so the file stays
    names-free, and content-addressed so the same unresolved entity still
    links across documents. It cannot be mistaken for a master-list ID, and
    the ``Flagged`` column says why it is there. Note the hash is a *linkage*
    token, not a secrecy guarantee: a short digest of a guessable name is
    confirmable by anyone who can guess the name.

    ``master_list_fingerprint`` stamps which master list this mapping decodes
    against. With no names in the file there is nothing to cross-check a
    stale decode against, so an edited or reused ``Internal ID`` would
    otherwise mis-decode silently.
    """
    rows = [
        {
            "Label": a.label,
            "Internal ID": a.internal_id or a.pseudonym,
            "Category": a.category or "(unknown)",
            "Entity type": a.entity_type,
            "Flagged": (
                _FLAG_AMBIGUOUS if a.ambiguous else _FLAG_NOT_CURATED if a.auto else ""
            ),
            "Master list": master_list_fingerprint,
        }
        for a in crosswalk
    ]
    return pd.DataFrame(rows, columns=_PDF_MAPPING_COLUMNS)


def findings_dataframe(findings: list[Finding], page_label: str) -> pd.DataFrame:
    """Render PDF/Word findings as a readable DataFrame for the UI.

    Both flows reuse :class:`Finding`, whose ``page`` field holds a PDF page
    number or a Word paragraph/block ordinal depending on the caller -
    ``page_label`` names that column accordingly (``"Page"`` or
    ``"Paragraph"``).
    """
    return pd.DataFrame(
        [
            {
                page_label: f.page + 1,
                "Detected text": f.detected_text,
                "Entity type": f.entity_type,
                "Confidence": round(f.score, 2),
                "Source": f.source.value,
            }
            for f in findings
        ]
    )


# The deselect editor. One row per distinct detected term, because a word
# appearing forty times is one decision, not forty.
_EDITOR_COLUMNS = [
    "Redact?",
    "Detected text",
    "Entity type",
    "Source",
    "Occurrences",
]

_REDACT_COLUMN = "Redact?"
_TERM_COLUMN = "Detected text"


def detection_editor_dataframe(
    findings: Sequence[Finding], excluded: frozenset[str] = frozenset()
) -> pd.DataFrame:
    """Render detections as a tickable table for rejecting false positives.

    One row per distinct detected term, ordered by first appearance, with
    ``Redact?`` seeded from ``excluded`` so an unticked row stays unticked
    across reruns. Pair with :func:`excluded_terms` to read the ticks back.

    ``Source`` is here on purpose: it is what tells the operator which fix
    applies. ``master list`` means a row in the workbook matches this word, so
    unticking is a per-document patch and editing the workbook is the real fix.
    ``model`` means spaCy guessed, and the confidence threshold is a lever.
    ``custom word`` means it came from the words box, so clearing that box
    fixes it.

    Grouping is keyed on :func:`normalize`, matching how ``exclude`` is
    compared in the redaction services, so a term ticked off here matches every
    casing and spacing of itself in the document.
    """
    # Insertion-ordered, so rows read in order of first appearance. Counts are
    # kept in their own dict rather than mutated inside the row dicts, which
    # keeps both dicts singly typed.
    first_seen: dict[str, Finding] = {}
    counts: Counter[str] = Counter()
    for finding in findings:
        key = normalize(finding.detected_text)
        first_seen.setdefault(key, finding)
        counts[key] += 1

    rows = [
        {
            _REDACT_COLUMN: key not in excluded,
            _TERM_COLUMN: finding.detected_text,
            "Entity type": finding.entity_type,
            "Source": finding.source.value,
            "Occurrences": counts[key],
        }
        for key, finding in first_seen.items()
    ]
    return pd.DataFrame(rows, columns=_EDITOR_COLUMNS)


def excluded_terms(edited: pd.DataFrame) -> frozenset[str]:
    """Read back the normalized terms the operator unticked in the editor.

    The inverse of :func:`detection_editor_dataframe`. Returns normalized
    terms, ready to hand to a redaction service's ``exclude`` argument.

    A missing or empty frame yields an empty set, which means "redact
    everything" - the safe direction if the widget state is ever lost.
    """
    if edited is None or edited.empty or _REDACT_COLUMN not in edited.columns:
        return frozenset()
    unticked = edited.loc[~edited[_REDACT_COLUMN].fillna(True).astype(bool)]
    return frozenset(normalize(str(term)) for term in unticked[_TERM_COLUMN])
