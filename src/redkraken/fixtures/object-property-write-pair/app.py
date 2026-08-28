"""The object-property-write fixture, both variants, from one source.

One record, one owner, and one `PATCH` that writes what the body names. The
caller owns the object it is editing on both variants and on every request, so
nothing here is about reaching somebody else's row. What differs is which of
that object's *properties* the caller is allowed to set.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit


VARIANTS = ("vulnerable", "secure")

COOKIE = "session"

SESSIONS = {"s-alice-4f2c": "alice"}

PASSWORDS = {"alice": "alice-password"}

#: The record as it is served before anything is written to it. Rebuilt per
#: handler so two variants of one run do not share a mutation.
def _record() -> dict:
    return {
        "user": "alice",
        "display_name": "Alice",
        "email": "alice@fixture.invalid",
        "role": "member",
        "credit": 0,
        "verified": False,
    }


#: The properties the caller owns. Everything else on the record is the
#: application's, and the secure variant says so by name.
WRITABLE = ("display_name", "email")


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
    bounded = variant == "secure"
    record = _record()

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            if urlsplit(self.path).path != "/session":
                self.answer(404, {"error": "no such route"})
                return
            document = self.body()
            if document is None:
                return
            user, password = document.get("user"), document.get("password")
            if PASSWORDS.get(str(user)) != password:
                self.answer(401, {"error": "not authenticated"})
                return
            token = next(key for key, name in SESSIONS.items() if name == user)
            self.answer(
                200,
                {"user": user},
                cookie=f"{COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax",
            )

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            if urlsplit(self.path).path != "/account":
                self.answer(404, {"error": "no such route"})
                return
            if _session(self.headers.get("Cookie")) is None:
                self.answer(401, {"error": "not authenticated"})
                return
            self.answer(200, dict(record))

        def do_PATCH(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            if urlsplit(self.path).path != "/account":
                self.answer(404, {"error": "no such route"})
                return
            caller = _session(self.headers.get("Cookie"))
            if caller is None:
                self.answer(401, {"error": "not authenticated"})
                return
            document = self.body()
            if document is None:
                return
            if not isinstance(document, dict):
                self.answer(400, {"error": "an edit is an object"})
                return

            unowned = [key for key in document if key not in WRITABLE]
            if bounded and unowned:
                # The one difference between the variants. It names the fields
                # rather than answering a bare 400, because a refusal that does
                # not say what it refused cannot be told from a parse failure.
                self.answer(
                    403,
                    {
                        "error": "these properties are not the caller's to set",
                        "refused": sorted(unowned),
                        "writable": list(WRITABLE),
                    },
                )
                return

            # The vulnerable variant binds the whole body onto the record. The
            # caller owns the object, so no ownership check fires and none is
            # missing; what it never had is a statement of which of its
            # properties the caller owns.
            for key, value in document.items():
                if bounded and key not in WRITABLE:
                    continue
                record[key] = value
            self.answer(200, dict(record))

        def body(self) -> dict | None:
            """The JSON body, or the refusal that already went out."""
            length = int(self.headers.get("Content-Length") or 0)
            try:
                return json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                self.answer(400, {"error": "a request carries a JSON object"})
                return None

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
