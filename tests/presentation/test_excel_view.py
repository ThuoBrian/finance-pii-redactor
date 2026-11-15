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
