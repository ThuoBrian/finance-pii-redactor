"""Unit tests for the master-list status panel's pure text helpers."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from finance_redactor.presentation.master_list_view import (
    _format_absolute,
    _name_list_help,
    _relative_time,
)

_NOW = datetime(2026, 8, 7, 15, 47)


def test_help_text_shows_the_actual_resolved_path():
    # Must reflect wherever Settings.master_list_file actually resolved to
    # (the local data/ folder by default, or a shared FPR_MASTER_LIST_DIR
    # location) - never a hardcoded string that could point at the wrong file.
    shared_path = Path("C:/Users/Someone/Box/Team/Master List Folder") / (
        "Names List - Organized.xlsx"
    )

    text = _name_list_help({"Staff": 2, "Vendor": 1}, shared_path, None, _NOW)

    assert str(shared_path) in text
    assert "data/Names List - Organized.xlsx" not in text


def test_help_text_reports_total_and_per_category_counts():
    text = _name_list_help(
        {"Staff": 5639, "Vendor": 14797, "Funder": 6093},
        Path("data/Names List - Organized.xlsx"),
        None,
        _NOW,
    )

    assert "26,529" in text
    assert "5,639 Staff" in text
    assert "14,797 Vendor" in text
    assert "6,093 Funder" in text


def test_help_text_handles_empty_counts():
    text = _name_list_help({}, Path("data/Names List - Organized.xlsx"), None, _NOW)

    assert "Loaded 0 master-list entr(y/ies): none." in text


def test_help_text_omits_last_updated_clause_when_unknown():
    # A missing file (e.g. before it's ever been added) has no mtime to show.
    text = _name_list_help({}, Path("data/Names List - Organized.xlsx"), None, _NOW)

    assert "Last updated" not in text


def test_help_text_includes_last_updated_clause_when_known():
    last_updated = _NOW - timedelta(minutes=5)

    text = _name_list_help(
        {"Staff": 1}, Path("data/Names List - Organized.xlsx"), last_updated, _NOW
    )

    assert "Last updated" in text
    assert "5 minutes ago" in text


def test_format_absolute_has_no_leading_zero_and_correct_am_pm():
    # Hand-rolled instead of strftime's %-d/%-I (GNU extensions Windows'
    # C runtime doesn't reliably support) - verify the portable version.
    assert _format_absolute(datetime(2026, 8, 7, 15, 42)) == "Aug 7, 2026 at 3:42 PM"
    assert _format_absolute(datetime(2026, 1, 1, 0, 5)) == "Jan 1, 2026 at 12:05 AM"
    assert _format_absolute(datetime(2026, 1, 1, 12, 0)) == "Jan 1, 2026 at 12:00 PM"


def test_relative_time_buckets():
    assert _relative_time(30) == "just now"
    assert _relative_time(60) == "1 minute ago"
    assert _relative_time(300) == "5 minutes ago"
    assert _relative_time(3600) == "1 hour ago"
    assert _relative_time(7200) == "2 hours ago"
    assert _relative_time(86400) == "1 day ago"
    assert _relative_time(172800) == "2 days ago"


def test_relative_time_never_goes_negative():
    # A clock-skew edge case (mtime fractionally after "now") should still
    # read as "just now", not a nonsensical negative duration.
    assert _relative_time(-5) == "just now"
