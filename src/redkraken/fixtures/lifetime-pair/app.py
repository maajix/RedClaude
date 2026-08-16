"""The session-lifetime fixture, both variants, from one source.

Both variants log in, both clear the cookie on logout, and both refuse a session
value that was never issued. The difference is on the server: the vulnerable
variant's logout deletes the client's copy and leaves the record, so the token a
client held before the logout keeps working afterwards.

The class is `session_handling.lifetime` and this is the shape it takes in real
applications -- a logout that is a `Set-Cookie` and nothing else.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import hmac
import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit


VARIANTS = ("vulnerable", "secure")

EMAIL = "alice@fixture.invalid"
PASSWORD = "correct-horse-fixture"

COOKIE = "session"

#: The value `POST /session` issues. Fixed rather than random so that a run can
#: hold it across a logout without the fixture having to remember which request
#: minted it, and so that two repeats of an evaluation read the same thing.
SESSION = "s-alice-3ce8"


def _cookie(header: str | None, name: str) -> str | None:
    """The value a cookie header carries under one name, or None."""
    for part in (header or "").split(";"):
        found, separator, value = part.strip().partition("=")
        if separator and found == name:
            return value
    return None


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    revokes = variant == "secure"

    #: The server side of the session, which is what the class is about. A
    #: logout that only writes a `Set-Cookie` never touches this set.
    live: set[str] = set()

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            path = urlsplit(self.path).path
            if path == "/session":
                self.login()
            elif path == "/session/logout":
                self.logout()
            else:
                self.answer(404, {"error": "no such route"})

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            if urlsplit(self.path).path != "/account":
                self.answer(404, {"error": "no such route"})
                return
            presented = _cookie(self.headers.get("Cookie"), COOKIE)
            if presented is None or presented not in live:
                # The control, on both variants: a value nobody issued is
                # refused, so a `200` after a logout is a statement about the
                # logout rather than about a route that never authenticates.
                self.answer(401, {"error": "not authenticated"})
                return
            self.answer(200, {"email": EMAIL, "session": presented})

        def login(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            try:
                document = json.loads(self.rfile.read(length) or b"{}")
                secret = str(document["password"])
                email = str(document["email"])
            except (ValueError, KeyError, TypeError):
                self.answer(400, {"error": "a request carries an email and a password"})
                return
            if email != EMAIL or not hmac.compare_digest(PASSWORD, secret):
                self.answer(401, {"error": "authentication failed"})
                return
            live.add(SESSION)
            self.answer(200, {"email": EMAIL}, cookie=f"{COOKIE}={SESSION}; Path=/")

        def logout(self) -> None:
            presented = _cookie(self.headers.get("Cookie"), COOKIE)
            if presented is None or presented not in live:
                self.answer(401, {"error": "not authenticated"})
                return
            if revokes:
                # The one difference between the variants. Both clear the
                # client's copy below; only this variant ends the session.
                live.discard(presented)
            self.answer(
                200,
                {"ended": True},
                cookie=f"{COOKIE}=; Path=/; Max-Age=0",
            )

        def answer(self, status: int, document: dict, cookie: str | None = None) -> None:
            payload = json.dumps(document).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            if cookie is not None:
                self.send_header("Set-Cookie", cookie)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            """Silent, for the reason the other fixtures' are."""

    return Fixture
