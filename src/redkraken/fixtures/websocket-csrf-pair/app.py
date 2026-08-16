"""The websocket-CSRF fixture, both variants, from one source.

A cookie-authenticated WebSocket. The handshake is an ordinary HTTP request that
carries the caller's cookies, which is the whole reason this class exists on
this transport: a page on any origin can open one, and the browser will attach
the session.

The handshake is answered by hand rather than by a library, because the answer
is the fixture: `101` and a frame, or `403`. Once the frame is written the
connection is closed, so nothing here needs a frame parser or a read loop.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import base64
import hashlib
import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit


VARIANTS = ("vulnerable", "secure")

SESSIONS = {
    "s-alice-4f2c": "alice",
    "s-bob-9d17": "bob",
}

COOKIE = "session"

#: RFC 6455's constant. The accept value proves the server understood the
#: handshake, which is what tells a real upgrade from a page that happened to
#: answer `101`.
GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

SOCKET = "/socket"

#: What the socket sends once, immediately, to whoever completed the handshake.
#: Session-scoped on purpose: a socket that pushed only public data would be a
#: socket nobody could reach anything through.
INBOX = {
    "alice": [{"from": "bob", "subject": "quarterly report"}],
    "bob": [{"from": "alice", "subject": "invoice 4200"}],
}

UNAUTHENTICATED = {"error": "not authenticated"}
NOT_FOUND = {"error": "no such route"}
FORBIDDEN = {"error": "origin not allowed"}
BAD_HANDSHAKE = {"error": "not a websocket handshake"}


def _session(header: str | None) -> str | None:
    """The user a cookie header names, or None for every other header."""
    for part in (header or "").split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name == COOKIE:
            return SESSIONS.get(value)
    return None


def _accept(key: str) -> str:
    """RFC 6455's `Sec-WebSocket-Accept` for a client key."""
    return base64.b64encode(hashlib.sha1((key + GUID).encode("ascii")).digest()).decode("ascii")


def _frame(payload: bytes) -> bytes:
    """One unmasked text frame, FIN set. Short bodies only, which is all this sends."""
    if len(payload) > 125:
        raise ValueError("this fixture sends one short frame")
    return bytes([0x81, len(payload)]) + payload


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    checks_origin = variant == "secure"

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            if urlsplit(self.path).path != SOCKET:
                self.answer(404, NOT_FOUND)
                return
            key = self.headers.get("Sec-WebSocket-Key")
            upgrade = (self.headers.get("Upgrade") or "").lower()
            if not key or upgrade != "websocket":
                self.answer(400, BAD_HANDSHAKE)
                return

            caller = _session(self.headers.get("Cookie"))
            if caller is None:
                # Both variants, and the control: a refused handshake is
                # evidence about origins only if the session was working.
                self.answer(401, UNAUTHENTICATED)
                return

            # Same-origin, computed from the request rather than declared, so
            # the check holds wherever this fixture is served. A handshake with
            # no Origin at all is not a browser's and the secure variant
            # refuses it too.
            origin = self.headers.get("Origin")
            allowed = f"http://{self.headers.get('Host')}"
            if checks_origin and origin != allowed:
                # The one difference between the variants.
                self.answer(403, FORBIDDEN)
                return

            self.send_response(101)
            self.send_header("Upgrade", "websocket")
            self.send_header("Connection", "Upgrade")
            self.send_header("Sec-WebSocket-Accept", _accept(key))
            self.end_headers()
            self.wfile.write(_frame(json.dumps({"inbox": INBOX[caller]}).encode("utf-8")))
            self.wfile.flush()
            self.close_connection = True

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
