"""The per-identity rate limit fixture, both variants, from one source.

One API route, two sessions, and a counter that exists in one variant and not
the other. The counter is per session on purpose: a limit keyed on the process
would make the second Identity's requests depend on the first one's, and the
class is `per_identity` rather than `per_origin`.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit


VARIANTS = ("vulnerable", "secure")

#: session cookie -> user. Fixed and opaque, as in the other paired fixtures:
#: the sessions are how callers are told apart and not what is being asked
#: about.
SESSIONS = {
    "s-alice-4f2c": "alice",
    "s-bob-9d17": "bob",
}

COOKIE = "session"

#: What the secure variant allows one session before it refuses. Small enough
#: that a run does not have to spend much to see it, and larger than one so that
#: a single request is never the thing that trips it.
ALLOWANCE = 5

#: The rows the route serves. Static, so that the response is the same document
#: every time and the only thing that can vary across a sequence is whether it
#: was served at all.
ROWS = (
    {"id": 1, "title": "quarterly report"},
    {"id": 2, "title": "quarterly forecast"},
)

UNAUTHENTICATED = {"error": "not authenticated"}
NOT_FOUND = {"error": "no such route"}
TOO_MANY = {"error": "rate limit exceeded"}


def _session(header: str | None) -> str | None:
    """The user a cookie header names, or None for every other header."""
    for part in (header or "").split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name == COOKIE:
            return SESSIONS.get(value)
    return None


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    counts_requests = variant == "secure"

    #: user -> requests served this process. Per user, and gone when the process
    #: is, because a repeat that inherited the previous one's counter would be
    #: measuring the harness rather than the application.
    served: dict[str, int] = {}

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            if urlsplit(self.path).path != "/api/v1/documents":
                self.answer(404, NOT_FOUND)
                return
            caller = _session(self.headers.get("Cookie"))
            if caller is None:
                # Both variants. A sequence that was never authenticated is a
                # sequence against the anonymous surface, and the control step
                # is what tells the two apart.
                self.answer(401, UNAUTHENTICATED)
                return
            served[caller] = served.get(caller, 0) + 1
            if counts_requests and served[caller] > ALLOWANCE:
                # The one difference between the variants.
                self.send_response(429)
                self.send_header("Retry-After", "60")
                self.body(json.dumps(TOO_MANY).encode("utf-8"))
                return
            self.answer(200, {"rows": list(ROWS)})

        def answer(self, status: int, document: dict) -> None:
            self.send_response(status)
            self.body(json.dumps(document).encode("utf-8"))

        def body(self, payload: bytes) -> None:
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            """Silent, for the reason the other fixtures' are."""

    return Fixture
