"""The recovery-flow fixture, both variants, from one source.

Not imported by the corpus compiler: `fixture.py` digests this file and never
executes it. The evaluator runs it from the bytes that digest was taken over.

Standard library only, and no state that outlives one process: the token store
is a dict that starts empty, so a repeat that inherited the previous one's
tokens would be measuring the harness.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler


VARIANTS = ("vulnerable", "secure")

#: What the deployment believes it is called. The secure variant builds every
#: link from this and nothing else; the vulnerable one builds it from whatever
#: authority the request carried.
ORIGIN = "accounts.fixture.test"

#: Registered addresses. Both variants answer identically for an address that is
#: not here, so which addresses exist cannot be read off this route -- that
#: question is `information_disclosure.identifier_oracle` and belongs to the
#: fixture that declares it.
ACCOUNTS = ("dana@fixture.test", "erin@fixture.test")

#: Issued in order and fixed, because what is under test is the authority the
#: link carries rather than how the token was generated. A random token would
#: make two repeats of one reading disagree on everything except the part that
#: matters.
TOKENS = ("t-9f21", "t-4c08", "t-77ba", "t-1d53", "t-8e6f")

ACCEPTED = {"status": "sent"}
BAD_REQUEST = {"error": "an email address is required"}
NOT_FOUND = {"error": "no such route"}


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    trusts_request_authority = variant == "vulnerable"
    issued: list[str] = []

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            path, _, _ = self.path.partition("?")
            if path != "/account/recover":
                self.answer(404, NOT_FOUND)
                return
            asked = self.request_body()
            address = asked.get("email") if isinstance(asked, dict) else None
            if not isinstance(address, str) or "@" not in address:
                self.answer(400, BAD_REQUEST)
                return
            authority = (
                (self.headers.get("Host") or ORIGIN)
                if trusts_request_authority
                else ORIGIN
            )
            if address not in ACCOUNTS:
                # Identical to the accepted answer, deliberately: an address
                # nobody registered is answered the way a registered one is.
                self.answer(202, dict(ACCEPTED, delivered=None))
                return
            token = TOKENS[len(issued) % len(TOKENS)]
            issued.append(token)
            self.answer(
                202,
                dict(
                    ACCEPTED,
                    # The fixture's stand-in for the mailbox. There is no mail
                    # transport here, so what would have been sent is returned
                    # to the caller that triggered it -- identically on both
                    # variants, which is what makes the authority inside it the
                    # only difference between them. A claim about the preview
                    # itself is a claim about the fixture, not about the target.
                    delivered={
                        "to": address,
                        "link": f"https://{authority}/account/reset?token={token}",
                    },
                ),
            )

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
