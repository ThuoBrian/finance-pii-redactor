"""View formatters: turn domain results into what the interface shows.

The wording, labels, ordering and tables the API returns all come from here,
so the screen and the downloaded files speak one vocabulary.
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import pandas as pd

from finance_redactor.application.ports import SheetFormatting
from finance_redactor.application.results import WorkbookScanResult
from finance_redactor.domain.entities import DetectionSource, Finding
from finance_redactor.domain.pseudonyms import Assignment, normalize
from finance_redactor.domain.review_hints import (
    ALL_CAPS,
    ONE_WORD_ORGANIZATION,
    ORDINARY_WORD,
    review_hint,
)

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


PREVIEW_MAX_ROWS = 500


THRESHOLD_HELP = (
    "How sure the tool must be before it hides something. Lower catches more "
    "(fewer missed names, but more words that were not names); higher catches "
    "less. Lowering it is the safe direction. If unsure, keep the default. "
    "It stops at 0.85, the highest setting that still hides bank and payment "
    "details."
)
ENTITY_HELP = (
    "The kinds of sensitive information to look for: people, organizations, "
    "email addresses, websites, and bank or payment details (shown as a fixed "
    "mask like [ACCOUNT] rather than a pseudonym). Remove a kind only if you "
    "are sure the file has none of it."
)


# Codes whose plain capitalized form reads wrongly ("Url", "Iban code").
_ENTITY_LABELS = {
    "URL": "Website",
    "IBAN_CODE": "IBAN",
    "SWIFT_CODE": "SWIFT code",
    "KE_BANK_ACCOUNT": "Kenyan bank account",
    "MPESA_NUMBER": "M-Pesa number",
    "CUSTOM": "Added term",
    "DATE_TIME": "Date or time",
}
# First words that keep their capitals mid-sentence.
_PROPER_WORDS = ("IBAN", "SWIFT", "Kenyan", "M-Pesa")


def entity_label(entity_type: str) -> str:
    """Readable form of an entity code, e.g. ``EMAIL_ADDRESS`` -> ``Email address``."""
    return _ENTITY_LABELS.get(entity_type, entity_type.replace("_", " ").capitalize())


# How each detection source reads on screen.
_SOURCE_LABELS = {
    DetectionSource.MODEL.value: "Model guess",
    DetectionSource.MASTER_LIST.value: "Master list",
    DetectionSource.CUSTOM.value: "Typed word",
    DetectionSource.PATTERN.value: "Pattern match",
    DetectionSource.TABLE_COLUMN.value: "Table column",
}


def source_label(source: DetectionSource) -> str:
    """Readable form of a detection source, e.g. ``custom word`` -> ``Typed word``."""
    value = str(source.value)
    return _SOURCE_LABELS.get(value, value.capitalize())


def plural(count: int, singular: str, plural_form: str | None = None) -> str:
    """Return ``"1 name"`` / ``"2 names"``: a count with the right noun form."""
    word = singular if count == 1 else (plural_form or f"{singular}s")
    return f"{count:,} {word}"


# Shown in the Column field of a finding that sits in a tab's name, not a cell.
TAB_NAME_LABEL = "(tab name)"
# Follows the header text in the Column field of a finding in a column header.
HEADER_LABEL = "(header)"


def excel_findings_dataframe(scan_result: WorkbookScanResult) -> pd.DataFrame:
    """Flatten a workbook scan result into a per-detection findings table."""
    rows: list[dict[str, object]] = [
        {
            "Sheet": sheet,
            "Row": cell.row + 1,
            "Column": cell.column,
            "Detected text": detection.text,
            "Entity type": entity_label(detection.entity_type),
            "Confidence": round(detection.score, 2),
            "Source": source_label(detection.source),
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
            "Entity type": entity_label(detection.entity_type),
            "Confidence": round(detection.score, 2),
            "Source": source_label(detection.source),
        }
        for sheet, detections in scan_result.tab_names.items()
        for detection in detections
    ]
    rows += [
        {
            "Sheet": sheet,
            "Row": None,
            "Column": f"{header} {HEADER_LABEL}",
            "Detected text": detection.text,
            "Entity type": entity_label(detection.entity_type),
            "Confidence": round(detection.score, 2),
            "Source": source_label(detection.source),
        }
        for sheet, by_header in scan_result.headers.items()
        for header, detections in by_header.items()
        for detection in detections
    ]
    return pd.DataFrame(rows, columns=_EXCEL_COLUMNS)


def scan_result_findings(scan_result: WorkbookScanResult) -> list[Finding]:
    """Flatten a workbook scan result into :class:`Finding` objects.

    Only so Excel can share :func:`review_terms` with the PDF
    and Word flows, which already work in ``Finding``. ``page`` carries the
    row index here, the same way it carries a paragraph ordinal in the Word
    flow - and ``-1`` for a tab name or a
    column header.
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
    ] + [
        (-1, detection)
        for by_header in scan_result.headers.values()
        for detections in by_header.values()
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
            "Entity type": entity_label(a.entity_type),
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
    ``CST-AUTO-3F9A1C07``) - a hash of the name, not the name, so the file stays
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


# The review list. One row per distinct detected term, because a word
# appearing forty times is one decision, not forty.


@dataclass(frozen=True)
class ReviewTerm:
    """One distinct detected term in the review list.

    ``key`` is the normalized form the redaction services compare against
    (see :func:`term_key`). ``source`` and ``kind`` are readable labels.
    """

    key: str
    term: str
    why: str
    kind: str
    source: str
    confidence: float
    hint: str
    occurrences: int


# A model hint, in words someone who has never heard of spaCy can act on.
_PLAIN_HINT = {
    ORDINARY_WORD: "it is an ordinary English word",
    ALL_CAPS: "it is in capitals, often a heading or an acronym",
    ONE_WORD_ORGANIZATION: "one-word organizations are often labels",
}

# Review order: the guesses most likely to be wrong first, curated names last.
_MODEL_WITH_HINT, _MODEL_PLAIN, _TYPED, _PATTERN, _CURATED = range(5)
_SOURCE_TIER = {
    DetectionSource.CUSTOM: _TYPED,
    DetectionSource.TABLE_COLUMN: _TYPED,
    DetectionSource.PATTERN: _PATTERN,
    DetectionSource.MASTER_LIST: _CURATED,
}

# Filter choices for the review table: label -> the Source values it shows.
SOURCE_FILTERS = {
    "Model guesses": source_label(DetectionSource.MODEL),
    "Typed words": source_label(DetectionSource.CUSTOM),
    "Table columns": source_label(DetectionSource.TABLE_COLUMN),
    "Pattern matches": source_label(DetectionSource.PATTERN),
    "Master list": source_label(DetectionSource.MASTER_LIST),
}


def why_found(finding: Finding, hint: str = "") -> str:
    """Say in plain words why a term was found, and whether to look twice.

    The review table's main column. ``Source``, ``Kind``, ``Confidence`` and
    ``Hint`` say the same things in the tool's own terms, behind "Show
    details".
    """
    source = finding.source
    if source == DetectionSource.MASTER_LIST:
        return "On your master list"
    if source == DetectionSource.CUSTOM:
        return "You typed it"
    if source == DetectionSource.TABLE_COLUMN:
        return "In a table column you chose"
    kind = entity_label(finding.entity_type)
    if not kind.startswith(_PROPER_WORDS):
        kind = kind.lower()
    if source == DetectionSource.PATTERN:
        return f"Shaped like {_with_article(kind)}"
    # A model guess, or a source this build does not know: treat as a guess.
    guess = "a name" if finding.entity_type == "PERSON" else _with_article(kind)
    if hint:
        return f"Looks like {guess}. Check it: {_PLAIN_HINT.get(hint, hint)}"
    return f"Looks like {guess}"


def _with_article(noun: str) -> str:
    # "an M-Pesa number": the letter M is said "em", so it takes "an".
    vowel = noun[:1].lower() in "aeiou" or noun.startswith("M-")
    return f"{'an' if vowel else 'a'} {noun}"


def review_terms(findings: Sequence[Finding]) -> list[ReviewTerm]:
    """Group detections into one row per distinct term, likeliest mistakes first.

    ``source`` is here on purpose: it is what tells the reviewer which fix
    applies. ``Master list`` means a row in the workbook matches this word, so
    unticking is a per-document patch and editing the workbook is the real fix.
    ``Model guess`` means spaCy guessed, and the confidence threshold is a
    lever. ``Typed word`` means it came from the words box, so clearing that
    box fixes it.

    Grouping is keyed on :func:`normalize`, matching how ``exclude`` is
    compared in the redaction services, so a term ticked off matches every
    casing and spacing of itself in the document.
    """
    # Insertion-ordered, so ties read in order of first appearance.
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
        # An unknown source sorts with the guesses, the safe end.
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
    return [
        ReviewTerm(
            key=key,
            term=finding.detected_text,
            why=why_found(finding, hint),
            kind=entity_label(finding.entity_type),
            source=source_label(finding.source),
            confidence=round(score, 2),
            hint=hint,
            occurrences=counts[key],
        )
        for (_, hint), score, _, key, finding in ranked
    ]


def merge_findings(
    existing: Sequence[Finding], new: Sequence[Finding]
) -> list[Finding]:
    """Return ``existing`` plus each finding of ``new`` whose term is not in it yet."""
    seen = {term_key(f.detected_text) for f in existing}
    merged = list(existing)
    for finding in new:
        key = term_key(finding.detected_text)
        if key not in seen:
            seen.add(key)
            merged.append(finding)
    return merged


def carry_over_exclusions(
    previous: frozenset[str], findings: Sequence[Finding]
) -> frozenset[str]:
    """Return the terms unticked last run that the new run found again.

    Going back to Options and redacting again must not throw away the review
    already done. A term the new scan no longer finds has nothing to leave
    visible, so it is dropped rather than kept as a silent exception.
    """
    return previous & {term_key(f.detected_text) for f in findings}


def term_key(term: object) -> str:
    """Return the normalized form a row is compared by (matches ``exclude``)."""
    return normalize(str(term))


def model_guess_count(terms: Sequence[ReviewTerm]) -> int:
    """Return how many review terms are model guesses."""
    model = source_label(DetectionSource.MODEL)
    return sum(1 for t in terms if t.source == model)


def pdf_job_size_note(
    scanned: int,
    total_pages: int,
    *,
    reading_scans: bool,
    seconds_per_page: float,
    large_pages: int,
) -> str:
    """Say up front how long a big PDF will take; empty for a quick one.

    The OCR estimate shows once reading the scans would take a minute or
    more; the page-count warning once the file has ``large_pages`` pages.
    """
    parts = []
    seconds = scanned * seconds_per_page if reading_scans else 0
    if seconds >= 60:
        minutes = math.ceil(seconds / 60)
        parts.append(
            f"**{plural(scanned, 'scanned page')}, about "
            f"{plural(minutes, 'minute')} to read.** Scanned pages are read "
            "one at a time; leave this tab open until the review appears."
        )
    if total_pages >= large_pages:
        parts.append(
            f"**This PDF has {plural(total_pages, 'page')}.** A file this long "
            "can take a long time and a lot of memory, and a run cannot be "
            "stopped halfway. Consider splitting it into smaller files."
        )
    return "\n\n".join(parts)


def not_located_warning(not_located: Sequence[Finding]) -> str:
    """Warn about detected terms the PDF search could not find on the page.

    Nothing covers these: the text was read from the page, but no search
    variant matched the page's own text (ligatures, unusual encoding). The
    terms are listed for the operator's own screen, never logged.
    """
    if not not_located:
        return ""
    pages = sorted({f.page for f in not_located})
    terms = ", ".join(sorted({f"`{f.detected_text}`" for f in not_located}))
    n = len(not_located)
    return (
        f"**{plural(n, 'detected term')} could not be found on the page, so "
        f"{'it is' if n == 1 else 'they are'} not covered** ({_page_list(pages)}): "
        f"{terms}. The text was read from the PDF, but its letters are stored "
        "in a way the search could not match. Check those pages in the "
        "download before sharing it; anything still showing has to be "
        "covered by hand."
    )


def review_summary(terms: Sequence[ReviewTerm]) -> str:
    """One line saying what is in the list, so the reviewer knows the size of the job."""
    n = len(terms)
    by_source = Counter(t.source for t in terms)
    hinted = sum(1 for t in terms if t.hint)
    parts = []
    model = by_source[source_label(DetectionSource.MODEL)]
    if model:
        guess = plural(model, "model guess", "model guesses")
        parts.append(f"{guess} ({hinted} worth a closer look)" if hinted else guess)
    for label, source in (
        ("typed word", DetectionSource.CUSTOM),
        ("table cell", DetectionSource.TABLE_COLUMN),
        ("pattern match", DetectionSource.PATTERN),
        ("master-list name", DetectionSource.MASTER_LIST),
    ):
        count = by_source[source_label(source)]
        if count:
            parts.append(
                plural(count, label, label + "es" if label.endswith("h") else None)
            )
    return f"{plural(n, 'term')}: " + ", ".join(parts) + "."


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


def _page_list(pages: Sequence[int]) -> str:
    """Return 1-based page numbers, e.g. ``"page 1, 3"`` (first ten only)."""
    shown = ", ".join(str(i + 1) for i in pages[:10]) + (
        ", ..." if len(pages) > 10 else ""
    )
    return f"page {shown}"


def pdf_mapping_notes(crosswalk: Sequence[Assignment]) -> list[str]:
    """Return notes on mapping rows with no Internal ID, for "Before you share".

    The items were redacted like any other, so nothing shows. But the PDF
    mapping has no names, so such a row can never be decoded later; that is
    worth knowing before the file goes anywhere.
    """
    unresolved = [a for a in crosswalk if a.internal_id is None]
    ambiguous = sum(1 for a in unresolved if a.ambiguous)
    missing = len(unresolved) - ambiguous
    notes = []
    if missing:
        notes.append(
            f"**{plural(missing, 'redacted item')} not on the master list.** "
            "They are hidden, but the mapping can't say who they are later. "
            "Add them to the master list and redact again if that matters."
        )
    if ambiguous:
        notes.append(
            f"**{plural(ambiguous, 'redacted item')} matched more than one "
            "master-list row** with different IDs, so no ID was recorded. Fix "
            "the duplicates (the master-list card in the sidebar lists them) "
            "and redact again."
        )
    return notes


def scanned_pages_warning(
    scanned: Sequence[int],
    total_pages: int,
    images_blacked_out: bool,
    *,
    read: Sequence[int] = (),
) -> str:
    """Explain what happened to scanned pages, read with OCR or not.

    A scan is a picture of text with no text layer, or a page that is mostly
    such a picture under some typed text. A page OCR read had its names
    redacted and, with image black-out on, everything it could not read with
    confidence blacked out; it still deserves a look, because OCR can
    misread. A page left unread has its scanned image blacked out with image
    black-out on (for a plain scan, the whole page), and unredacted with it
    off.
    """
    parts = []
    read_set = set(read)
    done = [i for i in scanned if i in read_set]
    unread = [i for i in scanned if i not in read_set]
    if done:
        n = len(done)
        rest = (
            ", and anything OCR could not read with confidence (signatures, "
            "handwriting, stamps) is blacked out"
            if images_blacked_out
            else "; signatures, handwriting and stamps are left as they are, "
            "because black out images is off"
        )
        parts.append(
            f"**{n} of {plural(total_pages, 'page')} "
            f"{'is a scan' if n == 1 else 'are scans'}, read with OCR** "
            f"({_page_list(done)}). Names found in "
            f"{'it' if n == 1 else 'them'} were redacted{rest}. OCR can misread, "
            f"so check {'that page' if n == 1 else 'those pages'} in the download."
        )
    if unread:
        n = len(unread)
        outcome = (
            "Black out images is on, so the scanned image on "
            f"{'that page' if n == 1 else 'those pages'} is blacked out in the "
            "download."
            if images_blacked_out
            else "Black out images is off, so "
            f"{'that page goes' if n == 1 else 'those pages go'} into the download "
            "unredacted. Turn it on under Customize, or check them by hand."
        )
        parts.append(
            f"**{n} of {plural(total_pages, 'page')} "
            f"{'is a scan' if n == 1 else 'are scans'}** ({_page_list(unread)}): a "
            "picture of text that was not read, so names inside "
            f"{'it' if n == 1 else 'them'} are not detected. {outcome}"
        )
    return "\n\n".join(parts)


# Scan-size warning (see scan_size_warning). About a minute of scanning, or a
# workbook big enough that holding it twice in memory starts to drag.
_SLOW_SCAN_VALUES = 3_000
_BIG_WORKBOOK_CELLS = 500_000
_FAST_VALUES_PER_SECOND = 60
_SLOW_VALUES_PER_SECOND = 30


def scan_size_warning(
    sheets: dict[str, pd.DataFrame], columns_by_sheet: dict[str, list[str]]
) -> str | None:
    """Warn before a scan that will take minutes or a lot of memory, else None.

    The scan analyzes each distinct value once, so its time follows the
    distinct values in the chosen columns, not the row count. The rate range
    is rough: the real engine checked about 48 values a second on a
    development laptop, and the master list and longer cells slow it down.
    lean-dev: a warning only, no chunking or abort.
    """
    n_cells = sum(df.size for df in sheets.values())
    distinct = len(
        {
            value
            for name, df in sheets.items()
            for col in columns_by_sheet.get(name, [])
            if col in df.columns
            for value in df[col].dropna().unique()
        }
    )
    slow = distinct >= _SLOW_SCAN_VALUES
    big = n_cells >= _BIG_WORKBOOK_CELLS
    if not (slow or big):
        return None
    parts = [
        f"This is a large job: {n_cells:,} cells, with {distinct:,} distinct "
        "values in the chosen columns."
    ]
    if slow:
        low = max(1, round(distinct / _FAST_VALUES_PER_SECOND / 60))
        high = max(low + 1, round(distinct / _SLOW_VALUES_PER_SECOND / 60))
        parts.append(f"Expect the scan to take roughly {low:,} to {high:,} minutes.")
    if big:
        parts.append(
            "The whole workbook is held in memory while you work, so the "
            "app may be slow to respond."
        )
    parts.append(
        "Keep this page open while it runs. To make it quicker, choose fewer "
        "tabs or columns under Customize."
    )
    return " ".join(parts)


def name_summary(names: list[str], shown: int = 2) -> str:
    """``"Jan, Feb + 8 more"``: the first few names, then a count of the rest."""
    head = ", ".join(names[:shown])
    rest = len(names) - shown
    return f"{head} + {rest:,} more" if rest > 0 else head
