"""Unit tests for master-list location resolution in ``config.py``."""

from __future__ import annotations

import json
from pathlib import Path

from finance_redactor.config import (
    DEFAULT_SETTINGS,
    _resolve_data_dir,
    current_settings,
    read_persisted_master_list_dir,
    save_master_list_dir,
)


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


def test_url_is_a_supported_entity_with_an_auto_prefix():
    # Websites are detected in Word/Excel via Presidio's built-in UrlRecognizer
    # (already loaded by default) and in PDF via the spaCy-free
    # PatternDetector - both need "URL" present in both collections.
    assert "URL" in DEFAULT_SETTINGS.supported_entities
    assert DEFAULT_SETTINGS.auto_prefixes["URL"] == "URL"


def test_no_persisted_setting_returns_none(monkeypatch):
    monkeypatch.delenv("FPR_MASTER_LIST_DIR", raising=False)

    assert read_persisted_master_list_dir() is None


def test_save_then_read_persisted_master_list_dir(tmp_path):
    shared = tmp_path / "Box" / "Team" / "Master List Folder"

    save_master_list_dir(shared)

    assert read_persisted_master_list_dir() == shared


def test_persisted_setting_survives_unrelated_future_keys(tmp_path):
    # Saving must not clobber other keys a future version might add to the
    # same settings file.
    save_master_list_dir(tmp_path / "first")
    settings_file = Path.home() / ".finance_pii_redactor" / "settings.json"
    data = json.loads(settings_file.read_text(encoding="utf-8"))
    data["some_future_setting"] = "keep me"
    settings_file.write_text(json.dumps(data), encoding="utf-8")

    save_master_list_dir(tmp_path / "second")

    data = json.loads(settings_file.read_text(encoding="utf-8"))
    assert data["some_future_setting"] == "keep me"
    assert data["master_list_dir"] == str(tmp_path / "second")


def test_a_corrupt_settings_file_is_treated_as_absent(monkeypatch):
    monkeypatch.delenv("FPR_MASTER_LIST_DIR", raising=False)
    settings_file = Path.home() / ".finance_pii_redactor" / "settings.json"
    settings_file.parent.mkdir(parents=True)
    settings_file.write_text("{not valid json", encoding="utf-8")

    assert read_persisted_master_list_dir() is None
    assert _resolve_data_dir() == Path(__file__).parent.parent / "data"


def test_persisted_setting_wins_over_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv("FPR_MASTER_LIST_DIR", str(tmp_path / "env-folder"))
    save_master_list_dir(tmp_path / "persisted-folder")

    assert _resolve_data_dir() == tmp_path / "persisted-folder"


def test_current_settings_reflects_a_persisted_change_without_reimport(tmp_path):
    # Simulates Streamlit's rerun model: the module is imported once, but
    # current_settings() must notice a save() that happens later in the
    # same process.
    before = current_settings()
    assert before.names_dir == DEFAULT_SETTINGS.names_dir

    save_master_list_dir(tmp_path / "newly-configured")

    after = current_settings()
    assert after.names_dir == tmp_path / "newly-configured"
    # DEFAULT_SETTINGS itself is frozen at import time and must not change.
    assert DEFAULT_SETTINGS.names_dir == before.names_dir
