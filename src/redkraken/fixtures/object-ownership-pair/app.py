"""The object-ownership fixture, both variants, from one source.

Not imported by the corpus compiler: `fixture.py` digests this file and never
executes it, so a corpus that will not compile is still a corpus nobody ran. The
evaluator runs it from the bytes that digest was taken over, which is the only
moment anything here runs and the reason "what was served" and "what was
recorded" are one claim rather than two.

Standard library only, like the rest of the package, and no state that outlives
one process: the fixture is restarted per repeat and a repeat that inherited the
previous one's notes would be measuring the harness.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler


#: The two ways this source can be served. `secure` is the control half of the
#: pair and the vulnerable half is the other; a fixture with only one of them
#: could not tell a Playbook that fires correctly from one that always fires.
VARIANTS = ("vulnerable", "secure")

#: note id -> (owner, body). Sequential integers on purpose: an identifier a
#: caller cannot guess would make this fixture about enumeration as well, and a
#: fixture that carries two classes cannot say which one a claim was right about.
NOTES = {
    "1": ("alice", "alice's note"),
    "2": ("bob", "bob's note"),
}

#: session cookie -> user. Opaque and fixed, because the sessions are how the
#: caller is told apart and not something this fixture is asking a question
#: about. Both variants issue and accept exactly these.
SESSIONS = {
    "s-alice-4f2c": "alice",
    "s-bob-9d17": "bob",
}

COOKIE = "session"

#: Fixed bodies. A failure that returned a stack trace, a query or a path would
#: put `information_disclosure.error_detail` into the fixture beside the class it
#: declares, and the ground truth would then be understating what it contains.
UNAUTHENTICATED = {"error": "not authenticated"}
FORBIDDEN = {"error": "forbidden"}
NOT_FOUND = {"error": "no such note"}


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
    checks_owner = variant == "secure"

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            path, _, _ = self.path.partition("?")
            prefix, _, identifier = path.rpartition("/")
            if prefix != "/notes" or identifier not in NOTES:
                self.answer(404, NOT_FOUND)
                return
            caller = _session(self.headers.get("Cookie"))
            if caller is None:
                # Both variants. This is what makes the control evaluable: a
                # refusal under the second Identity means nothing unless a
                # working session is told apart from a broken one.
                self.answer(401, UNAUTHENTICATED)
                return
            owner, body = NOTES[identifier]
            if checks_owner and owner != caller:
                self.answer(403, FORBIDDEN)
                return
            self.answer(200, {"id": identifier, "owner": owner, "body": body})

        def answer(self, status: int, document: dict) -> None:
            payload = json.dumps(document).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            """Silent. The door's Receipts are the record of what was asked."""

    return Fixture
