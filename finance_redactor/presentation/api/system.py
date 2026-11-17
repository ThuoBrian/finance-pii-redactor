"""Health check and Close the app."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks

from finance_redactor.presentation.api.context import Context

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health() -> dict[str, str]:
    """Report that the server is up."""
    return {"status": "ok"}


@router.post("/shutdown", status_code=202)
def shutdown(context: Context, tasks: BackgroundTasks) -> dict[str, str]:
    """Drop every job, then end the process once the response has gone out.

    Closing only the browser tab leaves the server, and the console window
    run.bat opened, holding the master list and NLP model in memory.
    """
    context.jobs.clear()
    tasks.add_task(context.shutdown)
    return {"status": "closing"}
