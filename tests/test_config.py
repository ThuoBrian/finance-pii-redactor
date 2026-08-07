"""Unit tests for master-list location resolution in ``config.py``."""

from __future__ import annotations

from pathlib import Path

from finance_redactor.config import _resolve_data_dir


def test_default_data_dir_is_next_to_the_package(monkeypatch):
    monkeypatch.delenv("FPR_MASTER_LIST_DIR", raising=False)

    data_dir = _resolve_data_dir()

    assert data_dir == Path(__file__).parent.parent / "data"


def test_env_override_points_at_a_shared_location(monkeypatch, tmp_path):
    shared = tmp_path / "shared" / "master-list-folder"
    monkeypatch.setenv("FPR_MASTER_LIST_DIR", str(shared))

    data_dir = _resolve_data_dir()

    assert data_dir == shared


def test_blank_env_override_falls_back_to_the_default(monkeypatch):
    # An empty string (e.g. a variable that's set but cleared) should not
    # resolve to the current working directory - fall back to the default.
    monkeypatch.setenv("FPR_MASTER_LIST_DIR", "")

    data_dir = _resolve_data_dir()

    assert data_dir == Path(__file__).parent.parent / "data"
