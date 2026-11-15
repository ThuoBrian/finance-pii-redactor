"""Tests for the master-list setup dialog: the path helper and its buttons."""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from finance_redactor.config import read_persisted_master_list_dir
from finance_redactor.presentation.master_list_setup import (
    MASTER_LIST_FILENAME,
    master_list_exists_at,
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


@pytest.fixture
def home(tmp_path, monkeypatch) -> Path:
    """Keep the per-user settings file inside the test's tmp dir."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    return tmp_path / "home"


def test_save_is_disabled_until_a_folder_is_entered(home):
    assert _save(_run_dialog()).disabled


def test_save_is_enabled_when_the_workbook_is_found(home, tmp_path):
    (tmp_path / MASTER_LIST_FILENAME).write_text("placeholder")
    at = _run_dialog()
    at.text_input[0].input(str(tmp_path)).run()

    assert not _save(at).disabled
    assert not at.checkbox  # no confirmation needed


def test_missing_workbook_needs_an_explicit_confirmation(home, tmp_path):
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
