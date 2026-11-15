"""Tests for the neutral download name."""

from __future__ import annotations

from datetime import datetime

from streamlit.testing.v1 import AppTest

from finance_redactor.presentation.session import neutral_stem, upload_identity


def test_neutral_stem_is_the_date_and_time_and_nothing_from_the_upload() -> None:
    assert neutral_stem(datetime(2026, 10, 20, 14, 5)) == "redacted-20261020-1405"


def test_neutral_stem_is_safe_in_a_file_name() -> None:
    stem = neutral_stem(datetime(2026, 1, 2, 3, 4))

    assert stem == "redacted-20260102-0304"
    assert all(ch.isalnum() or ch == "-" for ch in stem)


def _upload_script() -> None:
    from io import BytesIO

    import streamlit as st

    from finance_redactor.presentation.session import reset_on_new_upload

    buffer = BytesIO(st.session_state.get("payload", b"first version"))
    buffer.name = st.session_state.get("upload_name", "made_up.pdf")
    if reset_on_new_upload(buffer, "pdf", ("cached_result",)):
        st.session_state["resets"] = st.session_state.get("resets", 0) + 1
    st.session_state.setdefault("cached_result", "built")


def _upload_app() -> AppTest:
    return AppTest.from_function(_upload_script).run()


def test_the_same_file_again_keeps_its_results() -> None:
    at = _upload_app()
    at.run()

    assert at.session_state["resets"] == 1


def test_same_name_with_different_bytes_starts_again() -> None:
    at = _upload_app()
    at.session_state["cached_result"] = "built from the first version"

    at.session_state["payload"] = b"edited version"
    at.run()

    assert at.session_state["resets"] == 2
    assert at.session_state["cached_result"] == "built"


def test_same_size_and_name_but_different_bytes_starts_again() -> None:
    at = _upload_app()

    at.session_state["payload"] = b"FIRST VERSION"  # same length, other bytes
    at.run()

    assert at.session_state["resets"] == 2


def test_upload_identity_holds_no_file_content() -> None:
    from io import BytesIO

    buffer = BytesIO(b"Jane Test paid")
    buffer.name = "made_up.pdf"

    name, size, digest = upload_identity(buffer)

    assert (name, size) == ("made_up.pdf", 14)
    assert "Jane" not in digest and len(digest) == 64
