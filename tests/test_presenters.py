"""Tests for presentation-layer view formatters."""

from __future__ import annotations

import pandas as pd

from finance_redactor.presentation.presenters import highlighted_html


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
