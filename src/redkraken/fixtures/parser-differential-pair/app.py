"""The parser-differential fixture, both variants, from one source.

One request body, two parsers. A spending policy reads the body with a scanner
that stops at the first `amount` it finds; the route that places the order reads
it with `json.loads`, where the last duplicate key wins. A body carrying
`amount` twice is therefore one number to the policy and another to the ledger.

Neither reading is wrong on its own. Both are readings a real stack contains --
a gateway or a schema validator on one side, the application's own decoder on
the other -- and the class is that they are both present and disagree.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit


VARIANTS = ("vulnerable", "secure")

COOKIE = "session"

SESSIONS = {"s-alice-4f2c": "alice"}

PASSWORDS = {"alice": "alice-password"}

#: What the policy will approve. A request above it is refused by the policy on
#: both variants, so the ceiling itself is not what the pair grades.
CEILING = 100

#: The policy's own reader: the first `amount` in the raw bytes. It never calls
#: a JSON decoder, which is exactly why it can disagree with one.
FIRST_AMOUNT = re.compile(rb'"amount"\s*:\s*(-?\d+)')

DUPLICATE = re.compile(rb'"amount"\s*:')


def _policy_amount(raw: bytes) -> int | None:
    """What the spending policy thinks this body asks for."""
    found = FIRST_AMOUNT.search(raw)
    return int(found.group(1)) if found else None


def _session(header: str | None) -> str | None:
    for part in (header or "").split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name == COOKIE:
            return SESSIONS.get(value)
    return None


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    one_reader = variant == "secure"
    placed: list[dict] = []

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            path = urlsplit(self.path).path
            if path == "/session":
                self.session()
                return
            if path != "/orders":
                self.answer(404, {"error": "no such route"})
                return
            if _session(self.headers.get("Cookie")) is None:
                self.answer(401, {"error": "not authenticated"})
                return

            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) or b"{}"

            if one_reader and len(DUPLICATE.findall(raw)) > 1:
                # The secure variant decides there is one body and one reading
                # of it. A repeated key is refused before either reader runs,
                # which is the only answer both of them can agree on.
                self.answer(400, {"error": "the body names amount more than once"})
                return

            approved = _policy_amount(raw)
            if approved is None:
                self.answer(400, {"error": "an order carries an amount"})
                return
            if approved > CEILING:
                self.answer(403, {"error": "above the spending policy", "ceiling": CEILING})
                return

            try:
                document = json.loads(raw)
            except ValueError:
                self.answer(400, {"error": "an order carries a JSON object"})
                return
            charged = document.get("amount")
            if not isinstance(charged, int):
                self.answer(400, {"error": "an amount is an integer"})
                return

            # The one difference between the variants, and it is visible in the
            # answer rather than only in a ledger: what the policy approved and
            # what the order was placed for are both reported, so a run can say
            # they differ instead of inferring it.
            placed.append({"user": "alice", "amount": charged})
            self.answer(
                201,
                {"order": len(placed), "approved": approved, "charged": charged},
            )

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            if urlsplit(self.path).path != "/orders":
                self.answer(404, {"error": "no such route"})
                return
            if _session(self.headers.get("Cookie")) is None:
                self.answer(401, {"error": "not authenticated"})
                return
            self.answer(200, {"orders": list(placed), "ceiling": CEILING})

        def session(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            try:
                document = json.loads(self.rfile.read(length) or b"{}")
                user = str(document["user"])
                password = str(document["password"])
            except (ValueError, KeyError, TypeError):
                self.answer(400, {"error": "a session request carries user and password"})
                return
            if PASSWORDS.get(user) != password:
                self.answer(401, {"error": "not authenticated"})
                return
            token = next(key for key, name in SESSIONS.items() if name == user)
            self.answer(
                200,
                {"user": user},
                cookie=f"{COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax",
            )

        def answer(self, status: int, document: dict, cookie: str | None = None) -> None:
            payload = json.dumps(document).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            if cookie is not None:
                self.send_header("Set-Cookie", cookie)
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            """Silent, for the reason the other fixtures' are."""

    return Fixture
