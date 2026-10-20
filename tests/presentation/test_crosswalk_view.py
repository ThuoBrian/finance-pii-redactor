"""Tests for the PDF mapping section: the names file is opt-in and off by default."""

from __future__ import annotations

from streamlit.testing.v1 import AppTest


def _section() -> None:
    from finance_redactor.domain.pseudonyms import Assignment
    from finance_redactor.presentation.crosswalk_view import render_pdf_mapping_section

    render_pdf_mapping_section(
        [
            Assignment(
                original_name="Zzyzx Qwertyson",
                entity_type="PERSON",
                category="Staff",
                pseudonym="STF-17728",
                auto=False,
                ordinal=1,
                internal_id="17728",
            )
        ],
        "redacted-20261020-1405",
        master_list_fingerprint="list@1",
    )


def _downloads(at: AppTest) -> list[str]:
    return [element.proto.label for element in at.get("download_button")]


def test_only_the_names_free_download_is_offered_by_default() -> None:
    at = AppTest.from_function(_section, default_timeout=30).run()

    assert not at.exception
    assert _downloads(at) == ["Download label mapping (CSV, no names)"]
    assert at.toggle[0].value is False


def test_turning_the_toggle_on_adds_a_confidential_download_and_warning() -> None:
    at = AppTest.from_function(_section, default_timeout=30).run()

    at.toggle[0].set_value(True).run()

    assert not at.exception
    assert _downloads(at) == [
        "Download label mapping (CSV, no names)",
        "Download name mapping (CSV, Confidential)",
    ]
    assert any("Confidential" in warning.value for warning in at.warning)
