"""The identifier-oracle fixture, both variants, from one source.

Not imported by the corpus compiler: `fixture.py` digests this file and never
executes it. The evaluator runs it from the bytes that digest was taken over.

Standard library only, and no state that outlives one process.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler


VARIANTS = ("vulnerable", "secure")

#: Registered addresses and what would let them in. Nothing here is a secret
#: worth protecting; the question this fixture asks is whether the answer to a
#: wrong password says which of the two things was wrong.
ACCOUNTS = {
    "dana@fixture.test": "correct-horse-9f21",
    "erin@fixture.test": "correct-horse-4c08",
}

REFUSED = {"error": "the email address or the password is wrong"}
UNKNOWN_ADDRESS = {"error": "no account exists for that email address"}
BAD_REQUEST = {"error": "an email address and a password are required"}
NOT_FOUND = {"error": "no such route"}


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    names_the_reason = variant == "vulnerable"

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            path, _, _ = self.path.partition("?")
            if path != "/session":
                self.answer(404, NOT_FOUND)
                return
            asked = self.request_body()
            address = asked.get("email") if isinstance(asked, dict) else None
            secret = asked.get("password") if isinstance(asked, dict) else None
            if not isinstance(address, str) or not isinstance(secret, str):
                self.answer(400, BAD_REQUEST)
                return
            held = ACCOUNTS.get(address)
            if held == secret:
                self.answer(200, {"session": "s-1f4c", "email": address})
                return
            if held is None and names_the_reason:
                # The oracle: two refusals that a caller can tell apart, so the
                # register can be read off the route one address at a time.
                self.answer(404, UNKNOWN_ADDRESS)
                return
            self.answer(401, REFUSED)

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

        def answer(self, status: int, document: dict) -> None:
            payload = json.dumps(document).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            """Silent. The door's Receipts are the record of what was asked."""

    return Fixture
