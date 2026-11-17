"""Excel through the web API: options, scan, review, apply, preview, download.

Real use case and Excel gateway, fake detector (see api_fakes). All names
are made up.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from api_fakes import HEADERS, make_client
from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook

TABS: dict[str, list[list[object]]] = {
    "Jan": [
        ["Payee", "Amount", "Notes"],
        ["Jane Doe", 100, "salaries for Jane Doe"],
        ["Acme Widgets", 50, None],
    ],
    "Feb": [["Item"], ["stationery"]],
}


def workbook(tabs: dict[str, list[list[object]]] = TABS) -> bytes:
    """Return xlsx bytes with one sheet per tab, first row as headers."""
    book = Workbook()
    book.remove(book.active)
    for name, rows in tabs.items():
        sheet = book.create_sheet(name)
        for row in rows:
            sheet.append(row)
    out = BytesIO()
    book.save(out)
    return out.getvalue()


def start(tmp_path: Path, data: bytes | None = None):
    """Upload the workbook; return ``(client, fake, job id)``."""
    client, fake = make_client(tmp_path)
    response = client.post(
        "/api/jobs",
        files={"file": ("payroll.xlsx", data or workbook())},
        headers=HEADERS,
    )
    assert response.status_code == 201
    return client, fake, response.json()["id"]


def scan(client: TestClient, job_id: str, **overrides) -> None:
    """Scan with defaults (Jan, Payee and Notes, people and organizations)."""
    body = {
        "tabs": ["Jan"],
        "columns": {"Jan": [0, 2]},
        "entities": ["PERSON", "ORGANIZATION"],
        "threshold": 0.35,
        **overrides,
    }
    response = client.post(f"/api/jobs/{job_id}/excel/scan", json=body, headers=HEADERS)
    assert response.status_code == 202, response.text
    status = client.get(f"/api/jobs/{job_id}", headers=HEADERS).json()["task"]
    assert status["status"] == "done", status


def get(client: TestClient, path: str):
    """GET with the client header."""
    return client.get(path, headers=HEADERS)


def test_options_pick_text_columns(tmp_path: Path) -> None:
    client, _, job_id = start(tmp_path)
    body = get(client, f"/api/jobs/{job_id}/excel/options").json()
    jan = body["tabs"][0]
    assert jan["name"] == "Jan"
    assert jan["columns"] == ["Payee", "Amount", "Notes"]
    assert jan["default_columns"] == [0, 2]
    assert body["threshold"]["max"] == 0.85
    assert body["summary"].startswith("2 tabs (Jan, Feb)")
    assert {"code": "PERSON", "label": "Person"} in body["entities"]


def test_unreadable_workbook(tmp_path: Path) -> None:
    client, _, job_id = start(tmp_path, data=b"PK\x03\x04 not really a workbook")
    response = get(client, f"/api/jobs/{job_id}/excel/options")
    assert response.status_code == 422
    assert "could not be read" in response.json()["detail"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"tabs": []},
        {"tabs": ["Nope"]},
        {"columns": {"Jan": []}},
        {"columns": {"Jan": [9]}},
        {"threshold": 0.9},
        {"entities": []},
        {"entities": ["PASSWORD"]},
    ],
)
def test_scan_refuses_bad_choices(tmp_path: Path, overrides: dict) -> None:
    client, _, job_id = start(tmp_path)
    body = {
        "tabs": ["Jan"],
        "columns": {"Jan": [0]},
        "entities": ["PERSON"],
        "threshold": 0.35,
        **overrides,
    }
    response = client.post(f"/api/jobs/{job_id}/excel/scan", json=body, headers=HEADERS)
    assert response.status_code == 422


def test_estimate_is_quiet_for_a_small_workbook(tmp_path: Path) -> None:
    client, _, job_id = start(tmp_path)
    response = client.post(
        f"/api/jobs/{job_id}/excel/estimate",
        json={"tabs": ["Jan"], "columns": {"Jan": [0]}},
        headers=HEADERS,
    )
    assert response.json() == {"warning": None}


def test_review_lists_terms_guesses_first(tmp_path: Path) -> None:
    client, _, job_id = start(tmp_path)
    scan(client, job_id)
    body = get(client, f"/api/jobs/{job_id}/excel/review").json()
    terms = [r["term"] for r in body["rows"]]
    assert set(terms) == {"Jane Doe", "Acme Widgets", "salaries"}
    assert terms[-1] == "Jane Doe"  # curated names last
    assert body["applied"] == []
    assert body["clean"] is False
    assert {f["label"] for f in body["filters"]} == {"Model guesses", "Master list"}
    assert {m["original_name"] for m in body["mapping"]} == {
        "Jane Doe",
        "Acme Widgets",
        "salaries",
    }
    assert body["tabs"] == ["Jan"]
    assert any(o["row"] == 1 and o["column"] == "Payee" for o in body["occurrences"])


def test_apply_leaves_a_term_visible_and_download_matches(tmp_path: Path) -> None:
    client, _, job_id = start(tmp_path)
    scan(client, job_id)
    rows = get(client, f"/api/jobs/{job_id}/excel/review").json()["rows"]
    key = next(r["key"] for r in rows if r["term"] == "salaries")
    applied = client.post(
        f"/api/jobs/{job_id}/excel/apply", json={"excluded": [key]}, headers=HEADERS
    ).json()
    assert applied["applied"] == [key]
    assert "salaries" not in {m["original_name"] for m in applied["mapping"]}

    response = get(client, f"/api/jobs/{job_id}/files/redacted")
    assert response.status_code == 200
    disposition = response.headers["Content-Disposition"]
    assert 'filename="redacted-' in disposition
    assert "payroll" not in disposition
    sheet = load_workbook(BytesIO(response.content))["Jan"]
    values = [c.value for row in sheet.iter_rows() for c in row]
    assert "Jane Doe" not in " ".join(str(v) for v in values)
    assert any("salaries" in str(v) for v in values)

    info = get(client, f"/api/jobs/{job_id}/excel/download").json()
    assert info["excluded"] == [key]
    assert info["left_out"] == ["Feb"]
    assert info["has_mapping"] is True

    csv = get(client, f"/api/jobs/{job_id}/files/crosswalk")
    assert csv.headers["content-type"].startswith("text/csv")
    assert "Jane Doe" in csv.text
    assert "_crosswalk.csv" in csv.headers["Content-Disposition"]


def test_apply_refuses_a_term_the_scan_did_not_find(tmp_path: Path) -> None:
    client, _, job_id = start(tmp_path)
    scan(client, job_id)
    response = client.post(
        f"/api/jobs/{job_id}/excel/apply",
        json={"excluded": ["never found"]},
        headers=HEADERS,
    )
    assert response.status_code == 409


def test_unticked_terms_carry_over_to_a_new_scan(tmp_path: Path) -> None:
    client, _, job_id = start(tmp_path)
    scan(client, job_id)
    rows = get(client, f"/api/jobs/{job_id}/excel/review").json()["rows"]
    key = next(r["key"] for r in rows if r["term"] == "salaries")
    client.post(
        f"/api/jobs/{job_id}/excel/apply", json={"excluded": [key]}, headers=HEADERS
    )
    scan(client, job_id)
    body = get(client, f"/api/jobs/{job_id}/excel/review").json()
    assert body["applied"] == [key]
    assert body["carried"] == [key]


def test_preview_marks_changed_cells(tmp_path: Path) -> None:
    client, _, job_id = start(tmp_path)
    scan(client, job_id)
    body = get(client, f"/api/jobs/{job_id}/excel/preview?tab=0").json()
    assert body["total_rows"] == 2
    assert body["original_rows"][0][0] == "Jane Doe"
    assert body["rows"][0][0] != "Jane Doe"
    assert body["rows"][1][2] == ""  # an empty cell stays blank, not "nan"
    assert [0, 0] in body["marked"]
    assert [0, 1] not in body["marked"]  # Amount was not scanned
    assert body["elsewhere"] == 0
    assert get(client, f"/api/jobs/{job_id}/excel/preview?tab=5").status_code == 422


def test_nothing_found_still_downloads_and_has_no_mapping(tmp_path: Path) -> None:
    client, _, job_id = start(tmp_path)
    scan(client, job_id, columns={"Jan": [1]})
    info = get(client, f"/api/jobs/{job_id}/excel/download").json()
    assert info["nothing_found"] is True
    assert info["has_mapping"] is False
    assert get(client, f"/api/jobs/{job_id}/files/redacted").status_code == 200
    assert get(client, f"/api/jobs/{job_id}/files/crosswalk").status_code == 404


def test_review_before_scan_is_refused(tmp_path: Path) -> None:
    client, _, job_id = start(tmp_path)
    assert get(client, f"/api/jobs/{job_id}/excel/review").status_code == 409
    assert get(client, f"/api/jobs/{job_id}/files/redacted").status_code == 409


def test_excel_routes_refuse_another_format(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)
    job_id = client.post(
        "/api/jobs", files={"file": ("a.pdf", b"%PDF-1")}, headers=HEADERS
    ).json()["id"]
    assert get(client, f"/api/jobs/{job_id}/excel/options").status_code == 404
    # The PDF route answers for a PDF upload: not scanned yet.
    assert get(client, f"/api/jobs/{job_id}/files/redacted").status_code == 409


def test_busy_job_is_refused(tmp_path: Path) -> None:
    client, fake, job_id = start(tmp_path)
    fake.jobs.get(job_id).task.status = "running"
    assert get(client, f"/api/jobs/{job_id}/excel/options").status_code == 409


def test_failed_scan_reports_a_generic_error(tmp_path: Path, caplog) -> None:
    client, fake, job_id = start(tmp_path)

    def boom():
        raise RuntimeError("Jane Doe broke it")

    fake.excel_service = boom  # type: ignore[method-assign]
    client.post(
        f"/api/jobs/{job_id}/excel/scan",
        json={
            "tabs": ["Jan"],
            "columns": {"Jan": [0]},
            "entities": ["PERSON"],
            "threshold": 0.35,
        },
        headers=HEADERS,
    )
    task = get(client, f"/api/jobs/{job_id}").json()["task"]
    assert task["status"] == "error"
    assert "Jane Doe" not in task["error"]
    assert "Jane Doe" not in caplog.text
    assert "RuntimeError" in caplog.text


def test_unknown_job_status_is_404(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)
    assert get(client, "/api/jobs/nope").status_code == 404


def test_occurrences_link_to_review_rows_and_say_where_they_are(tmp_path: Path) -> None:
    data = workbook({"Acme Widgets": [["Jane Doe", "Notes"], ["x", "salaries"]]})
    client, _, job_id = start(tmp_path, data=data)
    scan(client, job_id, tabs=["Acme Widgets"], columns={"Acme Widgets": [1]})
    body = get(client, f"/api/jobs/{job_id}/excel/review").json()
    keys = {r["key"] for r in body["rows"]}
    assert {o["key"] for o in body["occurrences"]} <= keys
    places = {(o["place"], o["column_name"], o["term"]) for o in body["occurrences"]}
    assert ("tab", "", "Acme Widgets") in places
    assert ("header", "Jane Doe", "Jane Doe") in places
    assert ("cell", "Notes", "salaries") in places


def test_cancelled_scan_keeps_the_previous_result(tmp_path: Path) -> None:
    client, fake, job_id = start(tmp_path)
    scan(client, job_id)
    before = get(client, f"/api/jobs/{job_id}/excel/review").json()

    def cancel_now() -> None:
        assert client.post(f"/api/jobs/{job_id}/cancel", headers=HEADERS).json() == {
            "cancelling": True
        }

    fake.on_analyze = cancel_now
    client.post(
        f"/api/jobs/{job_id}/excel/scan",
        json={
            "tabs": ["Jan"],
            "columns": {"Jan": [0]},
            "entities": ["PERSON"],
            "threshold": 0.35,
        },
        headers=HEADERS,
    )
    task = get(client, f"/api/jobs/{job_id}").json()["task"]
    assert task["status"] == "cancelled"
    assert get(client, f"/api/jobs/{job_id}/excel/review").json() == before


def test_cancel_when_idle_or_unknown(tmp_path: Path) -> None:
    client, _, job_id = start(tmp_path)
    response = client.post(f"/api/jobs/{job_id}/cancel", headers=HEADERS)
    assert response.json() == {"cancelling": False}
    assert client.post("/api/jobs/nope/cancel", headers=HEADERS).status_code == 404
