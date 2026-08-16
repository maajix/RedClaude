"""The client-storage fixture, both variants, from one source.

The cookie is `HttpOnly` on both halves and both halves honour it. What differs
is whether the same session value is also handed to the page as data, where a
script can read it, keep it and present it later.

Both variants accept that value as a bearer credential. That is deliberately not
the difference: a leaked value nobody would honour is not a leaked credential,
so the acceptance is held constant and the leak is what moves.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit


VARIANTS = ("vulnerable", "secure")

ACCOUNTS = {"alice@example.test": "correct horse"}

SESSIONS = {"s-alice-4f2c": "alice"}

COOKIE = "session"

PROFILES = {
    "alice": {"user": "alice", "email": "alice@example.test", "plan": "team"},
}

#: Served by both variants, byte for byte. The script stores a token if it was
#: given one and does nothing if it was not, so the page is not the difference
#: either -- the login response is.
LOGIN = """<!doctype html>
<html><head><title>sign in</title></head>
<body>
<form id="signin">
<input id="email" name="email" value="">
<input id="password" name="password" type="password" value="">
<button id="go" type="submit">sign in</button>
</form>
<div id="state"></div>
<script>
(function () {
  document.getElementById('signin').addEventListener('submit', function (event) {
    event.preventDefault();
    fetch('/session', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        email: document.getElementById('email').value,
        password: document.getElementById('password').value
      })
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.token) { window.localStorage.setItem('session', data.token); }
        document.getElementById('state').textContent = data.session || data.error;
      });
  });
})();
</script>
</body></html>
"""

PROFILE = """<!doctype html>
<html><head><title>profile</title></head>
<body>
<div id="user">{user}</div>
<div id="email">{email}</div>
<div id="plan">{plan}</div>
</body></html>
"""

UNAUTHENTICATED = {"error": "not authenticated"}
BAD_CREDENTIALS = {"error": "email or password wrong"}
NOT_FOUND = {"error": "no such route"}

SESSION_ROUTE = "/session"
SUBJECT = "/profile"


def _session(header: str | None) -> str | None:
    """The user a cookie header names, or None for every other header."""
    for part in (header or "").split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name == COOKIE:
            return SESSIONS.get(value)
    return None


def _bearer(header: str | None) -> str | None:
    """The user an Authorization header names, on both variants."""
    scheme, separator, value = (header or "").partition(" ")
    if separator and scheme.lower() == "bearer":
        return SESSIONS.get(value.strip())
    return None


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    # The one difference between the variants, and it is one key in one body.
    # The vulnerable half answers a successful login with the session value the
    # cookie already carries; the secure half answers with the cookie only.
    hands_over_the_value = variant == "vulnerable"

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            path = urlsplit(self.path).path
            if path == "/":
                self.answer(200, LOGIN.encode("utf-8"), "text/html; charset=utf-8")
                return
            if path != SUBJECT:
                self.json(404, NOT_FOUND)
                return
            caller = _session(self.headers.get("Cookie")) or _bearer(
                self.headers.get("Authorization")
            )
            if caller is None:
                self.json(401, UNAUTHENTICATED)
                return
            self.answer(
                200,
                PROFILE.format(**PROFILES[caller]).encode("utf-8"),
                "text/html; charset=utf-8",
            )

        def do_POST(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            if urlsplit(self.path).path != SESSION_ROUTE:
                self.json(404, NOT_FOUND)
                return
            length = int(self.headers.get("Content-Length") or 0)
            try:
                sent = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                sent = {}
            if ACCOUNTS.get(sent.get("email")) != sent.get("password"):
                self.json(401, BAD_CREDENTIALS)
                return
            opened = {"session": "opened"}
            if hands_over_the_value:
                opened["token"] = "s-alice-4f2c"
            self.json(
                200,
                opened,
                # Same cookie on both halves. `Secure` is left off because this
                # fixture is served over plain HTTP, where a browser would
                # discard the cookie and the pair would grade nothing.
                cookie="session=s-alice-4f2c; HttpOnly; Path=/; SameSite=Lax",
            )

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
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            """Silent, for the reason the other fixtures' are."""

    return Fixture
