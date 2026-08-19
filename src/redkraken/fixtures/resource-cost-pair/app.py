"""The resource-cost fixture, both variants, from one source.

One batch route that both variants rate-limit per origin, and one bound that
only the secure variant has: a ceiling on how much work a single request may
ask for. What is under test is the cost of one request, not how many requests
are allowed, so the request limit is deliberately identical on both sides.

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

#: Requests one origin may send before either variant refuses. Enforced by both,
#: so a run that only counts requests sees no difference at all between them.
REQUEST_ALLOWANCE = 20

#: Operations one request may ask for in the secure variant. The vulnerable
#: variant has no equivalent: it performs whatever the batch names.
OPERATION_CEILING = 25

#: What each operation costs to perform, and what the answer reports having
#: spent. A fixed number rather than a measured duration, because a reading of
#: this fixture has to get the same answer under any machine load.
UNIT_COST = 4

#: The window the request allowance is spent in, in seconds, and what a refusal
#: tells the caller to wait. The batch refusal carries no `Retry-After` at all:
#: waiting does not make an oversized batch acceptable, and the answer already
#: says what would be.
WINDOW = 60

NOT_FOUND = {"error": "no such route"}
TOO_MANY = {"error": "rate limit exceeded"}
BAD_REQUEST = {"error": "operations is a list of {\"kind\": \"render\"} objects"}
TOO_MUCH = {"error": "too many operations in one request"}


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    bounds_one_request = variant == "secure"
    requests: dict[str, tuple[float, int]] = {}

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            if urlsplit(self.path).path != "/api/v1/render":
                self.answer(404, NOT_FOUND)
                return
            sent, wait = self.spend(self.client_address[0])
            if sent > REQUEST_ALLOWANCE:
                self.answer(429, TOO_MANY, retry_after=str(wait))
                return
            asked = self.request_body()
            batch = asked.get("operations") if isinstance(asked, dict) else None
            if not isinstance(batch, list) or not all(
                isinstance(one, dict) and one.get("kind") == "render" for one in batch
            ):
                self.answer(400, BAD_REQUEST)
                return
            if bounds_one_request and len(batch) > OPERATION_CEILING:
                self.answer(429, dict(TOO_MUCH, ceiling=OPERATION_CEILING, asked=len(batch)))
                return
            # The work itself is not done: what a reading needs is what the
            # request was allowed to ask for, and a fixture that actually spent
            # the time would make the corpus slow to grade and the answer
            # dependent on the machine.
            self.answer(
                200,
                {
                    "completed": len(batch),
                    "spent": len(batch) * UNIT_COST,
                    "requests_remaining": REQUEST_ALLOWANCE - sent,
                },
            )

        def spend(self, origin: str) -> tuple[int, int]:
            """What this origin has spent in the open window, and the wait left of it."""
            now = monotonic()
            opened, sent = requests.get(origin, (now, 0))
            if now - opened >= WINDOW:
                opened, sent = now, 0
            requests[origin] = (opened, sent + 1)
            return sent + 1, max(1, ceil(WINDOW - (now - opened)))

        def request_body(self) -> object:
            try:
                length = int(self.headers.get("Content-Length") or "0")
            except ValueError:
                return None
            try:
                return json.loads(self.rfile.read(length) or b"null")
            except (json.JSONDecodeError, UnicodeDecodeError):
                return None

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
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
