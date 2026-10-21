"""Tests for the PDF mapping downloads: the names file is opt-in and off by default."""

from __future__ import annotations

from streamlit.testing.v1 import AppTest


def _downloads_section() -> None:
    from finance_redactor.domain.pseudonyms import Assignment
    from finance_redactor.presentation.crosswalk_view import (
        render_pdf_mapping_download,
        render_pdf_names_download,
    )

    crosswalk = [
        Assignment(
            original_name="Zzyzx Qwertyson",
            entity_type="PERSON",
            category="Staff",
            pseudonym="STF-17728",
            auto=False,
            ordinal=1,
            internal_id="17728",
        )
    ]
    render_pdf_mapping_download(crosswalk, "redacted-20261020-1405", "list@1")
    render_pdf_names_download(crosswalk, "redacted-20261020-1405", "list@1")


def _downloads(at: AppTest) -> list[str]:
    return [element.proto.label for element in at.get("download_button")]


def test_only_the_names_free_download_is_offered_by_default() -> None:
    at = AppTest.from_function(_downloads_section, default_timeout=30).run()

    assert not at.exception
    assert _downloads(at) == ["Download label mapping (CSV, no names)"]
    assert at.toggle[0].value is False


def test_turning_the_toggle_on_adds_the_names_download_and_its_warning() -> None:
    at = AppTest.from_function(_downloads_section, default_timeout=30).run()

    at.toggle[0].set_value(True).run()

    assert not at.exception
    assert _downloads(at) == [
        "Download label mapping (CSV, no names)",
        "Download name mapping (CSV)",
    ]
    assert any("re-identify everyone" in c.value for c in at.caption)


def _undecodable_items() -> None:
    from finance_redactor.domain.pseudonyms import Assignment
    from finance_redactor.presentation.crosswalk_view import (
        render_pdf_mapping_warnings,
    )

    render_pdf_mapping_warnings(
        [
            Assignment(
                original_name="Zzyzx Qwertyson",
                entity_type="PERSON",
                category="",
                pseudonym="PSN-AUTO-1A2B3",
                auto=True,
                ordinal=1,
                internal_id=None,
            )
        ]
    )


def test_undecodable_items_are_information_not_a_warning() -> None:
    """They were still redacted, so nothing shows; yellow is for what shows."""
    at = AppTest.from_function(_undecodable_items, default_timeout=30).run()

    assert not at.exception
    assert any("Not in the master list" in i.value for i in at.info)
    assert not at.warning
