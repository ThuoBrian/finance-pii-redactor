"""The web API's skeleton: guard, master list, upload, start over, shutdown.

Uses a fake context, so no NLP model or real master list loads. All names
are made up.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from api_fakes import HEADERS, make_client
from fastapi.testclient import TestClient

from finance_redactor.config import master_list_setup_skipped

# --- guard -----------------------------------------------------------------


def test_api_call_without_client_header_is_refused(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)
    assert client.get("/api/health").status_code == 403


def test_foreign_host_is_refused_even_with_the_header(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)
    response = client.get(
        "/api/health", headers={**HEADERS, "Host": "evil.example:8501"}
    )
    assert response.status_code == 403


def test_localhost_name_is_allowed(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)
    response = client.get("/api/health", headers={**HEADERS, "Host": "localhost:8501"})
    assert response.status_code == 200


def test_responses_carry_security_headers(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)
    response = client.get("/api/health", headers=HEADERS)
    assert response.headers["Content-Security-Policy"].startswith("default-src 'self'")
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_no_cors_headers_for_a_cross_site_preflight(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)
    response = client.options(
        "/api/jobs",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-fpr-client",
        },
    )
    assert "access-control-allow-origin" not in response.headers


def test_api_docs_are_not_served(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


# --- static UI -------------------------------------------------------------


def test_placeholder_page_without_a_bundle(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)
    response = client.get("/")
    assert response.status_code == 200
    assert "just web-build" in response.text


def test_bundle_is_served_when_built(tmp_path: Path) -> None:
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text("<p>ui</p>", encoding="utf-8")
    client, _ = make_client(tmp_path, static_dir=static)
    assert client.get("/").text == "<p>ui</p>"
    assert client.get("/api/health", headers=HEADERS).json() == {"status": "ok"}


# --- master list -----------------------------------------------------------


def test_master_list_status(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)
    body = client.get("/api/master-list", headers=HEADERS).json()
    assert body["total"] == 2
    assert body["counts"] == {"Staff": 2}
    assert body["issues"][0]["title"] == "Duplicate names"
    assert body["issues"][0]["total"] == 3
    assert body["needs_setup"] is False
    assert body["age_seconds"] is None


def test_refresh_clears_the_cache(tmp_path: Path) -> None:
    client, fake = make_client(tmp_path)
    assert client.post("/api/master-list/refresh", headers=HEADERS).status_code == 200
    assert fake.refreshed == 1


def test_empty_list_needs_setup_until_skipped(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path, counts={})
    assert client.get("/api/master-list", headers=HEADERS).json()["needs_setup"]
    body = client.post("/api/master-list/skip", headers=HEADERS).json()
    assert body["needs_setup"] is False
    assert master_list_setup_skipped() is True


def test_skip_is_forgotten_once_names_load(tmp_path: Path) -> None:
    client, fake = make_client(tmp_path, counts={})
    client.post("/api/master-list/skip", headers=HEADERS)
    fake.counts = {"Staff": 1}
    client.get("/api/master-list", headers=HEADERS)
    assert master_list_setup_skipped() is False


def test_check_folder(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)
    folder = tmp_path / "shared"
    folder.mkdir()
    url = "/api/master-list/check"
    assert not client.post(url, json={"folder": str(folder)}, headers=HEADERS).json()[
        "found"
    ]
    (folder / "Names List - Organized.xlsx").write_bytes(b"x")
    assert client.post(url, json={"folder": str(folder)}, headers=HEADERS).json()[
        "found"
    ]


def test_setup_refuses_a_folder_without_the_workbook(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)
    response = client.post(
        "/api/master-list/setup", json={"folder": str(tmp_path)}, headers=HEADERS
    )
    assert response.status_code == 422


@pytest.mark.parametrize("make_file", [True, False])
def test_setup_saves_the_folder(tmp_path: Path, make_file: bool) -> None:
    from finance_redactor.config import read_persisted_master_list_dir

    client, _ = make_client(tmp_path)
    folder = tmp_path / "shared"
    folder.mkdir()
    if make_file:
        (folder / "Names List - Organized.xlsx").write_bytes(b"x")
    response = client.post(
        "/api/master-list/setup",
        json={"folder": str(folder), "save_anyway": not make_file},
        headers=HEADERS,
    )
    assert response.status_code == 200
    assert read_persisted_master_list_dir() == folder


# --- jobs ------------------------------------------------------------------


def upload(client: TestClient, name: str, data: bytes):
    return client.post("/api/jobs", files={"file": (name, data)}, headers=HEADERS)


@pytest.mark.parametrize(
    ("name", "data", "fmt"),
    [
        ("book.xlsx", b"PK\x03\x04rest", "excel"),
        ("doc.PDF", b"%PDF-1.7 rest", "pdf"),
        ("letter.docx", b"PK\x03\x04rest", "docx"),
    ],
)
def test_upload_creates_a_job(tmp_path: Path, name: str, data: bytes, fmt: str) -> None:
    client, fake = make_client(tmp_path)
    response = upload(client, name, data)
    assert response.status_code == 201
    body = response.json()
    assert body["format"] == fmt
    assert body["size"] == len(data)
    assert fake.jobs.get(body["id"]).data == data


def test_upload_refuses_unsupported_type(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)
    response = upload(client, "old.xls", b"\xd0\xcf\x11\xe0")
    assert response.status_code == 415
    assert "re-saved as .xlsx" in response.json()["detail"]


def test_upload_refuses_contents_that_do_not_match(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)
    assert upload(client, "fake.pdf", b"PK\x03\x04").status_code == 415


def test_upload_refuses_an_oversized_file(tmp_path: Path, monkeypatch) -> None:
    from finance_redactor.presentation.api import jobs

    monkeypatch.setattr(jobs, "MAX_UPLOAD_BYTES", 10)
    client, _ = make_client(tmp_path)
    assert upload(client, "big.pdf", b"%PDF-" + b"x" * 10).status_code == 413


def test_start_over_drops_the_bytes(tmp_path: Path) -> None:
    client, fake = make_client(tmp_path)
    job_id = upload(client, "doc.pdf", b"%PDF-1").json()["id"]
    assert client.delete(f"/api/jobs/{job_id}", headers=HEADERS).status_code == 204
    assert fake.jobs.get(job_id) is None
    # Unknown id: still 204, nothing to drop.
    assert client.delete(f"/api/jobs/{job_id}", headers=HEADERS).status_code == 204


def test_shutdown_drops_jobs_and_ends_the_process(tmp_path: Path) -> None:
    client, fake = make_client(tmp_path)
    upload(client, "doc.pdf", b"%PDF-1")
    response = client.post("/api/shutdown", headers=HEADERS)
    assert response.status_code == 202
    assert len(fake.jobs) == 0
    assert fake.shut_down == 1


# --- master-list folder check (exact filename) ------------------------------


def test_folder_check_needs_the_exact_filename(tmp_path: Path) -> None:
    from finance_redactor.presentation.api.master_list import (
        MASTER_LIST_FILENAME,
        master_list_exists_at,
    )

    assert master_list_exists_at(str(tmp_path)) is False
    assert master_list_exists_at("") is False
    assert master_list_exists_at("   ") is False
    (tmp_path / "Names List - Organized (2).xlsx").write_text("x")
    assert master_list_exists_at(str(tmp_path)) is False
    (tmp_path / MASTER_LIST_FILENAME).write_text("x")
    assert master_list_exists_at(str(tmp_path)) is True
    assert master_list_exists_at(f"  {tmp_path}  ") is True
