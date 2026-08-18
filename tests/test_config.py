"""Unit tests for master-list location resolution in ``config.py``."""

from __future__ import annotations

from pathlib import Path

from finance_redactor.config import DEFAULT_SETTINGS, _resolve_data_dir


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


def test_date_time_is_never_a_supported_entity():
    # Dates/times aren't the PII this tool protects, and an entity type missing
    # from auto_prefixes silently falls back to a junk 3-letter prefix in
    # Pseudonymizer._auto_pseudonym (e.g. "DAT-AUTO-<hash>") instead of erroring -
    # so DATE_TIME must never be added to either collection. See the comments
    # above `_DEFAULT_AUTO_PREFIXES`/`supported_entities` in config.py.
    assert "DATE_TIME" not in DEFAULT_SETTINGS.supported_entities
    assert "DATE_TIME" not in DEFAULT_SETTINGS.auto_prefixes
