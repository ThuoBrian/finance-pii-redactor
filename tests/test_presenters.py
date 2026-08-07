"""Tests for presentation-layer view formatters."""

from __future__ import annotations

import pandas as pd

from finance_redactor.domain.pseudonyms import Assignment
from finance_redactor.presentation.presenters import (
    crosswalk_dataframe,
    highlighted_html,
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


def test_crosswalk_dataframe_surfaces_the_suggestion_s_own_category() -> None:
    """The 'Possible match' hint must show which category it came from.

    The fuzzy-match candidate pool is scoped by entity type only (Vendor and
    Funder both detect as ORGANIZATION), so a suggestion can come from a
    different category than the flagged name's own - the reviewer needs that
    visible, not folded away, to judge whether the match makes sense.
    """
    crosswalk = [
        Assignment(
            original_name="Acme Foundatio",
            entity_type="ORGANIZATION",
            category="",
            pseudonym="ORG-AUTO-1234",
            auto=True,
            suggested_pseudonym="FND-3001",
            suggested_name="Acme Foundation",
            suggested_score=0.92,
            suggested_category="Funder",
        )
    ]
    df = crosswalk_dataframe(crosswalk)
    assert (
        df.loc[0, "Possible match"] == "Acme Foundation (FND-3001, Funder, 92% match)"
    )
