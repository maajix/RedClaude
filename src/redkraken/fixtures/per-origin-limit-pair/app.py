"""The per-origin rate limit fixture, both variants, from one source.

One unauthenticated route and a counter that exists in one variant and not the
other. There is no session here at all, which is what makes the class
`per_origin` rather than `per_identity`: with no caller to key a limit on, the
only limit that could exist is one on the origin the requests arrive from.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from math import ceil
from time import monotonic
from urllib.parse import urlsplit


VARIANTS = ("vulnerable", "secure")

#: What the secure variant serves one origin before it refuses. Small enough
#: that a run does not have to spend much to see it, and larger than one so that
#: a single request never trips it.
ALLOWANCE = 5

#: The window the allowance is spent in, in seconds, and what a refusal tells
#: the caller to wait. A counter that never refilled would make `Retry-After` a
#: promise this fixture does not keep, and would leave the secure variant
#: refusing every later reading of every other class for the life of the process.
WINDOW = 60

#: Static, so the only thing that can vary across a sequence is whether it was
#: served at all.
ROWS = (
    {"symbol": "ACME", "price": "41.20"},
    {"symbol": "OMNI", "price": "17.05"},
)

NOT_FOUND = {"error": "no such route"}
TOO_MANY = {"error": "rate limit exceeded"}


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    counts_the_origin = variant == "secure"
    served: dict[str, tuple[float, int]] = {}

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            if urlsplit(self.path).path != "/api/v1/quotes":
                self.answer(404, NOT_FOUND)
                return
            spent, wait = self.spend(self.client_address[0])
            if counts_the_origin and spent > ALLOWANCE:
                self.answer(429, TOO_MANY, retry_after=str(wait))
                return
            self.answer(200, {"quotes": list(ROWS)})

        def spend(self, origin: str) -> tuple[int, int]:
            """What this origin has spent in the open window, and the wait left of it."""
            now = monotonic()
            opened, spent = served.get(origin, (now, 0))
            if now - opened >= WINDOW:
                opened, spent = now, 0
            served[origin] = (opened, spent + 1)
            return spent + 1, max(1, ceil(WINDOW - (now - opened)))

        def do_POST(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            self.answer(404, NOT_FOUND)

        def answer(
            self, status: int, document: dict, retry_after: str | None = None
        ) -> None:
            payload = json.dumps(document).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            if retry_after is not None:
                self.send_header("Retry-After", retry_after)
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            """Silent. The door's Receipts are the record of what was asked."""

    return Fixture
