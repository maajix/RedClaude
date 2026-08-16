"""The credential-verification fixture, both variants, from one source.

One login route. Both variants hold the same account, refuse the same wrong
password, and issue the same session for the right one. The difference is a
single guard: the vulnerable variant compares the secret only when the client
sent something truthy, so an omitted field, an empty string, `false`, `0` and
`[]` all walk past the comparison into a session.

That is the class as 018 describes it -- the server reaches an authenticated
state without having compared the secret -- and it is deliberately not a
guessing target: the stored password is a value no variant here iterates
towards.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import hmac
import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit


VARIANTS = ("vulnerable", "secure")

#: One account. Two would invite a run to compare the two answers and report
#: enumeration, which is a different class and not what this pair grades.
EMAIL = "alice@fixture.invalid"
PASSWORD = "correct-horse-fixture"
SESSION = "s-alice-4f2c"


def _verified(sent: object, coerces: bool) -> bool:
    """Whether this variant considers the presented secret checked.

    `coerces` is the whole defect. The vulnerable variant's guard is
    `if sent and not equal(...)`, which is a shape that appears in real code
    because it reads as "check it when we have one": every falsy value skips
    the comparison and the request continues as an authenticated one.

    Both variants agree on strings. A wrong non-empty password is refused by
    each of them, which is what makes that answer usable as a control.
    """
    if isinstance(sent, str) and sent:
        return hmac.compare_digest(PASSWORD, sent)
    if not coerces:
        # Absent, empty, or not a string: the secure variant has nothing to
        # compare and refuses rather than falling through.
        return False
    return not sent


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    coerces = variant == "vulnerable"

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            if urlsplit(self.path).path != "/session":
                self.answer(404, {"error": "no such route"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            try:
                document = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                self.answer(400, {"error": "a request carries a JSON object"})
                return
            if not isinstance(document, dict):
                self.answer(400, {"error": "a request carries a JSON object"})
                return

            if document.get("email") != EMAIL:
                # The same answer as a wrong password, on both variants and for
                # an address nobody holds. An account that answers differently
                # is user enumeration, which is a different class and would let
                # a run report this fixture for something it does not hold.
                self.answer(401, {"error": "authentication failed"})
                return

            if not _verified(document.get("password"), coerces):
                self.answer(401, {"error": "authentication failed"})
                return

            self.answer(200, {"session": SESSION, "email": EMAIL})

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
