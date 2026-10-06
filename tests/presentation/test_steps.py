"""Unit tests for the step tracker's pure text helper."""

from __future__ import annotations

from finance_redactor.presentation.steps import steps_markdown


def test_first_step_is_active_and_the_rest_are_upcoming():
    assert steps_markdown(1) == (
        ":blue-badge[:material/arrow_forward: 1. Upload] "
        ":gray-badge[2. Set options] :gray-badge[3. Review] :gray-badge[4. Download]"
    )


def test_last_step_marks_every_earlier_step_done():
    assert steps_markdown(4) == (
        ":green-badge[:material/check: 1. Upload] "
        ":green-badge[:material/check: 2. Set options] "
        ":green-badge[:material/check: 3. Review] "
        ":blue-badge[:material/arrow_forward: 4. Download]"
    )
