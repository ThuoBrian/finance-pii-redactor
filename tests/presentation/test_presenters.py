"""Tests for presentation-layer view formatters."""

from __future__ import annotations

import pandas as pd

from finance_redactor.application.results import CellFinding, ExcelScanResult
from finance_redactor.domain.entities import (
    DetectionSource,
    Finding,
    PiiDetection,
    Span,
)
from finance_redactor.domain.pseudonyms import Assignment
from finance_redactor.presentation.presenters import (
    crosswalk_dataframe,
    detection_editor_dataframe,
    excluded_terms,
    findings_dataframe,
    highlighted_html,
    pdf_mapping_dataframe,
    pdf_review_dataframe,
    scan_result_findings,
)


def test_highlighted_html_escapes_cell_values() -> None:
    """A cell containing markup must not produce unescaped HTML.

    Cell values come from user-uploaded files (often authored by a third party,
    e.g. a vendor's spreadsheet), and the caller renders this output with
    Streamlit's ``unsafe_allow_html=True``, so unescaped markup would execute in
    the browser.
    """
    df = pd.DataFrame(
        {"Name": ["<img src=x onerror=alert(1)>", "<script>evil()</script>"]}
    )
    rendered = highlighted_html(df, cell_keys=set(), bg="#FFA500")
    assert "<img" not in rendered
    assert "<script>" not in rendered
    assert "&lt;img src=x onerror=alert(1)&gt;" in rendered
    assert "&lt;script&gt;evil()&lt;/script&gt;" in rendered


def test_highlighted_html_escapes_column_headers() -> None:
    """A column name containing markup is also escaped."""
    df = pd.DataFrame({"<b>Name</b>": ["Alice"]})
    rendered = highlighted_html(df, cell_keys=set(), bg="#FFA500")
    assert "<b>Name</b>" not in rendered
    assert "&lt;b&gt;Name&lt;/b&gt;" in rendered


def test_highlighted_html_still_highlights_selected_cells() -> None:
    """Escaping must not break the existing cell-highlighting behavior."""
    df = pd.DataFrame({"Name": ["Alice", "Bob"]})
    rendered = highlighted_html(df, cell_keys={(0, "Name")}, bg="#90EE90")
    assert 'style="background:#90EE90;padding:4px 8px">Alice</td>' in rendered
    assert 'style="padding:4px 8px">Bob</td>' in rendered


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

    assert bool(table.loc[0, "Redact?"]) is True


def test_unticking_round_trips_through_excluded_terms() -> None:
    """The editor and its inverse have to agree, or a tick would not stick."""
    findings = [_finding("Salaries"), _finding("Care Organisation")]
    table = detection_editor_dataframe(findings)
    table.loc[table["Detected text"] == "Salaries", "Redact?"] = False

    excluded = excluded_terms(table)

    assert excluded == frozenset({"salaries"})
    # Seeding a fresh table with that set leaves the same row unticked.
    reseeded = detection_editor_dataframe(findings, excluded)
    assert bool(reseeded.loc[0, "Redact?"]) is False
    assert bool(reseeded.loc[1, "Redact?"]) is True


def test_empty_inputs_exclude_nothing() -> None:
    """Losing the widget state must fail towards redacting, not away from it."""
    assert excluded_terms(pd.DataFrame()) == frozenset()
    assert detection_editor_dataframe([]).empty
    assert list(detection_editor_dataframe([]).columns) == [
        "Redact?",
        "Detected text",
        "Entity type",
        "Source",
        "Occurrences",
    ]


def test_scan_result_findings_flattens_excel_cells() -> None:
    """Excel shares the editor, so its cell findings become Findings."""
    detection = PiiDetection(
        entity_type="PERSON",
        span=Span(0, 8),
        score=0.9,
        text="Jane Doe",
        source=DetectionSource.MASTER_LIST,
    )
    scan = ExcelScanResult(
        findings=[CellFinding(row=4, column="notes", detections=[detection])]
    )

    flattened = scan_result_findings(scan)

    assert len(flattened) == 1
    assert flattened[0].detected_text == "Jane Doe"
    assert flattened[0].page == 4
