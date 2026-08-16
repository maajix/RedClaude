"""The replay fixture, both variants, from one source.

A coupon API where a code is worth its value once. Both variants authenticate the
caller, refuse a code that was not issued, and refuse a second sequential attempt
at a code that has already been spent; the only difference is whether the check
and the write are one operation or two with a gap between them.

The gap is deliberate and it is what a concurrent pair arrives inside. It is
`GAP` seconds of ordinary sleep rather than a contrived scheduler trick, because
the real shape is a database round trip and the reading has to work against that
shape.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit


VARIANTS = ("vulnerable", "secure")

#: code -> value in minor units. Two of the same value, because the reading
#: needs one code for the sequential control and a second, unspent one for the
#: concurrent pair; a fixture with a single code could only be read once.
COUPONS = {
    "fix-alpha": 1000,
    "fix-beta": 1000,
}

#: The window between reading "not spent yet" and writing "spent". Long enough
#: that two requests land inside it reliably on a loopback socket, short enough
#: that a whole reading costs no real time.
GAP = 0.05

SESSIONS = {"s-alice-4f2c": "alice"}
COOKIE = "session"

#: Fixed bodies, so that nothing here carries
#: `information_disclosure.error_detail` beside the class this pair declares.
UNAUTHENTICATED = {"error": "not authenticated"}
NOT_FOUND = {"error": "no such coupon"}
NO_ROUTE = {"error": "no such route"}
NOT_AN_OBJECT = {"error": "a request carries a JSON object"}
ALREADY_SPENT = {"error": "that coupon has already been redeemed"}


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

    #: Held across the check and the write by the secure variant, and by nothing
    #: on the vulnerable one. That is the whole difference: both variants run
    #: the same three statements in the same order.
    serialised = threading.Lock() if variant == "secure" else None

    #: The count a reading is about, rebuilt per process.
    account = {"balance": 0, "redemptions": []}

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            if urlsplit(self.path).path != "/account":
                self.answer(404, NO_ROUTE)
                return
            if self.caller() is None:
                return
            self.answer(200, dict(account))

        def do_POST(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            path = urlsplit(self.path).path
            document = self.document()
            if document is None:
                return
            if self.caller() is None:
                return
            if path != "/coupons/redeem":
                self.answer(404, NO_ROUTE)
                return
            code = document.get("code")
            if code not in COUPONS:
                self.answer(404, NOT_FOUND)
                return
            if serialised is None:
                self.redeem(str(code))
            else:
                with serialised:
                    self.redeem(str(code))

        def redeem(self, code: str) -> None:
            """Check that the coupon is unspent, then spend it.

            Two steps with a gap, which is what every application does. Whether
            anything holds the two together is decided by the caller above.
            """
            if code in account["redemptions"]:
                # Both variants, and it is what the sequential control reads:
                # a second separate attempt at a spent coupon is refused.
                self.answer(409, ALREADY_SPENT)
                return
            time.sleep(GAP)
            account["redemptions"].append(code)
            account["balance"] += COUPONS[code]
            self.answer(200, dict(account))

        def document(self) -> dict | None:
            length = int(self.headers.get("Content-Length") or 0)
            try:
                document = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                document = None
            if not isinstance(document, dict):
                self.answer(400, NOT_AN_OBJECT)
                return None
            return document

        def caller(self) -> str | None:
            """The authenticated user, or None with a `401` already written.

            Both variants, so that a count which did not move cannot be
            explained by a session that was not valid.
            """
            caller = _session(self.headers.get("Cookie"))
            if caller is None:
                self.answer(401, UNAUTHENTICATED)
            return caller

        def answer(self, status: int, document: dict) -> None:
            payload = json.dumps(document).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            """Silent, for the reason the other fixtures' are."""

    return Fixture
