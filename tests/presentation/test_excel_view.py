"""Excel flow through the wizard, driven with Streamlit's AppTest.

Made-up data and a fake detector that flags "Jane Doe", so no language model
is loaded. Each test builds its own workbook from ``tabs``: tab name to
``{header: column values}``.
"""

from __future__ import annotations

import zipfile
from io import BytesIO

from streamlit.testing.v1 import AppTest


def _flow(tabs: dict[str, dict[str, list[object]]]) -> None:
    import re
    from io import BytesIO

    import pandas as pd
    import streamlit as st

    from finance_redactor.application.redact_excel import RedactExcelService
    from finance_redactor.config import DEFAULT_SETTINGS as S
    from finance_redactor.domain.entities import DetectionSource, PiiDetection, Span
    from finance_redactor.infrastructure.documents.excel_gateway import (
        OpenpyxlExcelGateway,
    )
    from finance_redactor.presentation import wizard
    from finance_redactor.presentation.excel_view import run_excel_flow

    class Detector:
        def analyze(self, text, entities, threshold):
            return [
                PiiDetection(
                    entity_type="PERSON",
                    span=Span(m.start(), m.end()),
                    score=0.85,
                    text=m.group(),
                    source=DetectionSource.MODEL,
                )
                for m in re.finditer(r"Jane Doe", text)
            ]

    wizard.keep_option_choices()
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, columns in tabs.items():
            pd.DataFrame(columns).to_excel(writer, index=False, sheet_name=name)
    buffer.seek(0)
    buffer.name = "made_up.xlsx"
    service = RedactExcelService(
        Detector(),
        master_map={},
        auto_prefixes=S.auto_prefixes,
        fixed_masks=S.fixed_masks,
    )
    run_excel_flow(
        buffer,
        excel_service=service,
        excel_gateway=OpenpyxlExcelGateway(),
        settings=S,
        steps=st.empty(),
    )


def _start(tabs: dict[str, dict[str, list[object]]]) -> AppTest:
    at = AppTest.from_function(_flow, kwargs={"tabs": tabs}, default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    return at


def _click(at: AppTest, label: str) -> None:
    next(b for b in at.button if b.label == label).click()
    at.run()
    assert not at.exception, at.exception


def _to_download(at: AppTest) -> None:
    _click(at, "Redact my file")
    _click(at, "Continue to download →")


def _xml(data: bytes) -> bytes:
    with zipfile.ZipFile(BytesIO(data)) as archive:
        return b"".join(archive.read(n) for n in archive.namelist())


def test_a_name_in_a_column_header_does_not_reach_the_download() -> None:
    at = _start({"Payments": {"Jane Doe": [100, 200], "notes": ["ok", "fine"]}})
    _to_download(at)

    assert b"Jane Doe" not in _xml(at.session_state["excel_bytes"])


def test_the_threshold_slider_stops_at_the_master_list_score() -> None:
    """Above 0.90 every master-list match is dropped; the slider can't go there."""
    from finance_redactor.config import DEFAULT_SETTINGS

    at = _start({"Payments": {"notes": ["ok"]}})
    slider = at.slider(key="excel_threshold")

    assert slider.max == DEFAULT_SETTINGS.custom_match_score == 0.9
    assert slider.value == DEFAULT_SETTINGS.default_threshold


def test_name_summary_lists_the_first_names_then_a_count() -> None:
    from finance_redactor.presentation.excel_view import name_summary

    assert name_summary(["Jan"]) == "Jan"
    assert name_summary(["Jan", "Feb"]) == "Jan, Feb"
    assert name_summary(["Jan", "Feb", "Mar"]) == "Jan, Feb + 1 more"
    assert name_summary([f"T{n}" for n in range(12)]) == "T0, T1 + 10 more"


_THREE_TABS: dict[str, dict[str, list[object]]] = {
    "Jan": {"notes": ["Paid Jane Doe"], "memo": ["ok"]},
    "Feb": {"notes": ["Paid Jane Doe"], "memo": ["ok"]},
    "Mar": {"notes": ["ok"], "memo": ["ok"]},
}


def test_one_column_picker_serves_every_tab() -> None:
    at = _start(_THREE_TABS)

    assert [s.label for s in at.selectbox] == ["Which tab's columns?"]
    assert [m.label for m in at.multiselect].count("Columns to scan") == 1
    caption = next(c.value for c in at.caption if "3 tabs" in c.value)
    assert "(Jan, Feb + 1 more)" in caption


def test_column_choices_stay_with_their_tab_and_reach_the_scan() -> None:
    at = _start(_THREE_TABS)
    at.multiselect(key="excel_cols_Jan").set_value(["memo"]).run()
    at.selectbox[0].set_value("Feb").run()
    assert at.multiselect(key="excel_cols_Feb").value == ["notes", "memo"]
    at.selectbox[0].set_value("Jan").run()
    assert at.multiselect(key="excel_cols_Jan").value == ["memo"]

    _click(at, "Redact my file")

    assert at.session_state["scan_columns"] == {
        "Jan": ["memo"],
        "Feb": ["notes", "memo"],
        "Mar": ["notes", "memo"],
    }
    # Jan's "notes" was left out, so only Feb's cell is a finding.
    assert at.session_state["findings"].cell_count == 1


def _shown_text(at: AppTest) -> str:
    """Every cell of the one preview table, as text.

    Preview tables are the ones whose changed cells carry the » marker; the
    other tabs hold tables too. Exactly one must be on the page.
    """
    texts = [
        " ".join(str(v) for v in table.value.to_numpy().ravel())
        for table in at.dataframe
    ]
    (preview,) = [t for t in texts if "»" in t]
    return preview


def test_preview_shows_one_table_and_the_toggle_switches_it() -> None:
    at = _start({"Payments": {"notes": ["Paid Jane Doe", "ok"]}})
    _click(at, "Redact my file")

    assert "Jane Doe" not in _shown_text(at)  # redacted by default

    at.toggle(key="excel_preview_original").set_value(True).run()
    assert not at.exception, at.exception
    assert "Jane Doe" in _shown_text(at)  # switched, not stacked


def test_a_long_tab_says_what_the_preview_hides_and_pages_through_it() -> None:
    notes: list[object] = ["ok"] * 1203
    notes[0] = notes[1100] = "Paid Jane Doe"
    at = _start({"Payments": {"notes": notes}})
    _click(at, "Redact my file")

    (note,) = [m.value for m in at.info if "rows are not on screen" in m.value]
    assert "1,203 rows" in note
    assert "rows 1 to 500" in note
    assert "703 rows are not on screen" in note
    assert "1 highlighted cell among them" in note
    assert "The download has every row" in note
    assert _shown_text(at).count("»") == 1  # row 1 only

    at.selectbox(key="excel_preview_rows_0").set_value(1000).run()
    assert not at.exception, at.exception
    (note,) = [m.value for m in at.info if "rows are not on screen" in m.value]
    assert "rows 1,001 to 1,203" in note
    assert "1,000 rows are not on screen" in note
    assert _shown_text(at).count("»") == 1  # row 1,101, now on screen
    (table,) = [t for t in at.dataframe if "»" in str(t.value.to_numpy())]
    assert len(table.value) == 203


def _downloads(at: AppTest) -> list[str]:
    return [element.proto.label for element in at.get("download_button")]


def test_a_workbook_with_nothing_found_can_still_be_downloaded() -> None:
    at = _start({"Payments": {"notes": ["ok", "fine"]}})
    _to_download(at)

    assert any("Nothing was detected" in m.value for m in at.info)
    assert _downloads(at) == ["Download redacted workbook"]
    assert at.session_state["excel_bytes"]
