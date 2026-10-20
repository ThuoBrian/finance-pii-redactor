"""View formatters: turn domain results into UI-ready artifacts.

These were previously private helpers scattered inside the UI and PDF modules
(``_build_findings_table``, ``_findings_to_dataframe``).
Collected here, they are the presentation layer's single rendering vocabulary.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence

import pandas as pd
from pandas.io.formats.style import Styler

from finance_redactor.application.ports import SheetFormatting
from finance_redactor.application.results import WorkbookScanResult
from finance_redactor.domain.entities import DetectionSource, Finding
from finance_redactor.domain.pseudonyms import Assignment, normalize
from finance_redactor.domain.review_hints import review_hint

_EXCEL_COLUMNS = [
    "Sheet",
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

# The optional PDF mapping that carries names. A separate frame from the one
# above, on purpose; see :func:`pdf_mapping_with_names_dataframe`.
_PDF_MAPPING_WITH_NAMES_COLUMNS = [
    "Label",
    "Original name",
    "Internal ID",
    "Category",
    "Entity type",
    "Flagged",
    "Possible match",
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


# Matches the fill the downloaded workbook uses (excel_gateway._HIGHLIGHT_FILL),
# so what the reviewer sees on screen is what they get in Excel.
HIGHLIGHT_HEX = "#FFFF00"
# Colour alone is invisible to some readers, so a changed cell also carries
# this prefix in its text.
CHANGED_MARKER = "» "
PREVIEW_MAX_ROWS = 500


THRESHOLD_HELP = (
    "How sure the tool must be before it hides something. Lower catches more "
    "(fewer missed names, but more words that were not names); higher catches "
    "less. Lowering it is the safe direction. If unsure, keep the default. "
    "Do not go above 0.90 - that stops matching every name on the master list."
)
ENTITY_HELP = (
    "The kinds of sensitive information to look for: people, organizations, "
    "email addresses, websites, and bank or payment details (shown as a fixed "
    "mask like [ACCOUNT] rather than a pseudonym). Remove a kind only if you "
    "are sure the file has none of it."
)


def entity_label(entity_type: str) -> str:
    """Readable form of an entity code, e.g. ``EMAIL_ADDRESS`` -> ``Email address``."""
    return entity_type.replace("_", " ").capitalize()


def plural(count: int, singular: str, plural_form: str | None = None) -> str:
    """Return ``"1 name"`` / ``"2 names"``: a count with the right noun form."""
    word = singular if count == 1 else (plural_form or f"{singular}s")
    return f"{count:,} {word}"


def _marked_positions(
    shown: pd.DataFrame, cell_keys: set[tuple[int, str]]
) -> set[tuple[int, int]]:
    """Positions (row, col) in ``shown`` of the cells named by ``cell_keys``."""
    row_pos = {label: i for i, label in enumerate(shown.index)}
    col_pos = {label: j for j, label in enumerate(shown.columns)}
    return {
        (row_pos[r], col_pos[c]) for r, c in cell_keys if r in row_pos and c in col_pos
    }


def preview_hidden_count(
    df: pd.DataFrame,
    cell_keys: set[tuple[int, str]],
    max_rows: int = PREVIEW_MAX_ROWS,
) -> int:
    """Count highlighted cells that fall below the row cap and so are not shown."""
    visible = set(df.index[:max_rows])
    return sum(
        1
        for r, c in cell_keys
        if c in df.columns and r in df.index and r not in visible
    )


def preview_styler(
    df: pd.DataFrame,
    cell_keys: set[tuple[int, str]],
    max_rows: int = PREVIEW_MAX_ROWS,
) -> Styler:
    """Build the on-screen preview: first ``max_rows`` rows, flagged cells marked.

    Returned for ``st.dataframe``, which draws cells on a canvas as text, so a
    cell containing markup is shown literally and nothing here needs HTML. All
    values are turned into text, flagged cells get :data:`CHANGED_MARKER` in
    front, and also a yellow fill (dark text, so it reads on any theme).
    Row-capped because a preview of a very large sheet only slows the page;
    the download always has every row, and :func:`preview_hidden_count` tells the
    caller say how many flagged cells the cap hid.
    """
    shown = df.head(max_rows)
    marked = _marked_positions(shown, cell_keys)
    text = shown.map(lambda v: "" if pd.isna(v) else str(v))
    for i, j in marked:
        text.iat[i, j] = f"{CHANGED_MARKER}{text.iat[i, j]}"
    css = pd.DataFrame("", index=text.index, columns=text.columns)
    for i, j in marked:
        css.iat[i, j] = f"background-color: {HIGHLIGHT_HEX}; color: #1a1a1a"
    return text.style.apply(lambda _: css, axis=None)


# Shown in the Column field of a finding that sits in a tab's name, not a cell.
TAB_NAME_LABEL = "(tab name)"


def excel_findings_dataframe(scan_result: WorkbookScanResult) -> pd.DataFrame:
    """Flatten a workbook scan result into a per-detection findings table."""
    rows: list[dict[str, object]] = [
        {
            "Sheet": sheet,
            "Row": cell.row + 1,
            "Column": cell.column,
            "Detected text": detection.text,
            "Entity type": detection.entity_type,
            "Confidence": round(detection.score, 2),
            "Source": detection.source.value,
        }
        for sheet, sheet_result in scan_result.sheets.items()
        for cell in sheet_result.findings
        for detection in cell.detections
    ]
    rows += [
        {
            "Sheet": sheet,
            "Row": None,
            "Column": TAB_NAME_LABEL,
            "Detected text": detection.text,
            "Entity type": detection.entity_type,
            "Confidence": round(detection.score, 2),
            "Source": detection.source.value,
        }
        for sheet, detections in scan_result.tab_names.items()
        for detection in detections
    ]
    return pd.DataFrame(rows, columns=_EXCEL_COLUMNS)


def scan_result_findings(scan_result: WorkbookScanResult) -> list[Finding]:
    """Flatten a workbook scan result into :class:`Finding` objects.

    Only so Excel can share :func:`detection_editor_dataframe` with the PDF
    and Word flows, which already work in ``Finding``. ``page`` carries the
    row index here, the same way it carries a paragraph ordinal in the Word
    flow - see :func:`findings_dataframe` - and ``-1`` for a tab name.
    """
    cell_detections = [
        (cell.row, detection)
        for sheet_result in scan_result.sheets.values()
        for cell in sheet_result.findings
        for detection in cell.detections
    ]
    name_detections = [
        (-1, detection)
        for detections in scan_result.tab_names.values()
        for detection in detections
    ]
    return [
        Finding(
            page=page,
            detected_text=detection.text,
            entity_type=detection.entity_type,
            score=detection.score,
            source=detection.source,
        )
        for page, detection in cell_detections + name_detections
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

    A user who needs names in the mapping gets them from
    :func:`pdf_mapping_with_names_dataframe`, a separate, opt-in, Confidential
    file. Do not add a name column here.
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


def pdf_mapping_with_names_dataframe(
    crosswalk: list[Assignment], master_list_fingerprint: str = ""
) -> pd.DataFrame:
    """Render the PDF mapping *with* names, for the opt-in Confidential download.

    **This frame holds names, so its file is Confidential** and must never be
    kept with the redacted PDF; the warning beside its download button says so.
    It exists for people who need to read a mapping without going to the master
    list. It is deliberately not a flag on :func:`pdf_mapping_dataframe`: that
    frame is Internal because it has no name column, and a shared code path
    with a switch is how a name reaches a download that promised none. The
    default download is unchanged and the names file is only built when the
    user turns it on.

    Same rows and order as the names-free mapping, plus ``Original name`` (as it
    appeared in the document) and the ``Possible match`` hint the review table
    shows.
    """
    rows = [
        {
            "Label": a.label,
            "Original name": a.original_name,
            "Internal ID": a.internal_id or a.pseudonym,
            "Category": a.category or "(unknown)",
            "Entity type": a.entity_type,
            "Flagged": (
                _FLAG_AMBIGUOUS if a.ambiguous else _FLAG_NOT_CURATED if a.auto else ""
            ),
            "Possible match": (
                f"{a.suggested_name} ({a.suggested_pseudonym}, "
                f"{a.suggested_score:.0%} match)"
                if a.suggested_pseudonym
                else ""
            ),
            "Master list": master_list_fingerprint,
        }
        for a in crosswalk
    ]
    return pd.DataFrame(rows, columns=_PDF_MAPPING_WITH_NAMES_COLUMNS)


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
#
# ``REDACT_COLUMN`` is public because ``exclusion_view`` needs the same name
# to configure the checkbox column and to mark every other column read-only.
# A second copy of the string over there would drift silently: its
# ``disabled`` filter would stop excluding the real column, the tick boxes
# would render read-only, and nothing would raise.
REDACT_COLUMN = "Hide in output?"
_TERM_COLUMN = "Detected text"

_EDITOR_COLUMNS = [
    REDACT_COLUMN,
    _TERM_COLUMN,
    "Entity type",
    "Source",
    "Confidence",
    "Hint",
    "Occurrences",
]

# Review order: the guesses most likely to be wrong first, curated names last.
_MODEL_WITH_HINT, _MODEL_PLAIN, _TYPED, _PATTERN, _CURATED = range(5)
_SOURCE_TIER = {
    DetectionSource.CUSTOM: _TYPED,
    DetectionSource.PATTERN: _PATTERN,
    DetectionSource.MASTER_LIST: _CURATED,
}

# Filter choices for the review table: label -> the Source values it shows.
ALL_SOURCES = "All"
SOURCE_FILTERS = {
    "Model guesses": DetectionSource.MODEL.value,
    "Typed words": DetectionSource.CUSTOM.value,
    "Pattern matches": DetectionSource.PATTERN.value,
    "Master list": DetectionSource.MASTER_LIST.value,
}


def detection_editor_dataframe(
    findings: Sequence[Finding], excluded: frozenset[str] = frozenset()
) -> pd.DataFrame:
    """Render detections as a tickable table for rejecting false positives.

    One row per distinct detected term, ordered by first appearance, with
    ``Hide in output?`` seeded from ``excluded`` so an unticked row stays unticked
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
    # Insertion-ordered, so ties read in order of first appearance. Counts and
    # scores are kept in their own dicts rather than mutated inside the row
    # dicts, which keeps every dict singly typed.
    first_seen: dict[str, Finding] = {}
    counts: Counter[str] = Counter()
    best_score: dict[str, float] = {}
    for finding in findings:
        key = normalize(finding.detected_text)
        first_seen.setdefault(key, finding)
        counts[key] += 1
        best_score[key] = max(best_score.get(key, 0.0), finding.score)

    def tier_and_hint(finding: Finding) -> tuple[int, str]:
        hint = review_hint(finding.detected_text, finding.entity_type, finding.source)
        # ``==``, not ``is``: Streamlit re-imports changed modules on a rerun,
        # so findings kept in session state can hold members of an older copy
        # of the enum. Those compare and hash equal but are not the same
        # object. An unknown source sorts with the guesses, the safe end.
        if finding.source == DetectionSource.MODEL:
            return (_MODEL_WITH_HINT if hint else _MODEL_PLAIN), hint
        return _SOURCE_TIER.get(finding.source, _MODEL_PLAIN), hint

    ranked = sorted(
        (
            (tier_and_hint(finding), best_score[key], position, key, finding)
            for position, (key, finding) in enumerate(first_seen.items())
        ),
        # Lowest confidence first among plain model guesses; otherwise by
        # first appearance.
        key=lambda r: (r[0][0], r[1] if r[0][0] == _MODEL_PLAIN else 0.0, r[2]),
    )
    rows = [
        {
            REDACT_COLUMN: key not in excluded,
            _TERM_COLUMN: finding.detected_text,
            "Entity type": finding.entity_type,
            "Source": finding.source.value,
            "Confidence": round(score, 2),
            "Hint": hint,
            "Occurrences": counts[key],
        }
        for (_, hint), score, _, key, finding in ranked
    ]
    return pd.DataFrame(rows, columns=_EDITOR_COLUMNS)


def term_key(term: object) -> str:
    """Return the normalized form a row is compared by (matches ``exclude``)."""
    return normalize(str(term))


def filter_editor_rows(table: pd.DataFrame, choice: str | None) -> pd.DataFrame:
    """Rows of the review table to show for a filter choice (display only).

    ``None`` or :data:`ALL_SOURCES` shows everything. Filtering never changes
    what is redacted: hidden rows keep their tick state.
    """
    source = SOURCE_FILTERS.get(choice or ALL_SOURCES)
    if source is None:
        return table
    return table[table["Source"] == source]


def search_editor_rows(table: pd.DataFrame, text: str | None) -> pd.DataFrame:
    """Rows whose term contains ``text`` (case-insensitive); all rows if blank.

    Display only, like :func:`filter_editor_rows`: hidden rows keep their state.
    """
    needle = (text or "").strip().casefold()
    if not needle:
        return table
    terms = table[_TERM_COLUMN].astype(str).str.casefold()
    return table[terms.str.contains(needle, regex=False)]


def model_guess_count(table: pd.DataFrame) -> int:
    """Return how many terms in the review table are model guesses."""
    return int((table["Source"] == DetectionSource.MODEL.value).sum())


def review_tab_labels(
    findings: Sequence[Finding], *, preview: bool = False
) -> list[str]:
    """Return the review step's tab labels, with the review tab first.

    The count comes from the findings, not from the tick boxes, so the label
    stays put while the reviewer works: Streamlit keys tabs by label, and a
    label that changed on every tick would throw the reviewer back to the
    first tab.
    """
    n = model_guess_count(detection_editor_dataframe(findings)) if findings else 0
    review = f"Review ({n} to check)" if n else "Review"
    return [review, *(["Preview"] if preview else []), "Mapping", "Occurrences"]


def review_status(
    table: pd.DataFrame, applied: frozenset[str], pending: frozenset[str]
) -> str:
    """One line: what is in the table, what is left visible, what is not applied.

    Builds on :func:`review_summary`, so the review tab has a single line
    rather than two that both count the model guesses.
    """
    parts = [review_summary(table).removesuffix(".")]
    if applied:
        parts.append(f"{plural(len(applied), 'term')} left visible")
    n_changes = len(pending ^ applied)
    if n_changes:
        parts.append(f"{plural(n_changes, 'change')} not applied yet")
    return " · ".join(parts) + "."


def apply_notice(left_visible: frozenset[str]) -> str:
    """Return the confirmation shown once after Apply rebuilds the file."""
    if not left_visible:
        return "Rebuilt the file. Every detected term is hidden."
    n = len(left_visible)
    verb = "is" if n == 1 else "are"
    return (
        f"Rebuilt the file. {plural(n, 'term')} {verb} left visible; "
        "they are listed above the download."
    )


def review_summary(table: pd.DataFrame) -> str:
    """One line saying what is in the table, so the reviewer knows the size of the job."""
    n = len(table)
    by_source = Counter(table["Source"])
    hinted = int((table["Hint"] != "").sum())
    parts = []
    model = by_source[DetectionSource.MODEL.value]
    if model:
        guess = plural(model, "model guess", "model guesses")
        parts.append(f"{guess} ({hinted} worth a closer look)" if hinted else guess)
    for label, source in (
        ("typed word", DetectionSource.CUSTOM.value),
        ("pattern match", DetectionSource.PATTERN.value),
        ("master-list name", DetectionSource.MASTER_LIST.value),
    ):
        count = by_source[source]
        if count:
            parts.append(
                plural(count, label, label + "es" if label.endswith("h") else None)
            )
    return f"{plural(n, 'term')}: " + ", ".join(parts) + "."


def merge_pending(
    pending: frozenset[str], shown: pd.DataFrame, edited: pd.DataFrame
) -> frozenset[str]:
    """Combine the unticked terms of the visible rows with those of hidden ones.

    A filter hides rows without touching them, so a hidden row that was
    unticked stays unticked and a hidden row that was ticked stays ticked.
    """
    shown_keys = frozenset(term_key(t) for t in shown[_TERM_COLUMN])
    return (pending - shown_keys) | excluded_terms(edited)


def excluded_terms(edited: pd.DataFrame) -> frozenset[str]:
    """Read back the normalized terms the operator unticked in the editor.

    The inverse of :func:`detection_editor_dataframe`. Returns normalized
    terms, ready to hand to a redaction service's ``exclude`` argument.

    A missing or empty frame yields an empty set, which means "redact
    everything" - the safe direction if the widget state is ever lost.
    """
    if edited is None or edited.empty or REDACT_COLUMN not in edited.columns:
        return frozenset()
    unticked = edited.loc[~edited[REDACT_COLUMN].fillna(True).astype(bool)]
    return frozenset(normalize(str(term)) for term in unticked[_TERM_COLUMN])


def formatting_note(formats: Mapping[str, SheetFormatting], n_tabs: int) -> str:
    """Say what the redacted workbook does not carry over from the source.

    Empty ``formats`` for a workbook that has tabs means the formatting could
    not be read at all, so every sheet comes out plain.
    """
    if n_tabs and not formats:
        return (
            "The formatting of this workbook could not be read, so the "
            "download is plain: values only, no fonts, colours or widths."
        )
    totals: Counter[str] = Counter()
    for sheet in formats.values():
        totals.update(sheet.dropped)
    if not totals:
        return ""
    parts = [
        f"{kind}: {count:,}"
        + (" (their values are kept)" if kind == "formulas" else "")
        for kind, count in totals.items()
    ]
    return "Not carried over from the original: " + ", ".join(parts) + "."
