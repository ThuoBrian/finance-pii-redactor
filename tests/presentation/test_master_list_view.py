"""Unit tests for the master-list card's pure text helpers."""

from __future__ import annotations

from finance_redactor.presentation.master_list_view import _counts_line, time_ago


def test_counts_line_lists_each_category_sorted() -> None:
    assert _counts_line({"Staff": 5639, "Vendor": 14797, "Funder": 6093}) == (
        "6,093 Funder · 5,639 Staff · 14,797 Vendor"
    )


def test_counts_line_handles_no_names() -> None:
    assert _counts_line({}) == "none"


def test_time_ago_is_rough_and_plain() -> None:
    assert time_ago(5) == "just now"
    assert time_ago(5 * 60) == "5 minutes ago"
    assert time_ago(2 * 3600 + 120) == "2 hours ago"
    assert time_ago(86400) == "1 day ago"


def _card_script() -> None:
    from pathlib import Path

    import streamlit as st

    from finance_redactor.presentation.master_list_view import render_master_list_card

    def refresh() -> None:
        st.session_state["refreshed"] = True

    with st.sidebar:
        render_master_list_card(
            {"Staff": 3, "Vendor": 2},
            None,
            Path("made_up") / "Names List.xlsx",
            age_seconds=120,
            on_refresh=refresh,
        )


def test_refresh_is_on_the_card_and_the_path_is_folded_away() -> None:
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_function(_card_script).run()

    assert [e.label for e in at.expander] == ["Where it is"]
    assert not at.expander[0].button  # Refresh is not inside the expander
    assert any("Names List.xlsx" in c.value for c in at.expander[0].caption)

    at.button(key="master_list_refresh").click().run()

    assert at.session_state["refreshed"] is True
