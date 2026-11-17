"""In-memory store for uploads and everything built from them.

One :class:`Job` per uploaded file holds its bytes and, later, its scan
results and outputs. Nothing is written to disk: the uploaded document and
the files built from it are Confidential until the user downloads them, and
memory is dropped when the job is, or when the app closes.

The app serves one person on their own machine, so at most a handful of jobs
exist at once. A new upload replaces the previous job, Start over deletes it,
and a job left idle past :data:`IDLE_TTL_SECONDS` is dropped on the next store
access.
"""

from __future__ import annotations

import logging
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# Long enough for a slow review, short enough that a forgotten document does
# not sit in memory all day.
IDLE_TTL_SECONDS = 4 * 60 * 60

FORMATS = {"xlsx": "excel", "pdf": "pdf", "docx": "docx"}

_log = logging.getLogger(__name__)

Progress = Callable[[int, int], None]


class UserFacingError(Exception):
    """A failure whose message is safe and useful to show the user as is.

    Messages must never quote document content: they reach the screen and
    could reach a log.
    """


def neutral_stem(now: datetime) -> str:
    """Return ``redacted-YYYYMMDD-HHMM``: a download name with nothing from the upload.

    The upload's own name can be a person's or a vendor's, so no part of it is
    reused for the redacted file or its mapping CSV.
    """
    return f"redacted-{now:%Y%m%d-%H%M}"


def file_format(filename: str) -> str | None:
    """Return ``"excel"``, ``"pdf"`` or ``"docx"`` for a supported name, else None."""
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return FORMATS.get(extension)


class _Cancelled(Exception):
    """Raised from the progress callback once the user asked to cancel."""


@dataclass
class Task:
    """The job's one background task (a scan or a rebuild) and its progress."""

    status: str = "idle"  # idle | running | done | error | cancelled
    label: str = ""
    done: int = 0
    total: int = 0
    error: str = ""
    # Checked at every progress step (each unique value, paragraph or page).
    cancel_requested: bool = False


@dataclass
class Job:
    """One upload and what has been built from it so far.

    ``state`` holds per-format results (scan result, findings, outputs) under
    names the format's router owns.
    """

    id: str
    filename: str
    format: str
    data: bytes
    stem: str
    touched: float = field(default_factory=time.monotonic)
    state: dict[str, Any] = field(default_factory=dict)
    task: Task = field(default_factory=Task)
    # Guards ``state`` and ``task`` between request threads and the worker.
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)


class JobStore:
    """Thread-safe map of job id to :class:`Job`, with idle eviction."""

    def __init__(
        self,
        *,
        ttl_seconds: float = IDLE_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        spawn: Callable[[Callable[[], None]], None] | None = None,
    ) -> None:
        """Create an empty store.

        ``clock`` and ``spawn`` (how a background task is started; a daemon
        thread by default) are injectable so tests run deterministically.
        """
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds
        self._clock = clock
        self._spawn = spawn or _start_daemon

    def start_task(
        self, job: Job, label: str, work: Callable[[Progress], None]
    ) -> bool:
        """Run ``work`` in the background; False if a task is already running.

        ``work`` gets a progress callback ``(done, total)``. A
        :class:`UserFacingError` becomes the task's error message; any other
        exception gets a generic one, and only its type is logged, never its
        message, which could quote a cell or a name.

        After :meth:`cancel`, the next progress step stops the work and the
        task ends as ``cancelled``. Workers store their results only at the
        end, so a cancelled run leaves the previous result untouched.
        """
        with job.lock:
            if job.task.status == "running":
                return False
            job.task = Task(status="running", label=label)

        def progress(done: int, total: int) -> None:
            if job.task.cancel_requested:
                raise _Cancelled
            job.task.done, job.task.total = done, total

        def run() -> None:
            try:
                work(progress)
            except _Cancelled:
                job.task.status = "cancelled"
            except UserFacingError as exc:
                job.task.status, job.task.error = "error", str(exc)
            except Exception as exc:  # noqa: BLE001 - reported to the user below
                _log.error("Background task failed: %s", type(exc).__name__)
                job.task.status = "error"
                job.task.error = (
                    "Something went wrong while working on this file. Try "
                    "again, or close the app and start it again."
                )
            else:
                job.task.status = "done"

        self._spawn(run)
        return True

    def create(self, filename: str, data: bytes, fmt: str) -> Job:
        """Store a new upload, dropping every earlier job.

        One file at a time: a new upload replaces the previous one, so its bytes never linger behind the new document.
        """
        job = Job(
            id=secrets.token_urlsafe(16),
            filename=filename,
            format=fmt,
            data=data,
            stem=neutral_stem(datetime.now()),
            touched=self._clock(),
        )
        with self._lock:
            self._jobs.clear()
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        """Return the job and mark it used, or None if unknown or expired."""
        with self._lock:
            self._evict_idle()
            job = self._jobs.get(job_id)
            if job is not None:
                job.touched = self._clock()
            return job

    def cancel(self, job: Job) -> bool:
        """Ask the job's running task to stop; False if nothing is running."""
        with job.lock:
            if job.task.status != "running":
                return False
            job.task.cancel_requested = True
            return True

    def delete(self, job_id: str) -> bool:
        """Drop a job and its bytes; return whether it existed."""
        with self._lock:
            return self._jobs.pop(job_id, None) is not None

    def clear(self) -> None:
        """Drop every job."""
        with self._lock:
            self._jobs.clear()

    def __len__(self) -> int:
        with self._lock:
            self._evict_idle()
            return len(self._jobs)

    def _evict_idle(self) -> None:
        cutoff = self._clock() - self._ttl
        for job_id in [j.id for j in self._jobs.values() if j.touched < cutoff]:
            del self._jobs[job_id]


def _start_daemon(target: Callable[[], None]) -> None:
    threading.Thread(target=target, daemon=True).start()
