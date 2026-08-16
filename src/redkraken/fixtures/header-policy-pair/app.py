"""The header-policy fixture, both variants, from one source.

Every byte of every body is the same on both halves, and so is every status
line, every cookie attribute and the token check on the write. What differs is
the channel policy the response declares: whether the document may be framed,
and whether a foreign origin may read it with the caller's credentials attached.

There is no `Strict-Transport-Security` on either half. The class names HSTS
first, but this fixture is served over plain HTTP on loopback, where a browser
ignores the header entirely -- a policy nothing honours is a policy this pair
would be pretending to grade.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit


VARIANTS = ("vulnerable", "secure")

ACCOUNTS = {"alice@example.test": "correct horse"}

SESSIONS = {"s-alice-4f2c": "alice"}

COOKIE = "session"

#: One token per session, checked on the write by both variants. It is here so
#: that `session_handling.csrf` is settled the same way on each half: a pair
#: where only one side checked a token would be a pair holding two classes.
TOKENS = {"alice": "t-alice-91be"}

BALANCES = {"alice": 250}

FORM = """<!doctype html>
<html><head><title>transfer</title></head>
<body>
<form id="transfer" method="POST" action="/transfer">
<input type="hidden" name="token" value="{token}">
<input id="to" name="to" value="">
<input id="amount" name="amount" value="">
<button id="send" type="submit">send</button>
</form>
</body></html>
"""

UNAUTHENTICATED = {"error": "not authenticated"}
BAD_CREDENTIALS = {"error": "email or password wrong"}
BAD_TOKEN = {"error": "token missing or wrong"}
NOT_FOUND = {"error": "no such route"}

SESSION_ROUTE = "/session"
SUBJECT = "/transfer"


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
    # The one difference between the variants, and it is the policy alone. The
    # vulnerable half declares nothing about framing and hands any origin that
    # asks a credentialed read; the secure half refuses both.
    declares_policy = variant == "secure"

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            if urlsplit(self.path).path != SUBJECT:
                self.json(404, NOT_FOUND)
                return
            caller = _session(self.headers.get("Cookie"))
            if caller is None:
                self.json(401, UNAUTHENTICATED)
                return
            self.answer(
                200,
                FORM.format(token=TOKENS[caller]).encode("utf-8"),
                "text/html; charset=utf-8",
            )

        def do_POST(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            path = urlsplit(self.path).path
            sent = self.form()
            if path == SESSION_ROUTE:
                self.login(sent)
            elif path == SUBJECT:
                self.transfer(sent)
            else:
                self.json(404, NOT_FOUND)

        # -- the two writes ----------------------------------------------------

        def login(self, sent: dict[str, list[str]]) -> None:
            """Identical on both variants, including the cookie's attributes.

            `SameSite`, `Domain` and `Path` are `session_handling.cookie_scope`'s
            question and another pair already asks it, so they are fixed here.
            """
            email = sent.get("email", [""])[0]
            if ACCOUNTS.get(email) != sent.get("password", [""])[0]:
                self.json(401, BAD_CREDENTIALS)
                return
            self.json(
                200,
                {"session": "opened"},
                cookie="session=s-alice-4f2c; HttpOnly; Path=/; SameSite=Lax",
            )

        def transfer(self, sent: dict[str, list[str]]) -> None:
            """Also identical on both variants: the write is not what is graded."""
            caller = _session(self.headers.get("Cookie"))
            if caller is None:
                self.json(401, UNAUTHENTICATED)
                return
            if sent.get("token", [""])[0] != TOKENS[caller]:
                self.json(403, BAD_TOKEN)
                return
            self.json(
                200,
                {"from": caller, "to": sent.get("to", [""])[0], "balance": BALANCES[caller]},
            )

        # -- reading and writing -----------------------------------------------

        def form(self) -> dict[str, list[str]]:
            length = int(self.headers.get("Content-Length") or 0)
            return parse_qs(self.rfile.read(length).decode("utf-8"))

        def json(self, status: int, document: dict, cookie: str | None = None) -> None:
            self.answer(
                status, json.dumps(document).encode("utf-8"), "application/json", cookie
            )

        def answer(
            self,
            status: int,
            payload: bytes,
            content_type: str,
            cookie: str | None = None,
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            if cookie is not None:
                self.send_header("Set-Cookie", cookie)
            if declares_policy:
                self.send_header("Content-Security-Policy", "frame-ancestors 'none'")
                self.send_header("X-Frame-Options", "DENY")
            else:
                origin = self.headers.get("Origin")
                if origin:
                    self.send_header("Access-Control-Allow-Origin", origin)
                    self.send_header("Access-Control-Allow-Credentials", "true")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            """Silent, for the reason the other fixtures' are."""

    return Fixture
