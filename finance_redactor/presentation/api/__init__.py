"""The web API and the built React bundle, served from one FastAPI app."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from finance_redactor.presentation.api import (
    docx,
    downloads,
    excel,
    jobs,
    master_list,
    pdf,
    system,
)
from finance_redactor.presentation.api.context import AppContext
from finance_redactor.presentation.security import allowed_hosts, make_guard

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

_NO_BUNDLE = (
    "<!doctype html><title>Finance PII Redactor</title>"
    "<p>The interface has not been built yet. Run <code>just web-build</code>.</p>"
)


def build_api(
    context: AppContext, *, port: int, static_dir: Path = STATIC_DIR
) -> FastAPI:
    """Return the app: API routers, request guard, and the static UI."""
    # No /docs or /openapi.json: nothing for the user there, and less surface.
    app = FastAPI(
        title="Finance PII Redactor", docs_url=None, redoc_url=None, openapi_url=None
    )
    app.state.context = context
    app.middleware("http")(make_guard(allowed_hosts(port)))
    for module in (master_list, jobs, excel, docx, pdf, downloads, system):
        app.include_router(module.router)

    if (static_dir / "index.html").is_file():
        # html=True serves index.html at "/"; the UI keeps its step in React
        # state, not the URL, so no client-side route fallback is needed.
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="ui")
    else:

        @app.get("/", include_in_schema=False)
        def no_bundle() -> HTMLResponse:
            return HTMLResponse(_NO_BUNDLE)

    return app
