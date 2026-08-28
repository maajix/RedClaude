"""The cookie-parsing fixture, both variants, from one source.

Two readers of one `Cookie` header. The gate that decides whether a request is
authenticated walks the header from the front and stops at the first `session`;
the handler that decides *whose* account to answer with walks it from the back.
One header carrying the name twice is therefore two different callers, and the
vulnerable variant answers as the second while having admitted the first.

That is the whole class, and it is deliberately not about scope: both variants
issue the same `Set-Cookie` line, with the same attributes, from the same route.
A run that read the issuing response has read nothing here.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit


VARIANTS = ("vulnerable", "secure")

COOKIE = "session"

#: The sessions this fixture issues, and nothing else is one. Fixed rather than
#: minted, so two runs of one plan see the same bytes and a differing answer is
#: about the parser rather than about a token.
SESSIONS = {
    "s-alice-4f2c": "alice",
    "s-bob-9d17": "bob",
}

ACCOUNTS = {
    "alice": {"user": "alice", "email": "alice@fixture.invalid", "balance": 120},
    "bob": {"user": "bob", "email": "bob@fixture.invalid", "balance": 4},
}

PASSWORDS = {"alice": "alice-password", "bob": "bob-password"}

#: The attributes both variants issue. Identical on purpose: the difference this
#: pair grades is in how a header is read back, not in how one is written.
ATTRIBUTES = "Path=/; HttpOnly; SameSite=Lax"


def _pairs(header: str | None) -> list[tuple[str, str]]:
    """Every `name=value` in a `Cookie` header, in the order it was sent."""
    found = []
    for part in (header or "").split(";"):
        name, separator, value = part.strip().partition("=")
        if separator:
            found.append((name, value))
    return found


def _first(header: str | None) -> str | None:
    """The caller the *first* `session` names. This is what the gate reads."""
    for name, value in _pairs(header):
        if name == COOKIE:
            return SESSIONS.get(value)
    return None


def _last(header: str | None) -> str | None:
    """The caller the *last* `session` names. This is what the handler reads."""
    caller = None
    for name, value in _pairs(header):
        if name == COOKIE:
            caller = SESSIONS.get(value)
    return caller


def _repeated(header: str | None) -> bool:
    return sum(1 for name, _ in _pairs(header) if name == COOKIE) > 1


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    one_reader = variant == "secure"

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            if urlsplit(self.path).path != "/session":
                self.answer(404, {"error": "no such route"})
                return
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
                cookie=f"{COOKIE}={token}; {ATTRIBUTES}",
            )

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            if urlsplit(self.path).path != "/account":
                self.answer(404, {"error": "no such route"})
                return
            header = self.headers.get("Cookie")

            if one_reader and _repeated(header):
                # The secure variant reads the header once and refuses a second
                # `session` outright, which is the only answer that cannot be
                # two answers. It says which name repeated, because a 400 with
                # no reason is indistinguishable from a malformed request.
                self.answer(400, {"error": f"the {COOKIE} cookie was sent more than once"})
                return

            admitted = _first(header)
            if admitted is None:
                self.answer(401, {"error": "not authenticated"})
                return

            # The one difference between the variants, and it is a disagreement
            # rather than a missing check: the gate above admitted the first
            # session and the line below serves the last one.
            served = _first(header) if one_reader else _last(header)
            if served is None:
                self.answer(401, {"error": "not authenticated"})
                return
            self.answer(200, dict(ACCOUNTS[served], admitted_as=admitted))

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
