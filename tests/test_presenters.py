"""Tests for presentation-layer view formatters."""

from __future__ import annotations

import pandas as pd

from finance_redactor.domain.entities import DetectionSource, Finding
from finance_redactor.domain.pseudonyms import Assignment
from finance_redactor.presentation.presenters import (
    crosswalk_dataframe,
    findings_dataframe,
    highlighted_html,
    pdf_mapping_dataframe,
    pdf_review_dataframe,
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
