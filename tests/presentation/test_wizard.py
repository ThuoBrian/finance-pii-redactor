"""Start over asks first: it throws away the findings and the review."""

from __future__ import annotations

from streamlit.testing.v1 import AppTest


def _script() -> None:
    import streamlit as st

    from finance_redactor.presentation import wizard

    with st.sidebar:
        wizard.render_start_over()


def _app_with_results() -> AppTest:
    at = AppTest.from_function(_script).run()
    at.session_state["pdf_buffer"] = b"made-up redacted file"
    return at


def _click(at: AppTest, label: str) -> None:
    next(b for b in at.button if b.label == label).click()
    at.run()
    # The click reruns mid-run, and AppTest keeps a stale copy of the
    # elements from before it; one more run gives a clean tree.
    at.run()
    assert not at.exception, at.exception


def test_start_over_asks_before_clearing_anything() -> None:
    at = _app_with_results()

    _click(at, "Start over")

    assert at.session_state["pdf_buffer"] == b"made-up redacted file"
    warning = at.warning[0].value
    assert "findings" in warning and "downloads" in warning


def test_confirming_start_over_clears_the_results() -> None:
    at = _app_with_results()
    _click(at, "Start over")

    _click(at, "Yes, start over")

    assert "pdf_buffer" not in at.session_state
    assert at.session_state["wizard_step"] == 1


def test_cancel_keeps_the_results_and_the_button() -> None:
    at = _app_with_results()
    _click(at, "Start over")

    _click(at, "Cancel")

    assert at.session_state["pdf_buffer"] == b"made-up redacted file"
    assert not at.warning
    assert [b.label for b in at.button] == ["Start over"]
