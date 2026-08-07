"""Unit tests for the master-list status panel's pure text helper."""

from __future__ import annotations

from pathlib import Path

from finance_redactor.presentation.master_list_view import _name_list_help


def test_help_text_shows_the_actual_resolved_path():
    # Must reflect wherever Settings.master_list_file actually resolved to
    # (the local data/ folder by default, or a shared FPR_MASTER_LIST_DIR
    # location) - never a hardcoded string that could point at the wrong file.
    shared_path = Path("C:/Users/Someone/Box/Team/Master List Folder") / (
        "Names List - Organized.xlsx"
    )

    text = _name_list_help({"Staff": 2, "Vendor": 1}, shared_path)

    assert str(shared_path) in text
    assert "data/Names List - Organized.xlsx" not in text


def test_help_text_reports_total_and_per_category_counts():
    text = _name_list_help(
        {"Staff": 5639, "Vendor": 14797, "Funder": 6093},
        Path("data/Names List - Organized.xlsx"),
    )

    assert "26,529" in text
    assert "5,639 Staff" in text
    assert "14,797 Vendor" in text
    assert "6,093 Funder" in text


def test_help_text_handles_empty_counts():
    text = _name_list_help({}, Path("data/Names List - Organized.xlsx"))

    assert "Loaded 0 master-list entr(y/ies): none." in text
