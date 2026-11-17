"""Word through the web API: options, scan, review, typed words, download.

Real use case and docx adapter, fake detector (see api_fakes). All names
are made up.
"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from api_fakes import HEADERS, make_client
from docx import Document
from fastapi.testclient import TestClient

PARAGRAPHS = [
    "Payment to Jane Doe for salaries.",
    "Supplier: Acme Widgets.",
    "Codename Project Falcon stays internal.",
    "",
]


def document(paragraphs: list[str] = PARAGRAPHS) -> bytes:
    """Return .docx bytes with one paragraph per string."""
    doc = Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    out = BytesIO()
    doc.save(out)
    return out.getvalue()


def text_of(data: bytes) -> str:
    """Return all paragraph text of a .docx."""
    return "\n".join(p.text for p in Document(BytesIO(data)).paragraphs)


def start(tmp_path: Path, data: bytes | None = None):
    """Upload the document; return ``(client, fake, job id)``."""
    client, fake = make_client(tmp_path)
    response = client.post(
        "/api/jobs",
        files={"file": ("letter.docx", data or document())},
        headers=HEADERS,
    )
    assert response.status_code == 201
    return client, fake, response.json()["id"]


def scan(client: TestClient, job_id: str, words: list[str] | None = None) -> dict:
    """Scan with people and organizations; return the finished task."""
    response = client.post(
        f"/api/jobs/{job_id}/docx/scan",
        json={
            "entities": ["PERSON", "ORGANIZATION"],
            "threshold": 0.35,
            "words": words or [],
        },
        headers=HEADERS,
    )
    assert response.status_code == 202, response.text
    return client.get(f"/api/jobs/{job_id}", headers=HEADERS).json()["task"]


def review(client: TestClient, job_id: str) -> dict:
    """Return the review payload."""
    return client.get(f"/api/jobs/{job_id}/docx/review", headers=HEADERS).json()


def apply(client: TestClient, job_id: str, excluded: list[str], words: list[str]):
    """Post review choices."""
    return client.post(
        f"/api/jobs/{job_id}/docx/apply",
        json={"excluded": excluded, "words": words},
        headers=HEADERS,
    )


def key_of(body: dict, term: str) -> str:
    """Return the review key of ``term``."""
    return next(r["key"] for r in body["rows"] if r["term"] == term)


def test_options(tmp_path: Path) -> None:
    client, _, job_id = start(tmp_path)
    body = client.get(f"/api/jobs/{job_id}/docx/options", headers=HEADERS).json()
    assert body["threshold"]["max"] == 0.85
    assert {"code": "PERSON", "label": "Person"} in body["entities"]


def test_scan_and_review(tmp_path: Path) -> None:
    client, _, job_id = start(tmp_path)
    assert scan(client, job_id)["status"] == "done"
    body = review(client, job_id)
    assert {r["term"] for r in body["rows"]} == {"Jane Doe", "Acme Widgets", "salaries"}
    assert body["applied"] == [] and body["words"] == []
    assert len(body["occurrences"]) == 3
    assert {o["location"] for o in body["occurrences"]} == {1, 2}
    assert {m["original_name"] for m in body["mapping"]} >= {"Jane Doe"}


def test_untick_then_download(tmp_path: Path) -> None:
    client, _, job_id = start(tmp_path)
    scan(client, job_id)
    key = key_of(review(client, job_id), "salaries")
    body = apply(client, job_id, [key], []).json()
    assert body["applied"] == [key]
    # The unticked row stays in the list so it can be re-ticked.
    assert "salaries" in {r["term"] for r in body["rows"]}

    response = client.get(f"/api/jobs/{job_id}/files/redacted", headers=HEADERS)
    assert 'filename="redacted-' in response.headers["Content-Disposition"]
    text = text_of(response.content)
    assert "Jane Doe" not in text and "Acme Widgets" not in text
    assert "salaries" in text

    info = client.get(f"/api/jobs/{job_id}/docx/download", headers=HEADERS).json()
    assert info == {"excluded": [key], "removed_links": 0, "has_mapping": True}
    csv = client.get(f"/api/jobs/{job_id}/files/crosswalk", headers=HEADERS)
    assert "Jane Doe" in csv.text


def test_typed_word_is_added_without_rescanning(tmp_path: Path) -> None:
    client, fake, job_id = start(tmp_path)
    scan(client, job_id)
    calls = []
    original = fake.docx_service

    def counting():
        service = original()
        real_scan = service.scan
        service.scan = lambda *a, **k: calls.append(1) or real_scan(*a, **k)
        return service

    fake.docx_service = counting  # type: ignore[method-assign]
    body = apply(client, job_id, [], ["Project Falcon", " ", "Project Falcon"]).json()
    assert calls == []
    assert body["words"] == ["Project Falcon"]
    row = next(r for r in body["rows"] if r["term"] == "Project Falcon")
    assert row["why"] == "You typed it"
    response = client.get(f"/api/jobs/{job_id}/files/redacted", headers=HEADERS)
    assert "Project Falcon" not in text_of(response.content)


def test_words_from_an_earlier_file_apply_on_the_first_build(tmp_path: Path) -> None:
    client, _, job_id = start(tmp_path)
    scan(client, job_id, words=["Project Falcon"])
    body = review(client, job_id)
    assert body["words"] == ["Project Falcon"]
    assert "Project Falcon" in {r["term"] for r in body["rows"]}


def test_unticked_terms_carry_over(tmp_path: Path) -> None:
    client, _, job_id = start(tmp_path)
    scan(client, job_id)
    key = key_of(review(client, job_id), "salaries")
    apply(client, job_id, [key], [])
    scan(client, job_id)
    body = review(client, job_id)
    assert body["applied"] == [key] and body["carried"] == [key]
    response = client.get(f"/api/jobs/{job_id}/files/redacted", headers=HEADERS)
    assert "salaries" in text_of(response.content)


def test_apply_refuses_an_unknown_term(tmp_path: Path) -> None:
    client, _, job_id = start(tmp_path)
    scan(client, job_id)
    assert apply(client, job_id, ["never found"], []).status_code == 409


def test_too_many_words_are_refused(tmp_path: Path) -> None:
    client, _, job_id = start(tmp_path)
    scan(client, job_id)
    assert apply(client, job_id, [], ["x"] * 501).status_code == 422
    assert apply(client, job_id, [], ["x" * 201]).status_code == 422


def test_unreadable_document_reports_a_clear_error(tmp_path: Path) -> None:
    client, _, job_id = start(tmp_path, data=b"PK\x03\x04 not a document")
    task = scan(client, job_id)
    assert task["status"] == "error"
    assert "could not be read as a Word document" in task["error"]


def test_nothing_found_has_no_mapping(tmp_path: Path) -> None:
    client, _, job_id = start(tmp_path, data=document(["Nothing to see here."]))
    scan(client, job_id)
    body = review(client, job_id)
    assert body["rows"] == []
    assert body["summary"].startswith("Nothing was detected")
    response = client.get(f"/api/jobs/{job_id}/files/crosswalk", headers=HEADERS)
    assert response.status_code == 404


def test_word_routes_refuse_another_format(tmp_path: Path) -> None:
    client, _ = make_client(tmp_path)
    job_id = client.post(
        "/api/jobs", files={"file": ("a.pdf", b"%PDF-1")}, headers=HEADERS
    ).json()["id"]
    response = client.get(f"/api/jobs/{job_id}/docx/options", headers=HEADERS)
    assert response.status_code == 404


def test_occurrences_link_to_review_rows(tmp_path: Path) -> None:
    client, _, job_id = start(tmp_path)
    scan(client, job_id)
    body = review(client, job_id)
    assert {o["key"] for o in body["occurrences"]} == {r["key"] for r in body["rows"]}
