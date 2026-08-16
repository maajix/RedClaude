"""The channel-subscription fixture, both variants, from one source.

A cookie-authenticated WebSocket that takes the topic to subscribe to in the
handshake's query string. Both halves know who is calling and both halves refuse
a handshake from a foreign origin. What differs is whether the topic asked for is
checked against the topics the caller is entitled to.

The handshake is answered by hand rather than by a library, and one frame is
written before the connection closes, for the reasons the other socket fixture's
source gives.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import base64
import hashlib
import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit


VARIANTS = ("vulnerable", "secure")

SESSIONS = {
    "s-alice-4f2c": "alice",
    "s-bob-9d17": "bob",
}

COOKIE = "session"

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

SOCKET = "/socket"

#: The topics this server publishes, and what each one carries. They are streams
#: rather than objects: no row here has an owner column and no name here is an
#: identifier that could be incremented. What is authorized is the subscription.
TOPICS = {
    "orders": [{"event": "order.placed", "reference": "AB-1190"}],
    "payouts": [{"event": "payout.sent", "amount": 4200, "to": "acct-77"}],
}

#: Published on purpose, and identically on both variants, so a run that refutes
#: is refuting against a stated rule rather than against a guess.
ENTITLEMENTS = {
    "alice": ["orders"],
    "bob": ["orders", "payouts"],
}

UNAUTHENTICATED = {"error": "not authenticated"}
NOT_FOUND = {"error": "no such route"}
NO_SUCH_TOPIC = {"error": "no such topic"}
FORBIDDEN_ORIGIN = {"error": "origin not allowed"}
FORBIDDEN_TOPIC = {"error": "not subscribed to that topic"}
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
    # The one difference between the variants. Both know the caller and both
    # know what the caller is entitled to; one of them consults it.
    checks_entitlement = variant == "secure"

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            parts = urlsplit(self.path)
            if parts.path != SOCKET:
                self.answer(404, NOT_FOUND)
                return
            key = self.headers.get("Sec-WebSocket-Key")
            if not key or (self.headers.get("Upgrade") or "").lower() != "websocket":
                self.answer(400, BAD_HANDSHAKE)
                return

            caller = _session(self.headers.get("Cookie"))
            if caller is None:
                # Both variants, and the control: a refused subscription is
                # evidence about entitlements only if the session was working.
                self.answer(401, UNAUTHENTICATED)
                return

            # Both variants, so that `session_handling.csrf` is settled the same
            # way on each half and is not a second class in this pair. Same-origin
            # is computed from the request rather than declared, and a handshake
            # carrying no Origin at all is refused on both.
            if self.headers.get("Origin") != f"http://{self.headers.get('Host')}":
                self.answer(403, FORBIDDEN_ORIGIN)
                return

            topic = (parse_qs(parts.query).get("channel") or [""])[0]
            if topic not in TOPICS:
                self.answer(404, NO_SUCH_TOPIC)
                return
            if checks_entitlement and topic not in ENTITLEMENTS[caller]:
                self.answer(403, FORBIDDEN_TOPIC)
                return

            self.subscribe(key, topic)

        def subscribe(self, key: str, topic: str) -> None:
            self.send_response(101)
            self.send_header("Upgrade", "websocket")
            self.send_header("Connection", "Upgrade")
            self.send_header("Sec-WebSocket-Accept", _accept(key))
            self.end_headers()
            pushed = {"channel": topic, "events": TOPICS[topic]}
            self.wfile.write(_frame(json.dumps(pushed).encode("utf-8")))
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
