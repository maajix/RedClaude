"""The cookie-scope fixture, both variants, from one source.

Two things differ between the variants and they are the two halves of the class:
the attributes the server declares when it issues the session cookie, and
whether the server honours that cookie when the request arrives at a host other
than the one that issued it.

Declaring a loose `Domain` alone would make this a header-reading exercise, and
the Playbook exists precisely because a header is not the finding. Honouring the
cookie somewhere else alone would be unreadable, because nothing would say the
cookie was ever supposed to travel. The pair holds both.

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
SESSION = "s-alice-71bd"

#: What each variant declares when it issues the cookie. The vulnerable one is a
#: cookie for every host under the registrable parent of the host that issued it,
#: on every path, over plain HTTP, in cross-site requests; the secure one is
#: host-only, path-scoped, and neither of the last two.
ATTRIBUTES = {
    "vulnerable": "Domain={parent}; Path=/; SameSite=None",
    "secure": "Path=/account; Secure; HttpOnly; SameSite=Lax",
}


def _cookie(header: str | None, name: str) -> str | None:
    """The value a cookie header carries under one name, or None."""
    for part in (header or "").split(";"):
        found, separator, value = part.strip().partition("=")
        if separator and found == name:
            return value
    return None


def _host(header: str | None) -> str:
    """The host a request was addressed to, without its port."""
    return (header or "").partition(":")[0]


def _parent(host: str) -> str:
    """The registrable parent of a host, or the host where it has none.

    Taken from the request rather than written down, so that this fixture is
    scoped to whatever origin it is served under -- `evaluation.origin` derives
    that from the fixture's directory name, and a copy of the name in this file
    would go stale the moment the directory is renamed.
    """
    return host.partition(".")[2] or host


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    confines = variant == "secure"
    #: The host the session was issued under, recorded at issuance so the secure
    #: variant compares arrival against issuance rather than against a name.
    issued: dict[str, str] = {}

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            if urlsplit(self.path).path != "/session":
                self.answer(404, {"error": "no such route"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            try:
                document = json.loads(self.rfile.read(length) or b"{}")
                secret = str(document["password"])
                email = str(document["email"])
            except (ValueError, KeyError, TypeError):
                self.answer(400, {"error": "a request carries an email and a password"})
                return
            # Checked on both variants, and with the same answer for a wrong
            # address as for a wrong secret: this pair grades where a cookie
            # goes, and a login that let anybody in would make it hold a second
            # class nothing here declares.
            if email != EMAIL or not hmac.compare_digest(PASSWORD, secret):
                self.answer(401, {"error": "authentication failed"})
                return
            host = _host(self.headers.get("Host"))
            issued[SESSION] = host
            self.answer(
                200,
                {"email": EMAIL},
                cookie=f"{COOKIE}={SESSION}; {ATTRIBUTES[variant].format(parent=_parent(host))}",
            )

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            path = urlsplit(self.path).path
            if path not in ("/account", "/account/preferences"):
                self.answer(404, {"error": "no such route"})
                return
            if _cookie(self.headers.get("Cookie"), COOKIE) != SESSION:
                self.answer(401, {"error": "not authenticated"})
                return
            if confines and _host(self.headers.get("Host")) != issued.get(SESSION):
                # The other half of the class. The secure variant scoped the
                # cookie to one host and enforces that scope on arrival; the
                # vulnerable one answers whoever presents it, which is what
                # turns "the browser would attach this" into a session.
                self.answer(401, {"error": "session is not valid for this host"})
                return
            self.answer(200, {"email": EMAIL, "path": path, "host": _host(self.headers.get("Host"))})

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
