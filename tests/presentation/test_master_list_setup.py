"""Unit tests for the master-list setup dialog's pure validation helper."""

from __future__ import annotations

from finance_redactor.presentation.master_list_setup import (
    MASTER_LIST_FILENAME,
    master_list_exists_at,
)


def test_finds_the_workbook_at_an_exact_path(tmp_path):
    (tmp_path / MASTER_LIST_FILENAME).write_text("not a real workbook")

    assert master_list_exists_at(str(tmp_path)) is True


def test_missing_workbook_returns_false(tmp_path):
    assert master_list_exists_at(str(tmp_path)) is False


def test_blank_input_returns_false():
    assert master_list_exists_at("") is False
    assert master_list_exists_at("   ") is False


def test_renamed_or_versioned_file_does_not_match(tmp_path):
    (tmp_path / "Names List - Organized (2).xlsx").write_text("not a real workbook")

    assert master_list_exists_at(str(tmp_path)) is False


def test_surrounding_whitespace_in_the_path_is_tolerated(tmp_path):
    (tmp_path / MASTER_LIST_FILENAME).write_text("not a real workbook")

    assert master_list_exists_at(f"  {tmp_path}  ") is True
