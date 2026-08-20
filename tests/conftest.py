"""Shared test fixtures.

``autouse`` so every test gets it automatically, with no per-test opt-in.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    """Point ``Path.home()`` at a throwaway directory for every test.

    ``finance_redactor.config`` persists the in-app "Set up shared master
    list" dialog's choice to ``Path.home() / ".finance_pii_redactor" /
    "settings.json"``. Without this fixture, running the test suite on a
    real machine that has ever used that dialog (or ever will) would read
    and could overwrite that real file - tests must never touch a
    developer's actual home directory, especially one that might contain a
    path to a real, Confidential master-list location.
    """
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
