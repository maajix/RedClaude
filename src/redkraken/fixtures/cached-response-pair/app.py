"""The cached-response fixture, both variants, from one source.

A dashboard behind a session, with a cache in front of it. The cache is a dict in
this process rather than a front end somebody deployed: what the class is about
is the key, and a key is the same wrong shape whoever holds it.

The session is checked before the cache is consulted, on both halves. That order
is deliberate. A cache that answered a caller carrying no session at all would be
a fixture holding a missing authentication check as well as this class, and the
disclosure this pair grades is the one between two callers who both signed in.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import json
import time
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit


VARIANTS = ("vulnerable", "secure")

ACCOUNTS = {
    "alice@example.test": ("correct horse", "s-alice-4f2c"),
    "bob@example.test": ("battery staple", "s-bob-9d17"),
}

SESSIONS = {
    "s-alice-4f2c": "alice",
    "s-bob-9d17": "bob",
}

COOKIE = "session"

DASHBOARDS = {
    "alice": {"user": "alice", "balance": 250, "next_invoice": "AB-1190"},
    "bob": {"user": "bob", "balance": 4120, "next_invoice": "CD-2277"},
}

PAGE = """<!doctype html>
<html><head><title>dashboard</title></head>
<body>
<div id="user">{user}</div>
<div id="balance">{balance}</div>
<div id="invoice">{next_invoice}</div>
</body></html>
"""

#: Published on purpose and the same on both variants, so a run that reports a
#: stale answer is reporting against a stated lifetime rather than a guess.
MAX_AGE = 60

UNAUTHENTICATED = {"error": "not authenticated"}
BAD_CREDENTIALS = {"error": "email or password wrong"}
NOT_FOUND = {"error": "no such route"}

SESSION_ROUTE = "/session"
SUBJECT = "/dashboard"


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
    # The one difference between the variants, and it is the key. The vulnerable
    # half keys on what was asked for; the secure half keys on who asked.
    keys_on_the_caller = variant == "secure"
    #: `key -> (stored_at, document)`. One process, one dict, for the lifetime of
    #: the variant the evaluator started.
    cache: dict[str, tuple[float, str]] = {}

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            if urlsplit(self.path).path != SUBJECT:
                self.json(404, NOT_FOUND)
                return
            presented = _cookie(self.headers.get("Cookie"), COOKIE)
            caller = SESSIONS.get(presented or "")
            if caller is None:
                # Before the cache, on both variants, and never cached itself.
                self.json(401, UNAUTHENTICATED)
                return
            self.dashboard(caller, presented or "")

        def do_POST(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            if urlsplit(self.path).path != SESSION_ROUTE:
                self.json(404, NOT_FOUND)
                return
            length = int(self.headers.get("Content-Length") or 0)
            try:
                sent = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                sent = {}
            known = ACCOUNTS.get(sent.get("email"))
            if known is None or known[0] != sent.get("password"):
                self.json(401, BAD_CREDENTIALS)
                return
            self.json(
                200,
                {"session": "opened"},
                cookie=f"session={known[1]}; HttpOnly; Path=/; SameSite=Lax",
            )

        def dashboard(self, caller: str, presented: str) -> None:
            """The subject, served through the cache the variant configured."""
            key = f"GET {self.path}"
            if keys_on_the_caller:
                key = f"{key} {presented}"
            stored = cache.get(key)
            if stored is not None and time.monotonic() - stored[0] < MAX_AGE:
                self.answer(200, stored[1], age=int(time.monotonic() - stored[0]))
                return
            document = PAGE.format(**DASHBOARDS[caller])
            cache[key] = (time.monotonic(), document)
            self.answer(200, document, age=None)

        # -- reading and writing -----------------------------------------------

        def json(self, status: int, document: dict, cookie: str | None = None) -> None:
            payload = json.dumps(document).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            if cookie is not None:
                self.send_header("Set-Cookie", cookie)
            self.end_headers()
            self.wfile.write(payload)

        def answer(self, status: int, document: str, age: int | None) -> None:
            payload = document.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            # Published on both halves so a run can tell a stored answer from a
            # fresh one without timing it, and so the two directives below are
            # the only thing that differs.
            self.send_header("X-Cache", "MISS" if age is None else "HIT")
            if age is not None:
                self.send_header("Age", str(age))
            if keys_on_the_caller:
                self.send_header("Cache-Control", f"private, max-age={MAX_AGE}")
                self.send_header("Vary", "Cookie")
            else:
                self.send_header("Cache-Control", f"public, max-age={MAX_AGE}")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            """Silent, for the reason the other fixtures' are."""

    return Fixture
