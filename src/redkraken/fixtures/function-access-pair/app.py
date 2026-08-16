"""The function-access fixture, both variants, from one source.

A gRPC-Web surface: the method is the path, the request is a POST, and the
answer to "was this allowed" is the `grpc-status` value rather than the HTTP
status. Every response here is HTTP `200`, including the refusals, which is the
whole reason this fixture exists as its own target rather than as another JSON
route.

Two deliberate simplifications, stated here because a fixture that quietly
deviates is a fixture nobody can grade against:

* The codec is JSON, not protobuf. What the Playbook under test reads is the
  trailer, and the bytes of the message are not what decides the claim.
* `grpc-status` is sent as a response header rather than as a trailer frame.
  That is what a Trailers-Only response looks like on the wire, and it keeps
  the fixture readable by an ordinary HTTP client while preserving the property
  that matters: the decision is not in the status line.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit


VARIANTS = ("vulnerable", "secure")

SESSIONS = {
    "s-alice-4f2c": "alice",
    "s-bob-9d17": "bob",
}

#: Which caller the application considers an administrator. One of the two, so
#: that "this method refuses me" can be told from "this method refuses
#: everybody".
ADMINISTRATORS = ("alice",)

COOKIE = "session"

#: gRPC status codes, by the name the specification gives them. Only the four
#: this fixture can answer with.
OK = 0
PERMISSION_DENIED = 7
UNAUTHENTICATED = 16
UNIMPLEMENTED = 12

#: The method every caller may call. This is the control: a refusal on the
#: privileged method means nothing unless the same session was served here.
OPEN_METHOD = "/billing.Invoices/ListMine"

#: The method the secure variant reserves for an administrator.
ADMIN_METHOD = "/billing.Admin/ListAll"

INVOICES = {
    "alice": [{"id": "inv-1", "cents": 4200}],
    "bob": [{"id": "inv-2", "cents": 900}],
}


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
    checks_role = variant == "secure"

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            method = urlsplit(self.path).path
            length = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(length)

            caller = _session(self.headers.get("Cookie"))
            if caller is None:
                # Both variants. `16` is not `7`: the caller was not identified,
                # which is a different answer from being identified and refused.
                self.answer(UNAUTHENTICATED, "no session", {})
                return
            if method == OPEN_METHOD:
                self.answer(OK, "", {"invoices": INVOICES[caller]})
                return
            if method == ADMIN_METHOD:
                if checks_role and caller not in ADMINISTRATORS:
                    # The one difference between the variants.
                    self.answer(PERMISSION_DENIED, "administrator only", {})
                    return
                everything = [row for rows in INVOICES.values() for row in rows]
                self.answer(OK, "", {"invoices": everything})
                return
            # `12` says the method is not served. A run that reads it as a
            # boundary has read the absence of an implementation as a decision.
            self.answer(UNIMPLEMENTED, f"unknown method {method}", {})

        def answer(self, status: int, message: str, document: dict) -> None:
            payload = json.dumps(document).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/grpc-web+json")
            self.send_header("grpc-status", str(status))
            if message:
                self.send_header("grpc-message", message)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            """Silent, for the reason the other fixtures' are."""

    return Fixture
