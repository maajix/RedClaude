"""The cross-origin-read fixture, both variants, from one source.

An authenticated account view that decides, per request, which origin may read
its answer. One variant answers whichever origin asked; the other answers only
the one origin this deployment was configured for.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit


VARIANTS = ("vulnerable", "secure")

SESSIONS = {"s-alice-4d18": "alice"}
COOKIE = "session"

#: The token the write route requires beside the session, on both variants. It
#: is here so the pair holds a write that is defended identically on both halves:
#: `session_handling.csrf` is `realtime`'s class and `websocket-csrf-pair`'s
#: target, and a fixture whose write accepted a forged request would be positive
#: for two classes at once.
CSRF_COOKIE = "csrf"
CSRF_HEADER = "X-CSRF-Token"
CSRF_TOKEN = "c-7f31a90b"

#: The one origin this deployment was configured to share with, on both variants.
#: Answering it is a decision somebody made, not a defect, and it is the control
#: that keeps a reading from reporting the configuration.
PARTNER = "https://partner.acme.com"

#: What the account view answers, and every field of it belongs to the caller
#: rather than to the application. That is what makes a cross-origin read of it a
#: disclosure rather than a misconfiguration.
ACCOUNT = {
    "identity": "alice",
    "email": "alice@acme-customers.example",
    "plan": "business",
    "customer_id": "cus-4471",
}

#: What the public route answers. The same for every caller, which is why a
#: wildcard over it is not a finding.
STATUS = {"status": "ok", "build": "2026.8.3"}

UNAUTHENTICATED = {"error": "not authenticated"}
FORBIDDEN = {"error": "request token missing or wrong"}
NO_ROUTE = {"error": "no such route"}


def _session(header: str | None) -> str | None:
    """The user a cookie header names, or None for every other header."""
    return _cookie(header, COOKIE, SESSIONS)


def _cookie(header: str | None, name: str, table: dict[str, str] | None = None) -> str | None:
    for part in (header or "").split(";"):
        key, separator, value = part.strip().partition("=")
        if separator and key == name:
            return value if table is None else table.get(value)
    return None


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    shares_with_anybody = variant == "vulnerable"

    #: The counter behind `/api/metrics/live`. It exists to be noisy, and it is
    #: deliberately not on the subject: an account view that moved between two
    #: sends would make every comparison a reading performs ambiguous.
    scrapes = [0]

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            path = urlsplit(self.path).path
            if path == "/api/account":
                self.account()
            elif path == "/api/public/status":
                # The decoy, identically on both variants: a wildcard with no
                # credentials line, over a document that says the same thing to
                # everybody. A browser sends no session with it, so nothing
                # anybody reads here is anybody's.
                self.answer(200, dict(STATUS), {"Access-Control-Allow-Origin": "*"})
            elif path == "/api/metrics/live":
                # Noise, identically on both variants.
                scrapes[0] += 1
                self.answer(200, {"scrapes": scrapes[0]})
            else:
                self.answer(404, NO_ROUTE)

        def do_POST(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            path = urlsplit(self.path).path
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            if path != "/api/account/email":
                self.answer(404, NO_ROUTE)
                return
            if _session(self.headers.get("Cookie")) is None:
                self.answer(401, UNAUTHENTICATED)
                return
            # The write, defended the same way on both variants: the header has
            # to carry the value the cookie carries, which no other origin can
            # read. Refused identically on both halves, so this route can never
            # be the difference this pair grades.
            presented = self.headers.get(CSRF_HEADER)
            if presented != _cookie(self.headers.get("Cookie"), CSRF_COOKIE):
                self.answer(403, FORBIDDEN)
                return
            self.answer(200, {"updated": True})

        def account(self) -> None:
            """The subject. The one decision the variants disagree about."""
            if _session(self.headers.get("Cookie")) is None:
                self.answer(401, UNAUTHENTICATED)
                return
            self.answer(200, dict(ACCOUNT), self.sharing(self.headers.get("Origin")))

        def sharing(self, origin: str | None) -> dict[str, str]:
            """The two headers that decide who may read the answer."""
            if origin is None:
                # Not a cross-origin request at all, so there is nothing to say
                # about who may read it. Both variants say nothing.
                return {}
            if origin == PARTNER or shares_with_anybody:
                # The defect is the second half of that condition: the vulnerable
                # variant writes back whatever origin asked, beside the
                # credentials line that makes a browser hand the answer over.
                return {
                    "Access-Control-Allow-Origin": origin,
                    "Access-Control-Allow-Credentials": "true",
                    "Vary": "Origin",
                }
            # The defence: an origin that is not the configured one is told
            # nothing, so the browser keeps the answer to itself.
            return {"Vary": "Origin"}

        def answer(self, status: int, document: dict, headers: dict[str, str] | None = None) -> None:
            payload = json.dumps(document).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            """Silent, for the reason the other fixtures' are."""

    return Fixture
