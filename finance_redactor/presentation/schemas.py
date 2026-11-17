"""Request and response models for the web API."""

from __future__ import annotations

from pydantic import BaseModel


class QualityIssueOut(BaseModel):
    """One master-list data-quality finding."""

    severity: str
    title: str
    detail: str
    examples: list[str]
    total: int


class MasterListOut(BaseModel):
    """Master-list status for the top bar."""

    total: int
    counts: dict[str, int]
    issues: list[QualityIssueOut]
    path: str
    age_seconds: float | None
    # True when no names loaded and the user has not chosen "Skip for now".
    needs_setup: bool


class FolderIn(BaseModel):
    """A folder path typed by the user."""

    folder: str


class FolderCheckOut(BaseModel):
    """Whether a folder holds the master-list workbook."""

    found: bool


class SetupIn(BaseModel):
    """The master-list folder to save."""

    folder: str
    # The folder may still be syncing from Box; saving a path without the
    # workbook needs an explicit yes.
    save_anyway: bool = False


class JobOut(BaseModel):
    """A stored upload."""

    id: str
    filename: str
    format: str
    size: int


class TaskOut(BaseModel):
    """The job's background task: ``idle``, ``running``, ``done`` or ``error``."""

    status: str
    label: str
    done: int
    total: int
    error: str


class JobStatusOut(JobOut):
    """A stored upload and its background task."""

    task: TaskOut


# --- shared review vocabulary (all formats) ---------------------------------


class ReviewRowOut(BaseModel):
    """One distinct detected term in the review list.

    ``key`` is the normalized form the redaction services compare against,
    and what the client sends back to leave a term visible.
    """

    key: str
    term: str
    why: str
    kind: str
    source: str
    confidence: float
    hint: str
    occurrences: int


class SourceFilterOut(BaseModel):
    """A review filter chip: a label and how many terms it shows."""

    label: str
    source: str
    count: int


class MappingRowOut(BaseModel):
    """One row of the on-screen name -> code mapping (Confidential)."""

    original_name: str
    kind: str
    pseudonym: str
    flagged: bool
    possible_match: str


class TextOccurrenceOut(BaseModel):
    """One place a term was found in a Word paragraph or PDF page (1-based).

    ``key`` matches the review row's ``key``, so the interface can jump from
    a term to where it is.
    """

    location: int
    key: str
    term: str
    kind: str


class ExcludeIn(BaseModel):
    """Terms (review ``key`` values) to leave visible in this document."""

    excluded: list[str]


# --- Excel ------------------------------------------------------------------


class ExcelTabOut(BaseModel):
    """One tab: its columns by position, and the text columns picked for it."""

    name: str
    columns: list[str]
    default_columns: list[int]


class ThresholdOut(BaseModel):
    """The confidence slider's range, default and help text."""

    default: float
    min: float
    max: float
    step: float
    help: str


class EntityOut(BaseModel):
    """A kind of information the user can choose to hide."""

    code: str
    label: str


class ExcelOptionsOut(BaseModel):
    """Everything the Options step needs to draw itself."""

    tabs: list[ExcelTabOut]
    summary: str
    threshold: ThresholdOut
    entities: list[EntityOut]
    entity_help: str


class ExcelSelectionIn(BaseModel):
    """Tabs to scan and, per tab, column positions to scan."""

    tabs: list[str]
    columns: dict[str, list[int]]


class ExcelScanIn(ExcelSelectionIn):
    """A scan request: the selection plus detection settings."""

    entities: list[str]
    threshold: float


class EstimateOut(BaseModel):
    """A warning before a slow or memory-hungry scan, or None."""

    warning: str | None


class OccurrenceOut(BaseModel):
    """One place a term was found: a cell, a tab name or a header.

    ``row`` is 1-based (None for a tab name or header). ``key`` matches the
    review row's ``key``. ``place`` is ``cell``, ``header`` or ``tab``;
    ``column_name`` is the original column header ("" for a tab name), for
    finding the column in the preview.
    """

    sheet: str
    row: int | None
    column: str
    place: str
    column_name: str
    key: str
    term: str


class ExcelReviewOut(BaseModel):
    """The Review step: terms, what is applied, the mapping, every occurrence."""

    summary: str
    entity_count: int
    cell_count: int
    rows: list[ReviewRowOut]
    applied: list[str]
    carried: list[str]
    filters: list[SourceFilterOut]
    clean: bool
    mapping: list[MappingRowOut]
    occurrences: list[OccurrenceOut]
    tabs: list[str]


class ExcelPreviewOut(BaseModel):
    """A block of rows of one tab, redacted and original, with changed cells.

    ``marked`` holds ``[row, column]`` positions within this block; row ``-1``
    is the header.
    """

    tab: int
    tabs: list[str]
    total_rows: int
    start: int
    page_size: int
    columns: list[str]
    original_columns: list[str]
    rows: list[list[str]]
    original_rows: list[list[str]]
    marked: list[tuple[int, int]]
    elsewhere: int


class ExcelDownloadOut(BaseModel):
    """What the Download step must say before offering the files."""

    excluded: list[str]
    left_out: list[str]
    nothing_found: bool
    formatting_note: str
    has_mapping: bool


# --- Word -------------------------------------------------------------------


class DetectionOptionsOut(BaseModel):
    """Options for a text document: the confidence slider and kinds to hide."""

    threshold: ThresholdOut
    entities: list[EntityOut]
    entity_help: str


class DocxScanIn(BaseModel):
    """A Word scan: detection settings plus words typed for an earlier file."""

    entities: list[str]
    threshold: float
    words: list[str] = []


class WordsApplyIn(ExcludeIn):
    """Review choices: terms to leave visible and words to add."""

    words: list[str]


class DocxReviewOut(BaseModel):
    """The Word Review step."""

    summary: str
    rows: list[ReviewRowOut]
    applied: list[str]
    carried: list[str]
    words: list[str]
    filters: list[SourceFilterOut]
    clean: bool
    mapping: list[MappingRowOut]
    occurrences: list[TextOccurrenceOut]


class DocxDownloadOut(BaseModel):
    """What the Word Download step must say before offering the files."""

    excluded: list[str]
    removed_links: int
    has_mapping: bool


# --- PDF --------------------------------------------------------------------


class PdfOptionsOut(BaseModel):
    """The PDF Options step: OCR availability and how big the job is.

    The size note depends on whether scans will be read, so both versions
    are sent and the client shows the one matching its OCR switch.
    """

    can_read_scans: bool
    total_pages: int
    size_note_reading: str
    size_note_not_reading: str


class PdfScanIn(BaseModel):
    """A PDF scan: style, images, OCR, and words typed for an earlier file."""

    style: str = "pseudonymize"
    redact_images: bool = True
    read_scans: bool = True
    words: list[str] = []


class PdfApplyIn(WordsApplyIn):
    """Review choices: terms to leave visible, words to add, table columns."""

    columns: list[str]


class TableColumnOut(BaseModel):
    """A table column found in the PDF: its key and header as first seen."""

    key: str
    header: str


class PdfMappingRowOut(BaseModel):
    """One row of the on-screen label mapping. Names shown, never saved."""

    label: str
    original_name: str
    kind: str
    internal_id: str
    flagged: str
    possible_match: str


class PdfReviewOut(BaseModel):
    """The PDF Review step.

    ``scanned_note`` and ``not_located`` are short Markdown (bold and code).
    """

    summary: str
    page_count: int
    blackout: bool
    scanned_note: str
    not_located: str
    rows: list[ReviewRowOut]
    applied: list[str]
    carried: list[str]
    words: list[str]
    table_columns: list[TableColumnOut]
    columns: list[str]
    filters: list[SourceFilterOut]
    clean: bool
    mapping: list[PdfMappingRowOut]
    occurrences: list[TextOccurrenceOut]


class PdfDownloadOut(BaseModel):
    """What the PDF Download step must say before offering the files.

    ``before_share`` notes are short Markdown; ``before_share_warn`` says
    whether any of them means something may still show.
    """

    excluded: list[str]
    blackout: bool
    removed_links: int
    before_share: list[str]
    before_share_warn: bool
    not_located: str
    has_mapping: bool
    bracketed: int
    names_file: bool


class NamesFileIn(BaseModel):
    """Switch the opt-in Confidential names file on or off."""

    enabled: bool
