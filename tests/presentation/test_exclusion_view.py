"""AppTest checks for the review editor: search, clean run, ticks, Apply."""

from __future__ import annotations

from streamlit.testing.v1 import AppTest


def _editor(clean: bool = False, fake_clicks: bool = False, long: bool = True) -> None:
    from contextlib import nullcontext
    from typing import Any
    from unittest.mock import patch

    import pandas as pd
    import streamlit as st

    from finance_redactor.domain.entities import DetectionSource, Finding
    from finance_redactor.presentation.exclusion_view import render_deselect_editor
    from finance_redactor.presentation.presenters import REDACT_COLUMN

    state = st.session_state

    def fake_editor(data: pd.DataFrame, *, key: str, **_: Any) -> pd.DataFrame:
        # AppTest cannot click inside a data_editor, so this stands in for
        # one. Like the real widget, it is a new widget whenever its input
        # data changes, and its edits so far - including the click that
        # caused this run - are lost.
        edits = [*state.get("fake_edits", []), *state.pop("fake_click", [])]
        identity = (key, data.to_json())
        if state.get("fake_identity") != identity:
            state.fake_identity, edits = identity, []
        state.fake_edits = edits
        edited = data.copy()
        for term in edits:
            row = edited["Detected text"] == term
            edited.loc[row, REDACT_COLUMN] = ~edited.loc[row, REDACT_COLUMN]
        return edited

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
    if long:  # past one screen of rows, so the filter and bulk buttons show
        findings += [
            finding(f"Filler Name {n:02d}", DetectionSource.MASTER_LIST)
            for n in range(1, 13)
        ]
    applied = st.session_state.get("applied", frozenset())
    fake = patch.object(st, "data_editor", fake_editor) if fake_clicks else None
    with fake or nullcontext():
        result = render_deselect_editor(findings, key_prefix="t", excluded=applied)
    if result != applied:  # what the flows do: rebuild, then rerun
        st.session_state.applied = result
        st.rerun()


def _run(clean: bool = False, long: bool = True) -> AppTest:
    return AppTest.from_function(
        _editor, kwargs={"clean": clean, "long": long}, default_timeout=30
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
    assert [e.label for e in at.expander] == ["Review anyway"]


def test_apply_confirms_once_and_then_the_notice_goes() -> None:
    at = _run()
    _press(at, "Untick all shown (15)")

    _press(at, "Apply changes (15 pending)")

    assert not at.exception
    notices = [s.value for s in at.success if s.value.startswith("Rebuilt the file")]
    assert notices == [
        "Rebuilt the file. 15 terms are left visible; they are listed above the download."
    ]
    at.run()
    assert not [s for s in at.success if s.value.startswith("Rebuilt the file")]


def test_each_single_click_on_a_tick_box_counts() -> None:
    at = AppTest.from_function(
        _editor, kwargs={"fake_clicks": True}, default_timeout=30
    ).run()

    for term in ("Jane Doe", "Salaries"):
        at.session_state["fake_click"] = [term]
        at.run()

    assert not at.exception
    assert _apply_buttons(at) == ["Apply changes (2 pending)"]


def test_a_short_list_has_no_filter_search_or_bulk_buttons() -> None:
    at = _run(long=False)

    assert not at.exception
    assert not at.text_input
    assert not [b for b in at.button if "all shown" in b.label]
    assert [t.label for t in at.toggle] == ["Show details"]


def test_show_details_keeps_pending_ticks() -> None:
    at = _run()
    _press(at, "Untick all shown (15)")

    at.toggle[0].set_value(True).run()

    assert not at.exception
    assert _apply_buttons(at) == ["Apply changes (15 pending)"]
