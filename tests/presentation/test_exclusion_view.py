"""AppTest checks for the review editor's layout: search, clean run, Apply."""

from __future__ import annotations

from streamlit.testing.v1 import AppTest


def _editor(clean: bool = False) -> None:
    import streamlit as st

    from finance_redactor.domain.entities import DetectionSource, Finding
    from finance_redactor.presentation.exclusion_view import render_deselect_editor

    def finding(text: str, source: DetectionSource) -> Finding:
        return Finding(
            page=0,
            detected_text=text,
            entity_type="ORGANIZATION",
            score=0.85,
            source=source,
        )

    findings = [finding("Care Organisation", DetectionSource.MASTER_LIST)]
    if not clean:
        findings += [
            finding("Jane Doe", DetectionSource.MODEL),
            finding("Salaries", DetectionSource.MODEL),
        ]
    applied = st.session_state.get("applied", frozenset())
    result = render_deselect_editor(findings, key_prefix="t", excluded=applied)
    if result != applied:  # what the flows do: rebuild, then rerun
        st.session_state.applied = result
        st.rerun()


def _run(clean: bool = False) -> AppTest:
    return AppTest.from_function(
        _editor, kwargs={"clean": clean}, default_timeout=30
    ).run()


def _apply_buttons(at: AppTest) -> list[str]:
    return [b.label for b in at.button if b.label.startswith("Apply changes")]


def _press(at: AppTest, prefix: str) -> None:
    next(b for b in at.button if b.label.startswith(prefix)).click()
    at.run()


def test_there_is_exactly_one_apply_button() -> None:
    at = _run()

    assert not at.exception
    assert _apply_buttons(at) == ["Apply changes"]


def test_search_narrows_the_rows_and_a_hidden_untick_survives() -> None:
    at = _run()

    at.text_input[0].set_value("jane").run()
    _press(at, "Untick all shown (1)")
    at.text_input[0].set_value("").run()

    assert not at.exception
    assert _apply_buttons(at) == ["Apply changes (1 pending)"]
    assert any("1 change not applied yet" in c.value for c in at.caption)


def test_a_clean_run_says_so_and_folds_the_table_away() -> None:
    at = _run(clean=True)

    assert not at.exception
    assert any("Nothing here is a guess" in s.value for s in at.success)
    assert [e.label for e in at.expander] == ["How to read this table", "Review anyway"]


def test_apply_confirms_once_and_then_the_notice_goes() -> None:
    at = _run()
    _press(at, "Untick all shown (3)")

    _press(at, "Apply changes (3 pending)")

    assert not at.exception
    notices = [s.value for s in at.success if s.value.startswith("Rebuilt the file")]
    assert notices == [
        "Rebuilt the file. 3 terms are left visible; they are listed above the download."
    ]
    at.run()
    assert not [s for s in at.success if s.value.startswith("Rebuilt the file")]
