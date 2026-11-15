"""Tests for the master-list setup dialog: the path helper and its buttons."""

from __future__ import annotations

from streamlit.testing.v1 import AppTest

from finance_redactor.config import (
    master_list_setup_skipped,
    read_persisted_master_list_dir,
    set_master_list_setup_skipped,
)
from finance_redactor.presentation.master_list_setup import (
    MASTER_LIST_FILENAME,
    master_list_exists_at,
    should_offer_setup,
)


def _dialog() -> None:
    from pathlib import Path

    from finance_redactor.presentation.master_list_setup import (
        render_master_list_setup_dialog,
    )

    render_master_list_setup_dialog(Path("unused"))


def _run_dialog() -> AppTest:
    return AppTest.from_function(_dialog, default_timeout=30).run()


def _save(at: AppTest):
    return next(b for b in at.button if b.label == "Save and use this folder")


# Path.home() is redirected to tmp_path by the autouse fixture in conftest.py.


def test_save_is_disabled_until_a_folder_is_entered():
    assert _save(_run_dialog()).disabled


def test_skip_is_remembered_across_launches():
    at = _run_dialog()
    next(b for b in at.button if b.label == "Skip for now").click().run()

    assert master_list_setup_skipped() is True


def test_skipped_dialog_stays_closed_until_a_list_loads():
    assert should_offer_setup(has_names=False) is True

    set_master_list_setup_skipped(True)
    assert should_offer_setup(has_names=False) is False  # a later launch

    # A list with names clears the flag, so losing it again prompts again.
    assert should_offer_setup(has_names=True) is False
    assert master_list_setup_skipped() is False
    assert should_offer_setup(has_names=False) is True


def test_save_is_enabled_when_the_workbook_is_found(tmp_path):
    (tmp_path / MASTER_LIST_FILENAME).write_text("placeholder")
    at = _run_dialog()
    at.text_input[0].input(str(tmp_path)).run()

    assert not _save(at).disabled
    assert not at.checkbox  # no confirmation needed


def test_missing_workbook_needs_an_explicit_confirmation(tmp_path):
    at = _run_dialog()
    at.text_input[0].input(str(tmp_path)).run()

    assert at.warning
    assert _save(at).disabled

    at.checkbox[0].check().run()
    assert not _save(at).disabled
    _save(at).click().run()
    assert read_persisted_master_list_dir() == tmp_path


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
