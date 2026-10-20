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
    CHANGED_MARKER,
    HIGHLIGHT_HEX,
    apply_notice,
    crosswalk_dataframe,
    detection_editor_dataframe,
    excel_findings_dataframe,
    excluded_terms,
    filter_editor_rows,
    findings_dataframe,
    formatting_note,
    merge_pending,
    ordinary_word_terms,
    pdf_mapping_dataframe,
    pdf_mapping_with_names_dataframe,
    pdf_review_dataframe,
    plural,
    preview_hidden_count,
    preview_styler,
    review_status,
    review_summary,
    review_tab_labels,
    scan_result_findings,
    search_editor_rows,
)


def test_preview_shows_markup_literally_and_never_as_html_source() -> None:
    """Cell text with markup stays text; st.dataframe draws it on a canvas."""
    df = pd.DataFrame({"<b>Name</b>": ["<img src=x onerror=alert(1)>", "**bold**"]})
    styler = preview_styler(df, cell_keys=set())
    assert list(styler.data.columns) == ["<b>Name</b>"]
    assert list(styler.data["<b>Name</b>"]) == [
        "<img src=x onerror=alert(1)>",
        "**bold**",
    ]


def test_preview_marks_flagged_cells_by_text_and_by_colour() -> None:
    df = pd.DataFrame({"Name": ["Alice Test", "Bob Test"], "Note": ["a", "b"]})
    styler = preview_styler(df, cell_keys={(0, "Name")})
    assert list(styler.data["Name"]) == [CHANGED_MARKER + "Alice Test", "Bob Test"]
    assert list(styler.data["Note"]) == ["a", "b"]
    html = styler.to_html()
    assert html.count(HIGHLIGHT_HEX) == 1  # only the flagged cell is filled
    assert HIGHLIGHT_HEX == "#FFFF00"  # same yellow as the downloaded workbook


def test_preview_renders_missing_values_as_empty_text() -> None:
    df = pd.DataFrame({"Name": ["Alice Test", None]})
    assert list(preview_styler(df, cell_keys=set()).data["Name"]) == ["Alice Test", ""]


def test_preview_is_row_capped_and_reports_flagged_cells_it_hid() -> None:
    df = pd.DataFrame({"Name": [f"Person {i}" for i in range(5)]})
    keys = {(0, "Name"), (3, "Name"), (4, "Name")}
    styler = preview_styler(df, keys, max_rows=2)
    assert len(styler.data) == 2
    assert preview_hidden_count(df, keys, max_rows=2) == 2
    assert preview_hidden_count(df, keys, max_rows=5) == 0


def test_preview_ignores_keys_for_unknown_rows_or_columns() -> None:
    df = pd.DataFrame({"Name": ["Alice Test"]})
    styler = preview_styler(df, {(9, "Name"), (0, "Missing")})
    assert list(styler.data["Name"]) == ["Alice Test"]


@pytest.mark.parametrize(
    ("count", "expected"),
    [(0, "0 matches"), (1, "1 match"), (2, "2 matches"), (1234, "1,234 matches")],
)
def test_plural_picks_the_right_noun_form(count: int, expected: str) -> None:
    assert plural(count, "match", "matches") == expected


def test_plural_defaults_to_adding_s() -> None:
    assert plural(1, "page") == "1 page"
    assert plural(3, "page") == "3 pages"


def test_findings_dataframe_labels_the_location_column_paragraph() -> None:
    """Docx findings reuse Finding.page, labeled 'Paragraph' rather than 'Page'."""
    findings = [
        Finding(
            page=2,
            detected_text="John Doe",
            entity_type="PERSON",
            score=0.87,
            source=DetectionSource.MODEL,
        )
    ]
    df = findings_dataframe(findings, "Paragraph")
    assert list(df.columns) == [
        "Paragraph",
        "Detected text",
        "Entity type",
        "Confidence",
        "Source",
    ]
    assert df.iloc[0]["Paragraph"] == 3


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
                pseudonym="CST-AUTO-3F9A1", auto=True, internal_id=None, category=""
            )
        ]
    )

    assert df.loc[0, "Internal ID"] == "CST-AUTO-3F9A1"
    assert df.loc[0, "Flagged"] == "not in master list"
    assert _DISTINCTIVE not in df.to_csv(index=False)


def test_ambiguous_row_is_flagged_distinctly_from_a_plain_orphan() -> None:
    """An ID that was refused differs from one that was never there."""
    df = pdf_mapping_dataframe(
        [
            _assignment(
                pseudonym="CST-AUTO-3F9A1",
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

    table = detection_editor_dataframe(findings)

    assert len(table) == 1
    assert table.loc[0, "Occurrences"] == 3
    assert table.loc[0, "Detected text"] == "Salaries"


def test_editor_groups_across_casing_and_spacing() -> None:
    """Grouping uses the same normalization the services compare with.

    Otherwise unticking "Salaries" would leave "SALARIES" still redacted.
    """
    findings = [_finding("Salaries"), _finding("salaries"), _finding("  SALARIES  ")]

    table = detection_editor_dataframe(findings)

    assert len(table) == 1
    assert table.loc[0, "Occurrences"] == 3


def test_editor_reports_the_source_so_the_user_knows_which_fix_applies() -> None:
    """Master list -> edit the workbook; model -> raise the threshold."""
    findings = [
        _finding("Salaries"),
        _finding("someone@example.org", source=DetectionSource.PATTERN),
    ]

    table = detection_editor_dataframe(findings)

    assert set(table["Source"]) == {"master list", "pattern match"}


def test_editor_defaults_to_redacting_everything() -> None:
    """The safe default: nothing is excluded until someone unticks it."""
    table = detection_editor_dataframe([_finding("Salaries")])

    assert bool(table.loc[0, "Hide in output?"]) is True


def test_unticking_round_trips_through_excluded_terms() -> None:
    """The editor and its inverse have to agree, or a tick would not stick."""
    findings = [_finding("Salaries"), _finding("Care Organisation")]
    table = detection_editor_dataframe(findings)
    table.loc[table["Detected text"] == "Salaries", "Hide in output?"] = False

    excluded = excluded_terms(table)

    assert excluded == frozenset({"salaries"})
    # Seeding a fresh table with that set leaves the same row unticked.
    reseeded = detection_editor_dataframe(findings, excluded)
    assert bool(reseeded.loc[0, "Hide in output?"]) is False
    assert bool(reseeded.loc[1, "Hide in output?"]) is True


def test_empty_inputs_exclude_nothing() -> None:
    """Losing the widget state must fail towards redacting, not away from it."""
    assert excluded_terms(pd.DataFrame()) == frozenset()
    assert detection_editor_dataframe([]).empty
    assert list(detection_editor_dataframe([]).columns) == [
        "Hide in output?",
        "Detected text",
        "Entity type",
        "Source",
        "Confidence",
        "Hint",
        "Occurrences",
    ]


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
    )


def test_scan_result_findings_flattens_excel_cells_and_tab_names() -> None:
    """Excel shares the editor, so cell and tab-name findings become Findings."""
    flattened = scan_result_findings(_workbook_scan())

    assert [f.detected_text for f in flattened] == ["Jane Doe", "Acme Ltd"]
    assert flattened[0].page == 4
    assert flattened[1].page == -1


def test_excel_findings_dataframe_names_the_sheet_for_every_finding() -> None:
    table = excel_findings_dataframe(_workbook_scan())

    assert list(table["Sheet"]) == ["Jan", "Feb"]
    assert table.loc[0, "Row"] == 5
    assert table.loc[1, "Column"] == "(tab name)"
    assert pd.isna(table.loc[1, "Row"])


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
        pseudonym="CST-AUTO-3F9A1",
        auto=True,
        internal_id=None,
        category="",
        suggested_pseudonym="STF-12345",
        suggested_name="Michael Sample",
        suggested_score=0.92,
    )

    named = pdf_mapping_with_names_dataframe([assignment])

    assert named.loc[0, "Internal ID"] == "CST-AUTO-3F9A1"
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
    table = detection_editor_dataframe(_mixed_findings())

    assert list(table["Detected text"]) == [
        "Salaries",
        "Across",
        "Mary Test",
        "Jane Doe",
        "Project Nightingale",
        "jane@example.org",
        "Care Organisation",
    ]


def test_editor_reports_confidence_and_hint_per_term() -> None:
    table = detection_editor_dataframe(
        [_model("Across", 0.5), _model("across", 0.8), _finding("Care Organisation")]
    )

    across = table[table["Detected text"] == "Across"].iloc[0]
    assert across["Confidence"] == 0.8  # strongest of its occurrences
    assert across["Hint"] == "ordinary word"
    assert across["Occurrences"] == 2
    curated = table[table["Detected text"] == "Care Organisation"].iloc[0]
    assert curated["Hint"] == ""


def test_review_summary_counts_each_kind_and_the_hinted_ones() -> None:
    summary = review_summary(detection_editor_dataframe(_mixed_findings()))

    assert summary == (
        "7 terms: 4 model guesses (2 worth a closer look), 1 typed word, "
        "1 pattern match, 1 master-list name."
    )


def test_filter_shows_one_source_and_all_by_default() -> None:
    table = detection_editor_dataframe(_mixed_findings())

    assert len(filter_editor_rows(table, None)) == 7
    assert len(filter_editor_rows(table, "All")) == 7
    assert set(filter_editor_rows(table, "Model guesses")["Source"]) == {"model"}
    assert len(filter_editor_rows(table, "Model guesses")) == 4


def test_ordinary_word_terms_only_picks_the_plain_english_hint() -> None:
    table = detection_editor_dataframe(_mixed_findings())

    assert ordinary_word_terms(table) == frozenset({"across"})


def test_a_filter_never_changes_a_hidden_rows_tick() -> None:
    """Hidden rows keep their state: filtering is display only."""
    table = detection_editor_dataframe(_mixed_findings())
    shown = filter_editor_rows(table, "Model guesses")
    edited = shown.copy()
    edited.loc[edited["Detected text"] == "Across", "Hide in output?"] = False
    already_unticked_but_hidden = frozenset({"care organisation"})

    merged = merge_pending(already_unticked_but_hidden, shown, edited)

    assert merged == frozenset({"care organisation", "across"})


def test_reticking_a_shown_row_removes_it_from_the_pending_set() -> None:
    table = detection_editor_dataframe(_mixed_findings())
    shown = filter_editor_rows(table, "Model guesses")

    merged = merge_pending(frozenset({"across"}), shown, shown)  # all ticked again

    assert merged == frozenset()


def test_review_comes_first_and_counts_the_model_guesses() -> None:
    findings = _mixed_findings()  # 4 model guesses among 7 terms

    assert review_tab_labels(findings) == [
        "Review (4 to check)",
        "Mapping",
        "Occurrences",
    ]
    assert review_tab_labels(findings, preview=True)[1] == "Preview"


def test_review_tab_label_has_no_count_when_nothing_is_a_guess() -> None:
    assert review_tab_labels([_finding("Care Organisation")])[0] == "Review"
    assert review_tab_labels([])[0] == "Review"


def test_review_tab_label_does_not_depend_on_the_ticks() -> None:
    """Streamlit keys tabs by label; a label that moved would jump tabs."""
    findings = _mixed_findings()

    assert review_tab_labels(findings) == review_tab_labels(list(findings))


def test_review_status_says_what_is_left_to_do() -> None:
    table = detection_editor_dataframe(_mixed_findings())

    assert review_status(table, frozenset(), frozenset()) == "4 model guesses to check"
    assert review_status(
        table, frozenset({"across"}), frozenset({"across", "salaries", "mary test"})
    ) == ("4 model guesses to check · 1 term left visible · 2 changes not applied yet")


def test_review_status_for_a_clean_run() -> None:
    table = detection_editor_dataframe([_finding("Care Organisation")])

    assert review_status(table, frozenset(), frozenset()) == (
        "Every detected term will be hidden."
    )


def test_search_is_case_insensitive_and_blank_shows_everything() -> None:
    table = detection_editor_dataframe(_mixed_findings())

    assert len(search_editor_rows(table, "")) == 7
    assert len(search_editor_rows(table, None)) == 7
    assert list(search_editor_rows(table, "JANE")["Detected text"]) == [
        "Jane Doe",
        "jane@example.org",
    ]


def test_search_combines_with_the_source_filter() -> None:
    table = detection_editor_dataframe(_mixed_findings())

    shown = search_editor_rows(filter_editor_rows(table, "Model guesses"), "jane")

    assert list(shown["Detected text"]) == ["Jane Doe"]


def test_apply_notice_says_what_was_left_visible() -> None:
    assert (
        apply_notice(frozenset()) == "Rebuilt the file. Every detected term is hidden."
    )
    assert apply_notice(frozenset({"across"})) == (
        "Rebuilt the file. 1 term is left visible; they are listed above the download."
    )


def test_findings_from_before_a_module_reload_still_sort_and_hint() -> None:
    """Streamlit re-imports changed modules, so a finding kept in session state
    can hold a member of an older copy of ``DetectionSource``. It is equal in
    value but not the same object; the review table must not crash on it.
    """
    from enum import Enum

    reloaded = Enum(  # type: ignore[misc]
        "DetectionSource", {m.name: m.value for m in DetectionSource}, type=str
    )
    findings = [
        Finding(
            page=0,
            detected_text=text,
            entity_type="ORGANIZATION",
            score=0.85,
            source=reloaded[name],
        )
        for text, name in (("Across", "MODEL"), ("Care Organisation", "MASTER_LIST"))
    ]

    table = detection_editor_dataframe(findings)

    assert list(table["Detected text"]) == ["Across", "Care Organisation"]
    assert table.loc[0, "Hint"] == "ordinary word"
    assert review_tab_labels(findings)[0] == "Review (1 to check)"
