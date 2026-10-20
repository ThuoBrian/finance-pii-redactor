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
