"""Tests for the neutral download name."""

from __future__ import annotations

from datetime import datetime

from finance_redactor.presentation.session import neutral_stem


def test_neutral_stem_is_the_date_and_time_and_nothing_from_the_upload() -> None:
    assert neutral_stem(datetime(2026, 10, 20, 14, 5)) == "redacted-20261020-1405"


def test_neutral_stem_is_safe_in_a_file_name() -> None:
    stem = neutral_stem(datetime(2026, 1, 2, 3, 4))

    assert stem == "redacted-20260102-0304"
    assert all(ch.isalnum() or ch == "-" for ch in stem)
