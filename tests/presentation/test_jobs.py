from __future__ import annotations

from datetime import datetime

import pytest

from finance_redactor.presentation.jobs import JobStore, file_format, neutral_stem


class FakeClock:
    """A clock the test moves by hand."""

    def __init__(self) -> None:
        """Start at an arbitrary time."""
        self.now = 1000.0

    def __call__(self) -> float:
        """Return the current fake time."""
        return self.now


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Budget.XLSX", "excel"),
        ("report.pdf", "pdf"),
        ("letter.docx", "docx"),
        ("old.xls", None),
        ("noextension", None),
        ("", None),
    ],
)
def test_file_format(name: str, expected: str | None) -> None:
    assert file_format(name) == expected


def test_create_stores_bytes_with_a_neutral_stem() -> None:
    store = JobStore()
    job = store.create("Jane Example payroll.xlsx", b"PK\x03\x04data", "excel")
    assert store.get(job.id) is job
    assert job.stem.startswith("redacted-")
    assert "Jane" not in job.stem
    assert len(job.id) >= 20


def test_new_upload_drops_the_previous_job() -> None:
    store = JobStore()
    first = store.create("a.pdf", b"%PDF-1", "pdf")
    second = store.create("b.pdf", b"%PDF-2", "pdf")
    assert store.get(first.id) is None
    assert store.get(second.id) is second
    assert len(store) == 1


def test_delete_drops_the_job() -> None:
    store = JobStore()
    job = store.create("a.pdf", b"%PDF-1", "pdf")
    assert store.delete(job.id) is True
    assert store.get(job.id) is None
    assert store.delete(job.id) is False


def test_idle_job_is_evicted_and_use_keeps_it_alive() -> None:
    clock = FakeClock()
    store = JobStore(ttl_seconds=60, clock=clock)
    job = store.create("a.pdf", b"%PDF-1", "pdf")
    clock.now += 50
    assert store.get(job.id) is job  # touched: the TTL restarts
    clock.now += 50
    assert store.get(job.id) is job
    clock.now += 61
    assert store.get(job.id) is None
    assert len(store) == 0


def test_neutral_stem_is_the_date_and_time_and_nothing_from_the_upload() -> None:
    assert neutral_stem(datetime(2026, 10, 20, 14, 5)) == "redacted-20261020-1405"


def test_neutral_stem_is_safe_in_a_file_name() -> None:
    stem = neutral_stem(datetime(2026, 1, 2, 3, 4))
    assert stem == "redacted-20260102-0304"
    assert all(ch.isalnum() or ch == "-" for ch in stem)


def test_cancel_stops_at_the_next_step_and_keeps_the_old_result() -> None:
    store = JobStore(spawn=lambda run: run())
    job = store.create("a.pdf", b"%PDF-1", "pdf")
    job.state["result"] = "old"

    def work(progress) -> None:
        progress(1, 3)
        assert store.cancel(job) is True  # the user clicks Cancel mid-run
        progress(2, 3)
        job.state["result"] = "new"  # never reached

    assert store.start_task(job, "Scanning", work)
    assert job.task.status == "cancelled"
    assert job.task.done == 1
    assert job.state["result"] == "old"
    # A new task starts clean, without the old cancel request.
    assert store.start_task(job, "Scanning", lambda progress: progress(1, 1))
    assert job.task.status == "done"


def test_cancelling_an_idle_job_does_nothing() -> None:
    store = JobStore()
    job = store.create("a.pdf", b"%PDF-1", "pdf")
    assert store.cancel(job) is False
    assert job.task.status == "idle"
