"""Unit tests for the step tracker's pure text helper."""

from __future__ import annotations

from finance_redactor.presentation.steps import steps_markdown


def test_first_step_is_current_and_the_rest_are_upcoming():
    assert steps_markdown(1) == (
        "🔵 **1. Upload** → ⚪ 2. Set options → ⚪ 3. Review → ⚪ 4. Download"
    )


def test_last_step_marks_every_earlier_step_done():
    assert steps_markdown(4) == (
        "✅ 1. Upload → ✅ 2. Set options → ✅ 3. Review → 🔵 **4. Download**"
    )
