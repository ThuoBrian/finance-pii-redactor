"""Tests for presentation-layer view formatters."""

from __future__ import annotations

import pandas as pd
import pytest

from finance_redactor.application.results import (
    CellFinding,
    ExcelScanResult,
    WorkbookScanResult,
)
from finance_redactor.domain.entities import (
    DetectionSource,
    Finding,
    PiiDetection,
    Span,
)
from finance_redactor.domain.pseudonyms import Assignment
from finance_redactor.presentation.presenters import (
    carry_over_exclusions,
    crosswalk_dataframe,
    entity_label,
    excel_findings_dataframe,
    formatting_note,
    merge_findings,
    name_summary,
    not_located_warning,
    pdf_job_size_note,
    pdf_mapping_dataframe,
    pdf_mapping_notes,
    pdf_mapping_with_names_dataframe,
    pdf_review_dataframe,
    plural,
    review_summary,
    review_terms,
    scan_result_findings,
    scan_size_warning,
    scanned_pages_warning,
    why_found,
)


@pytest.mark.parametrize(
    ("count", "expected"),
    [(0, "0 matches"), (1, "1 match"), (2, "2 matches"), (1234, "1,234 matches")],
)
def test_plural_picks_the_right_noun_form(count: int, expected: str) -> None:
    assert plural(count, "match", "matches") == expected


def test_plural_defaults_to_adding_s() -> None:
    assert plural(1, "page") == "1 page"
    assert plural(3, "page") == "3 pages"


def test_occurrences_are_one_based_with_a_readable_kind() -> None:
    """Word paragraphs and PDF pages reuse Finding.page, shown 1-based."""
    from finance_redactor.presentation.api.review import text_occurrences

    findings = [
        Finding(
            page=2,
            detected_text="John Doe",
            entity_type="EMAIL_ADDRESS",
            score=0.87,
            source=DetectionSource.MODEL,
        )
    ]

    (occurrence,) = text_occurrences(findings)

    assert occurrence.location == 3
    assert occurrence.key == "john doe"
    assert occurrence.kind == "Email address"


# --- PDF mapping / review frames ---------------------------------------------
#
# The PDF flow has two frames on purpose: one shown on screen (with names) and
# one downloaded (without). The tests below are what keeps them apart.

# A deliberately unmistakable synthetic name. A plausible one like "Jane Doe"
# would make "assert no name appears" a weak assertion, since fragments of it
# turn up in ordinary words.
_DISTINCTIVE = "Zzyzx Qwertyson"


def _assignment(**overrides) -> Assignment:
    defaults = {
        "original_name": _DISTINCTIVE,
        "entity_type": "CUSTOM",
        "category": "Vendor",
        "pseudonym": "VND-17728",
        "auto": False,
        "ordinal": 1,
        "internal_id": "17728",
    }
    return Assignment(**{**defaults, **overrides})


def test_pdf_mapping_never_contains_a_name() -> None:
    """The downloaded PDF mapping must carry no names at all.

    This is the entire reason the two-hop scheme exists: the mapping is
    Internal rather than Confidential *because* it cannot identify anyone on
    its own. If this test fails, the file has silently changed
    classification and must not be shipped alongside a redacted PDF.
    """
    df = pdf_mapping_dataframe([_assignment()])

    assert "Original name" not in df.columns
    rendered = df.to_csv(index=False)
    assert _DISTINCTIVE not in rendered
    assert "Zzyzx" not in rendered
    assert "Qwertyson" not in rendered
    # The Internal ID is what the file is for, so it must be there.
    assert "17728" in rendered


def test_pdf_mapping_carries_label_and_internal_id() -> None:
    df = pdf_mapping_dataframe([_assignment(ordinal=7)])

    assert df.loc[0, "Label"] == "[007]"
    assert df.loc[0, "Internal ID"] == "17728"
    assert df.loc[0, "Flagged"] == ""


def test_unresolved_row_gets_the_auto_token_not_a_blank() -> None:
    """An orphan must be visibly unresolved, not an empty cell.

    A blank is indistinguishable from a parse failure. The deterministic auto
    token says "the tool looked and found nothing", and being content-addressed
    it still links the same unresolved entity across documents.
    """
    df = pdf_mapping_dataframe(
        [
            _assignment(
                pseudonym="CST-AUTO-3F9A1C07", auto=True, internal_id=None, category=""
            )
        ]
    )

    assert df.loc[0, "Internal ID"] == "CST-AUTO-3F9A1C07"
    assert df.loc[0, "Flagged"] == "not in master list"
    assert _DISTINCTIVE not in df.to_csv(index=False)


def test_ambiguous_row_is_flagged_distinctly_from_a_plain_orphan() -> None:
    """An ID that was refused differs from one that was never there."""
    df = pdf_mapping_dataframe(
        [
            _assignment(
                pseudonym="CST-AUTO-3F9A1C07",
                auto=True,
                internal_id=None,
                ambiguous=True,
                category="",
            )
        ]
    )

    assert "ambiguous" in df.loc[0, "Flagged"]


def test_pdf_mapping_stamps_the_master_list_fingerprint() -> None:
    """Records which master list the mapping decodes against."""
    df = pdf_mapping_dataframe(
        [_assignment(), _assignment(ordinal=2)], "list.xlsx@2026-09-22T08:00:00Z/26431"
    )

    assert list(df["Master list"]) == ["list.xlsx@2026-09-22T08:00:00Z/26431"] * 2


def test_pdf_review_frame_does_show_the_name() -> None:
    """The on-screen table shows names, so the split above is deliberate."""
    df = pdf_review_dataframe([_assignment()])

    assert df.loc[0, "Original name"] == _DISTINCTIVE
    assert df.loc[0, "Label"] == "[001]"


def test_excel_and_word_crosswalk_still_carries_names() -> None:
    """The names-free mapping is PDF-only; Excel and Word are unchanged.

    Locks the agreed scope. Excel embeds its crosswalk in the workbook and
    Word downloads it as a CSV, and both still identify people - which is why
    they stay Confidential while the PDF mapping does not.
    """
    df = crosswalk_dataframe([_assignment()])

    assert "Original name" in df.columns
    assert df.loc[0, "Original name"] == _DISTINCTIVE
    assert df.loc[0, "Pseudonym"] == "VND-17728"


# --- The deselect editor -----------------------------------------------------
#
# Added after the ordinary word "salaries" came back redacted from a PDF and
# there was no way in the tool to say "not that one".


def _finding(
    text: str, page: int = 0, source: DetectionSource | None = None
) -> Finding:
    return Finding(
        page=page,
        detected_text=text,
        entity_type="ORGANIZATION",
        score=0.9,
        source=source or DetectionSource.MASTER_LIST,
    )


def test_editor_collapses_repeats_of_the_same_term_to_one_row() -> None:
    """A word appearing forty times is one decision, not forty tick boxes."""
    findings = [_finding("Salaries"), _finding("Salaries", 1), _finding("Salaries", 2)]

    terms = review_terms(findings)

    assert len(terms) == 1
    assert terms[0].occurrences == 3
    assert terms[0].term == "Salaries"
    assert terms[0].key == "salaries"


def test_editor_groups_across_casing_and_spacing() -> None:
    """Grouping uses the same normalization the services compare with.

    Otherwise unticking "Salaries" would leave "SALARIES" still redacted.
    """
    findings = [_finding("Salaries"), _finding("salaries"), _finding("  SALARIES  ")]

    terms = review_terms(findings)

    assert len(terms) == 1
    assert terms[0].occurrences == 3


def test_editor_reports_the_source_so_the_user_knows_which_fix_applies() -> None:
    """Master list -> edit the workbook; model -> raise the threshold."""
    findings = [
        _finding("Salaries"),
        _finding("someone@example.org", source=DetectionSource.PATTERN),
    ]

    terms = review_terms(findings)

    assert {t.source for t in terms} == {"Master list", "Pattern match"}


def _detection(text: str = "Jane Doe") -> PiiDetection:
    return PiiDetection(
        entity_type="PERSON",
        span=Span(0, len(text)),
        score=0.9,
        text=text,
        source=DetectionSource.MASTER_LIST,
    )


def _workbook_scan() -> WorkbookScanResult:
    return WorkbookScanResult(
        sheets={
            "Jan": ExcelScanResult(
                findings=[CellFinding(row=4, column="notes", detections=[_detection()])]
            ),
            "Feb": ExcelScanResult(findings=[]),
        },
        tab_names={"Feb": [_detection("Acme Ltd")]},
        headers={"Jan": {"Pat Example": [_detection("Pat Example")]}},
    )


def test_scan_result_findings_flattens_excel_cells_tab_names_and_headers() -> None:
    """Excel shares the editor, so every Excel finding becomes a Finding."""
    flattened = scan_result_findings(_workbook_scan())

    assert [f.detected_text for f in flattened] == [
        "Jane Doe",
        "Acme Ltd",
        "Pat Example",
    ]
    assert [f.page for f in flattened] == [4, -1, -1]


def test_excel_findings_dataframe_names_the_sheet_for_every_finding() -> None:
    table = excel_findings_dataframe(_workbook_scan())

    assert list(table["Sheet"]) == ["Jan", "Feb", "Jan"]
    assert table.loc[0, "Row"] == 5
    assert table.loc[1, "Column"] == "(tab name)"
    assert pd.isna(table.loc[1, "Row"])
    assert table.loc[2, "Column"] == "Pat Example (header)"
    assert pd.isna(table.loc[2, "Row"])


def test_the_default_pdf_mapping_header_is_pinned_without_any_name_column() -> None:
    """A name column cannot be added to the Internal file by accident."""
    df = pdf_mapping_dataframe([_assignment()])

    assert list(df.columns) == [
        "Label",
        "Internal ID",
        "Category",
        "Entity type",
        "Flagged",
        "Master list",
    ]


def test_the_opt_in_mapping_adds_the_name_and_keeps_the_same_rows() -> None:
    assignment = _assignment(ordinal=3)
    default = pdf_mapping_dataframe([assignment], "list@1")

    named = pdf_mapping_with_names_dataframe([assignment], "list@1")

    assert list(named.columns) == [
        "Label",
        "Original name",
        "Internal ID",
        "Category",
        "Entity type",
        "Flagged",
        "Possible match",
        "Master list",
    ]
    assert named.loc[0, "Original name"] == _DISTINCTIVE
    for column in default.columns:
        assert named.loc[0, column] == default.loc[0, column]


def test_the_opt_in_mapping_shows_unresolved_rows_and_the_possible_match() -> None:
    assignment = _assignment(
        pseudonym="CST-AUTO-3F9A1C07",
        auto=True,
        internal_id=None,
        category="",
        suggested_pseudonym="STF-12345",
        suggested_name="Michael Sample",
        suggested_score=0.92,
    )

    named = pdf_mapping_with_names_dataframe([assignment])

    assert named.loc[0, "Internal ID"] == "CST-AUTO-3F9A1C07"
    assert named.loc[0, "Flagged"] == "not in master list"
    assert named.loc[0, "Possible match"] == "Michael Sample (STF-12345, 92% match)"


class _Fmt:
    def __init__(self, dropped: dict[str, int]) -> None:
        self.dropped = dropped


def test_formatting_note_totals_what_was_left_behind_across_tabs() -> None:
    formats = {
        "Jan": _Fmt({"formulas": 3, "comments": 1}),
        "Feb": _Fmt({"formulas": 2}),
    }

    note = formatting_note(formats, 2)

    assert note == (
        "Not carried over from the original: formulas: 5 (their values are kept), "
        "comments: 1."
    )


def test_formatting_note_is_empty_when_nothing_was_left_behind() -> None:
    assert formatting_note({"Jan": _Fmt({})}, 1) == ""


def test_formatting_note_says_so_when_formatting_could_not_be_read() -> None:
    assert "could not be read" in formatting_note({}, 2)


def _model(text: str, score: float = 0.85, entity: str = "ORGANIZATION") -> Finding:
    return Finding(
        page=0,
        detected_text=text,
        entity_type=entity,
        score=score,
        source=DetectionSource.MODEL,
    )


def _mixed_findings() -> list[Finding]:
    return [
        _finding("Care Organisation"),  # master list
        _model("Jane Doe", 0.6, "PERSON"),  # plain model guess
        _model("Salaries"),  # one-word organization hint
        _model("Across"),  # ordinary word hint
        _finding("jane@example.org", source=DetectionSource.PATTERN),
        _finding("Project Nightingale", source=DetectionSource.CUSTOM),
        _model("Mary Test", 0.4, "PERSON"),  # plain model guess, lower score
    ]


def test_editor_puts_the_likely_false_positives_first_and_curated_names_last() -> None:
    terms = review_terms(_mixed_findings())

    assert [t.term for t in terms] == [
        "Salaries",
        "Across",
        "Mary Test",
        "Jane Doe",
        "Project Nightingale",
        "jane@example.org",
        "Care Organisation",
    ]


def test_editor_reports_confidence_and_hint_per_term() -> None:
    terms = review_terms(
        [_model("Across", 0.5), _model("across", 0.8), _finding("Care Organisation")]
    )

    across = next(t for t in terms if t.term == "Across")
    assert across.confidence == 0.8  # strongest of its occurrences
    assert across.hint == "ordinary word"
    assert across.occurrences == 2
    curated = next(t for t in terms if t.term == "Care Organisation")
    assert curated.hint == ""


def test_review_summary_counts_each_kind_and_the_hinted_ones() -> None:
    summary = review_summary(review_terms(_mixed_findings()))

    assert summary == (
        "7 terms: 4 model guesses (2 worth a closer look), 1 typed word, "
        "1 pattern match, 1 master-list name."
    )


def _unlocated(page: int, text: str) -> Finding:
    return Finding(
        page=page,
        detected_text=text,
        entity_type="PERSON",
        score=1.0,
        source=DetectionSource.CUSTOM,
    )


def test_not_located_warning_names_the_terms_and_pages() -> None:
    warning = not_located_warning(
        [_unlocated(2, "Zorbo Quillfeather"), _unlocated(0, "Ann Example")]
    )

    assert warning.startswith("**2 detected terms could not be found on the page")
    assert "(page 1, 3)" in warning
    assert "`Ann Example`, `Zorbo Quillfeather`" in warning


def _job_note(scanned: int, total: int, reading_scans: bool = True) -> str:
    return pdf_job_size_note(
        scanned,
        total,
        reading_scans=reading_scans,
        seconds_per_page=6.0,
        large_pages=300,
    )


def test_pdf_job_size_note_estimates_ocr_time_for_many_scans() -> None:
    note = _job_note(25, 40)

    # 25 pages at 6 seconds is 150 seconds: rounded up to 3 minutes.
    assert note.startswith("**25 scanned pages, about 3 minutes to read.**")
    assert "This PDF has" not in note


def test_pdf_job_size_note_stays_quiet_under_a_minute() -> None:
    assert _job_note(9, 9) == ""  # 54 seconds
    assert _job_note(10, 10).startswith("**10 scanned pages, about 1 minute")


def test_pdf_job_size_note_skips_the_estimate_when_scans_are_not_read() -> None:
    assert _job_note(200, 200, reading_scans=False) == ""


def test_pdf_job_size_note_warns_about_a_very_long_pdf() -> None:
    note = _job_note(0, 300)

    assert note.startswith("**This PDF has 300 pages.**")
    assert _job_note(0, 299) == ""


def test_not_located_warning_is_empty_when_everything_was_found() -> None:
    assert not_located_warning([]) == ""


def test_scanned_pages_warning_says_what_happens_to_the_pages() -> None:
    on = scanned_pages_warning([0], 3, images_blacked_out=True)
    off = scanned_pages_warning([0, 2], 3, images_blacked_out=False)

    assert on.startswith("**1 of 3 pages is a scan** (page 1)")
    assert "scanned image on that page is blacked out" in on
    assert off.startswith("**2 of 3 pages are scans** (page 1, 3)")
    assert "unredacted" in off


def test_scanned_pages_warning_for_pages_read_with_ocr() -> None:
    text = scanned_pages_warning([0, 1], 2, images_blacked_out=True, read=[0])

    read_part, unread_part = text.split("\n\n")
    assert read_part.startswith("**1 of 2 pages is a scan, read with OCR** (page 1)")
    assert "signatures, handwriting, stamps" in read_part
    assert "check that page" in read_part
    assert unread_part.startswith("**1 of 2 pages is a scan** (page 2)")


def test_merge_findings_adds_only_terms_not_already_listed() -> None:
    def finding(text: str) -> Finding:
        return Finding(
            page=0,
            detected_text=text,
            entity_type="CUSTOM",
            score=1.0,
            source=DetectionSource.TABLE_COLUMN,
        )

    existing = [finding("Alex Sample")]
    new = [finding("alex  sample"), finding("Robin Example")]

    merged = merge_findings(existing, new)

    assert [f.detected_text for f in merged] == ["Alex Sample", "Robin Example"]


def test_review_summary_counts_table_cells() -> None:
    findings = [
        Finding(
            page=0,
            detected_text="Alex Sample",
            entity_type="CUSTOM",
            score=1.0,
            source=DetectionSource.TABLE_COLUMN,
        )
    ]

    assert "1 table cell" in review_summary(review_terms(findings))


def _plain_finding(source: DetectionSource, entity_type: str = "PERSON") -> Finding:
    return Finding(
        page=0,
        detected_text="Across",
        entity_type=entity_type,
        score=0.85,
        source=source,
    )


def test_why_found_says_where_a_term_came_from_in_plain_words() -> None:
    assert (
        why_found(_plain_finding(DetectionSource.MASTER_LIST)) == "On your master list"
    )
    assert why_found(_plain_finding(DetectionSource.CUSTOM)) == "You typed it"
    assert why_found(_plain_finding(DetectionSource.TABLE_COLUMN)) == (
        "In a table column you chose"
    )
    assert why_found(_plain_finding(DetectionSource.PATTERN, "EMAIL_ADDRESS")) == (
        "Shaped like an email address"
    )
    assert why_found(_plain_finding(DetectionSource.MODEL)) == "Looks like a name"
    assert why_found(_plain_finding(DetectionSource.MODEL, "ORGANIZATION")) == (
        "Looks like an organization"
    )


def test_why_found_turns_a_hint_into_advice() -> None:
    why = why_found(_plain_finding(DetectionSource.MODEL), "ordinary word")

    assert why == "Looks like a name. Check it: it is an ordinary English word"


def test_the_review_table_fills_the_why_column() -> None:
    (term,) = review_terms([_plain_finding(DetectionSource.MASTER_LIST)])

    assert term.why == "On your master list"
    assert term.kind == "Person"


def test_pdf_mapping_notes_cover_missing_and_ambiguous_items() -> None:
    def item(ambiguous: bool, internal_id: str | None = None) -> Assignment:
        return Assignment(
            original_name="Zzyzx Qwertyson",
            entity_type="PERSON",
            category="",
            pseudonym="PSN-AUTO-1A2B3C4D",
            auto=True,
            ordinal=1,
            internal_id=internal_id,
            ambiguous=ambiguous,
        )

    notes = pdf_mapping_notes([item(False), item(True), item(False, "17728")])

    assert len(notes) == 2
    assert "1 redacted item not on the master list" in notes[0]
    assert "matched more than one" in notes[1]
    assert pdf_mapping_notes([item(False, "17728")]) == []


def test_carry_over_keeps_only_unticked_terms_the_new_scan_found_again() -> None:
    previous = frozenset({"salaries", "acme sample ltd"})
    findings = [_finding("SALARIES"), _finding("Jane Test")]

    assert carry_over_exclusions(previous, findings) == frozenset({"salaries"})


def test_carry_over_of_nothing_is_nothing() -> None:
    assert carry_over_exclusions(frozenset(), [_finding("Salaries")]) == frozenset()


def test_every_source_has_a_readable_label() -> None:
    from finance_redactor.presentation.presenters import source_label

    labels = {source_label(source) for source in DetectionSource}

    assert len(labels) == len(DetectionSource)
    assert all(label[0].isupper() and "_" not in label for label in labels)


@pytest.mark.parametrize(
    ("entity_type", "label", "why"),
    [
        ("URL", "Website", "Shaped like a website"),
        ("IBAN_CODE", "IBAN", "Shaped like an IBAN"),
        ("MPESA_NUMBER", "M-Pesa number", "Shaped like an M-Pesa number"),
        ("KE_BANK_ACCOUNT", "Kenyan bank account", "Shaped like a Kenyan bank account"),
        ("EMAIL_ADDRESS", "Email address", "Shaped like an email address"),
    ],
)
def test_entity_codes_read_as_plain_words(
    entity_type: str, label: str, why: str
) -> None:
    finding = Finding(
        page=0,
        detected_text="made-up value",
        entity_type=entity_type,
        score=1.0,
        source=DetectionSource.PATTERN,
    )

    assert entity_label(entity_type) == label
    assert why_found(finding) == why


def test_name_summary_lists_the_first_names_then_a_count() -> None:
    assert name_summary(["Jan"]) == "Jan"
    assert name_summary(["Jan", "Feb"]) == "Jan, Feb"
    assert name_summary(["Jan", "Feb", "Mar"]) == "Jan, Feb + 1 more"
    assert name_summary([f"T{n}" for n in range(12)]) == "T0, T1 + 10 more"


def test_no_size_warning_for_an_ordinary_workbook() -> None:
    df = pd.DataFrame({"notes": [f"value {n}" for n in range(2_999)]})
    assert scan_size_warning({"Jan": df}, {"Jan": ["notes"]}) is None


def test_many_distinct_values_warn_with_a_time_range() -> None:
    df = pd.DataFrame(
        {"notes": [f"value {n}" for n in range(30_000)], "other": ["x"] * 30_000}
    )
    message = scan_size_warning({"Jan": df}, {"Jan": ["notes"]})
    assert message is not None
    assert "30,000 distinct values" in message
    assert "roughly 8 to 17 minutes" in message
    assert "held in memory" not in message  # 60,000 cells is not big


def test_distinct_values_count_only_chosen_columns_and_repeat_once() -> None:
    df = pd.DataFrame(
        {
            "notes": [f"value {n % 100}" for n in range(3_000)],
            "unchosen": [f"other {n}" for n in range(3_000)],
        }
    )
    assert scan_size_warning({"Jan": df}, {"Jan": ["notes"]}) is None


def test_a_very_big_workbook_warns_about_memory_too() -> None:
    df = pd.DataFrame({"a": ["same"] * 250_000, "b": [1] * 250_000})
    message = scan_size_warning({"Jan": df}, {"Jan": ["a"]})
    assert message is not None
    assert "500,000 cells" in message
    assert "held in memory" in message
    assert "minutes" not in message  # one distinct value scans quickly
