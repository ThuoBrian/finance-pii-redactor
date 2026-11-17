"""PDF through the web API: options, scan, review, preview, the two mappings.

Real use case and PyMuPDF adapter, fake detector, no OCR (see api_fakes).
All names are made up.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import fitz
import pytest
from api_fakes import HEADERS, make_client
from fastapi.testclient import TestClient

PAGES = [
    ["Payment to Jane Doe for salaries.", "Supplier: Acme Widgets."],
    ["Codename Project Falcon stays internal."],
]


def pdf(pages: list[list[str]] = PAGES, *, password: str | None = None) -> bytes:
    """Return PDF bytes with one text line per string, one page per list."""
    doc = fitz.open()
    for lines in pages:
        page = doc.new_page()
        for i, line in enumerate(lines):
            page.insert_text((72, 72 + 20 * i), line)
    if password:
        data = doc.tobytes(
            encryption=fitz.PDF_ENCRYPT_AES_256, user_pw=password, owner_pw=password
        )
    else:
        data = doc.tobytes()
    doc.close()
    return data


def text_of(data: bytes) -> str:
    """Return the text of every page."""
    with fitz.open(stream=data, filetype="pdf") as doc:
        return "\n".join(page.get_text() for page in doc)


def start(tmp_path: Path, data: bytes | None = None):
    """Upload the PDF; return ``(client, fake, job id)``."""
    client, fake = make_client(tmp_path)
    response = client.post(
        "/api/jobs", files={"file": ("report.pdf", data or pdf())}, headers=HEADERS
    )
    assert response.status_code == 201
    return client, fake, response.json()["id"]


def scan(client: TestClient, job_id: str, **overrides) -> dict:
    """Scan with defaults (labels, images blacked out); return the task."""
    body = {"style": "pseudonymize", "redact_images": True, "read_scans": True}
    response = client.post(
        f"/api/jobs/{job_id}/pdf/scan", json={**body, **overrides}, headers=HEADERS
    )
    assert response.status_code == 202, response.text
    return client.get(f"/api/jobs/{job_id}", headers=HEADERS).json()["task"]


def get(client: TestClient, path: str):
    """GET with the client header."""
    return client.get(path, headers=HEADERS)


def apply(client, job_id, excluded=(), words=(), columns=()):
    """Post review choices."""
    return client.post(
        f"/api/jobs/{job_id}/pdf/apply",
        json={
            "excluded": list(excluded),
            "words": list(words),
            "columns": list(columns),
        },
        headers=HEADERS,
    )


def rows_of(csv_text: str) -> list[dict[str, str]]:
    """Parse CSV text into dict rows."""
    return list(csv.DictReader(io.StringIO(csv_text)))


def test_options_report_size_and_no_ocr(tmp_path: Path) -> None:
    client, _, job_id = start(tmp_path)
    body = get(client, f"/api/jobs/{job_id}/pdf/options").json()
    assert body["can_read_scans"] is False
    assert body["total_pages"] == 2
    assert body["size_note_reading"] == "" and body["size_note_not_reading"] == ""


def test_scan_and_review_with_labels(tmp_path: Path) -> None:
    client, _, job_id = start(tmp_path)
    assert scan(client, job_id)["status"] == "done"
    body = get(client, f"/api/jobs/{job_id}/pdf/review").json()
    assert {r["term"] for r in body["rows"]} == {"Jane Doe", "Acme Widgets", "salaries"}
    assert body["blackout"] is False
    assert body["summary"].startswith("3 matches on 2 pages")
    assert {m["label"] for m in body["mapping"]} == {"[001]", "[002]", "[003]"}
    assert {o["location"] for o in body["occurrences"]} == {1}
    assert body["not_located"] == "" and body["scanned_note"] == ""


def test_untick_and_download_the_redacted_pdf(tmp_path: Path) -> None:
    client, _, job_id = start(tmp_path)
    scan(client, job_id)
    rows = get(client, f"/api/jobs/{job_id}/pdf/review").json()["rows"]
    key = next(r["key"] for r in rows if r["term"] == "salaries")
    assert apply(client, job_id, excluded=[key]).json()["applied"] == [key]
    response = get(client, f"/api/jobs/{job_id}/files/redacted")
    disposition = response.headers["Content-Disposition"]
    assert 'filename="redacted-' in disposition and disposition.endswith('.pdf"')
    text = text_of(response.content)
    assert "Jane Doe" not in text and "Acme Widgets" not in text
    assert "salaries" in text and "[001]" in text


def test_label_mapping_never_has_names(tmp_path: Path) -> None:
    client, _, job_id = start(tmp_path)
    scan(client, job_id)
    response = get(client, f"/api/jobs/{job_id}/files/pdf-mapping")
    assert "_mapping.csv" in response.headers["Content-Disposition"]
    rows = rows_of(response.text)
    assert rows and "Original name" not in rows[0]
    assert "Jane Doe" not in response.text
    assert {r["Master list"] for r in rows} == {"abc"}


def test_names_file_needs_switching_on(tmp_path: Path) -> None:
    client, _, job_id = start(tmp_path)
    scan(client, job_id)
    assert get(client, f"/api/jobs/{job_id}/files/pdf-names").status_code == 409
    assert get(client, f"/api/jobs/{job_id}/pdf/download").json()["names_file"] is False
    switch = client.post(
        f"/api/jobs/{job_id}/pdf/names-file", json={"enabled": True}, headers=HEADERS
    )
    assert switch.json() == {"enabled": True}
    response = get(client, f"/api/jobs/{job_id}/files/pdf-names")
    assert "_crosswalk.csv" in response.headers["Content-Disposition"]
    assert "Jane Doe" in response.text
    # A new scan starts with it off again.
    scan(client, job_id)
    assert get(client, f"/api/jobs/{job_id}/files/pdf-names").status_code == 409


def test_blackout_has_nothing_to_decode(tmp_path: Path) -> None:
    client, _, job_id = start(tmp_path)
    scan(client, job_id, style="blackout")
    body = get(client, f"/api/jobs/{job_id}/pdf/review").json()
    assert body["blackout"] is True and body["mapping"] == []
    response = get(client, f"/api/jobs/{job_id}/files/redacted")
    assert '-blackout.pdf"' in response.headers["Content-Disposition"]
    assert "Jane Doe" not in text_of(response.content)
    assert get(client, f"/api/jobs/{job_id}/files/pdf-mapping").status_code == 404
    switch = client.post(
        f"/api/jobs/{job_id}/pdf/names-file", json={"enabled": True}, headers=HEADERS
    )
    assert switch.status_code == 409
    info = get(client, f"/api/jobs/{job_id}/pdf/download").json()
    assert info["blackout"] is True and info["has_mapping"] is False


def test_before_you_share_flags_items_without_an_id(tmp_path: Path) -> None:
    client, _, job_id = start(tmp_path)
    scan(client, job_id)
    info = get(client, f"/api/jobs/{job_id}/pdf/download").json()
    # The fake master list is empty, so nothing resolves to an Internal ID.
    assert any("not on the master list" in n for n in info["before_share"])
    assert info["before_share_warn"] is False


def test_typed_word_is_added(tmp_path: Path) -> None:
    client, _, job_id = start(tmp_path)
    scan(client, job_id)
    body = apply(client, job_id, words=["Project Falcon"]).json()
    assert body["words"] == ["Project Falcon"]
    assert "Project Falcon" in {r["term"] for r in body["rows"]}
    response = get(client, f"/api/jobs/{job_id}/files/redacted")
    assert "Project Falcon" not in text_of(response.content)


def test_unticked_terms_carry_over(tmp_path: Path) -> None:
    client, _, job_id = start(tmp_path)
    scan(client, job_id)
    rows = get(client, f"/api/jobs/{job_id}/pdf/review").json()["rows"]
    key = next(r["key"] for r in rows if r["term"] == "salaries")
    apply(client, job_id, excluded=[key])
    scan(client, job_id)
    body = get(client, f"/api/jobs/{job_id}/pdf/review").json()
    assert body["applied"] == [key] and body["carried"] == [key]


def test_page_preview(tmp_path: Path) -> None:
    client, _, job_id = start(tmp_path)
    scan(client, job_id)
    for version in ("redacted", "original"):
        response = get(client, f"/api/jobs/{job_id}/pdf/page?n=1&version={version}")
        assert response.headers["content-type"] == "image/png"
        assert response.content.startswith(b"\x89PNG")
    assert get(client, f"/api/jobs/{job_id}/pdf/page?n=9").status_code == 422
    assert get(client, f"/api/jobs/{job_id}/pdf/page?n=1&version=x").status_code == 422


@pytest.mark.parametrize(
    ("choices", "status"),
    [({"columns": ["no such column"]}, 422), ({"excluded": ["never found"]}, 409)],
)
def test_apply_refuses_unknown_choices(
    tmp_path: Path, choices: dict, status: int
) -> None:
    client, _, job_id = start(tmp_path)
    scan(client, job_id)
    assert apply(client, job_id, **choices).status_code == status


def test_unknown_style_is_refused(tmp_path: Path) -> None:
    client, _, job_id = start(tmp_path)
    response = client.post(
        f"/api/jobs/{job_id}/pdf/scan", json={"style": "shred"}, headers=HEADERS
    )
    assert response.status_code == 422


def test_password_protected_pdf(tmp_path: Path) -> None:
    client, _, job_id = start(tmp_path, data=pdf(password="made-up-pw"))
    options = get(client, f"/api/jobs/{job_id}/pdf/options").json()
    assert options["total_pages"] == 0
    task = scan(client, job_id)
    assert task["status"] == "error" and "password-protected" in task["error"]


def test_damaged_pdf(tmp_path: Path) -> None:
    client, _, job_id = start(tmp_path, data=b"%PDF-1.7 damaged")
    task = scan(client, job_id)
    assert task["status"] == "error" and "could not be read as a PDF" in task["error"]


def test_occurrences_link_to_review_rows(tmp_path: Path) -> None:
    client, _, job_id = start(tmp_path)
    scan(client, job_id)
    body = get(client, f"/api/jobs/{job_id}/pdf/review").json()
    assert {o["key"] for o in body["occurrences"]} == {r["key"] for r in body["rows"]}
