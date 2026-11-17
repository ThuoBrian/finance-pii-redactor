"""The app follows each person's light or dark preference (no forced theme)."""

from __future__ import annotations

import tomllib
from pathlib import Path

_CONFIG = Path(__file__).parent.parent / ".streamlit" / "config.toml"


def test_no_theme_is_forced_and_both_keep_the_accent() -> None:
    theme = tomllib.loads(_CONFIG.read_text(encoding="utf-8"))["theme"]

    assert "base" not in theme
    assert theme["light"]["primaryColor"] == theme["dark"]["primaryColor"] == "#2563EB"


def test_usage_statistics_stay_off() -> None:
    config = tomllib.loads(_CONFIG.read_text(encoding="utf-8"))

    assert config["browser"]["gatherUsageStats"] is False
