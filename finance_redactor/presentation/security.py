"""Request checks for the local web server.

The server listens on 127.0.0.1 only, but any web page the user has open can
still send requests to localhost. Two checks stop that:

- **Host allowlist.** A request whose ``Host`` header is not this server's
  own loopback address is refused. That defeats DNS rebinding, where a
  hostile domain is re-pointed at 127.0.0.1 so the browser treats it as
  same-origin.
- **Custom header on every API call.** ``/api`` requests must carry
  :data:`CLIENT_HEADER`. A cross-site page can only send a custom header
  after a CORS preflight, and this server answers none (there is no CORS
  middleware), so the browser never sends the real request.

Every response also gets headers that keep the page from loading anything
off this machine or leaking a referrer.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

CLIENT_HEADER = "X-FPR-Client"

SECURITY_HEADERS = {
    # Everything the page needs ships in the bundle; images are same-origin
    # or blob: (a PDF page preview).
    "Content-Security-Policy": (
        "default-src 'self'; img-src 'self' blob: data:; "
        "style-src 'self' 'unsafe-inline'; object-src 'none'; "
        "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Cache-Control": "no-store",
}


def allowed_hosts(port: int) -> frozenset[str]:
    """Return the ``Host`` values this server answers to on ``port``."""
    return frozenset({f"127.0.0.1:{port}", f"localhost:{port}"})


def make_guard(
    hosts: frozenset[str],
) -> Callable[[Request, Callable[[Request], Awaitable[Response]]], Awaitable[Response]]:
    """Return HTTP middleware enforcing the checks in this module's docstring."""

    async def guard(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.headers.get("host", "").lower() not in hosts:
            response: Response = PlainTextResponse("Forbidden host", status_code=403)
        elif request.url.path.startswith("/api") and (
            request.headers.get(CLIENT_HEADER) != "1"
        ):
            response = PlainTextResponse("Forbidden", status_code=403)
        else:
            response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response

    return guard
