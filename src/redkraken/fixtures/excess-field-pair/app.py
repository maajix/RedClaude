"""The excess-field fixture, both variants, from one source.

One GraphQL endpoint, two sessions, and one field that one variant withholds.
The interesting half of this fixture is what it does with the status line: every
answer here is `200` except the unauthenticated one, and whether the caller got
what it asked for is inside the document.

The query is not parsed. Field names are matched against a fixed set, which is
enough to serve one selection on one type and keeps the fixture about the class
it declares rather than about a parser somebody wrote in an afternoon.

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

COOKIE = "session"

#: The one type this endpoint serves, by identifier.
USERS = {
    "1": {"id": "1", "name": "alice", "email": "alice@fixture.invalid"},
    "2": {"id": "2", "name": "bob", "email": "bob@fixture.invalid"},
}

#: Every field a caller may name. A field outside this set is answered the way a
#: schema would answer it: `200`, `data: null`, and a reason in `errors`.
FIELDS = ("email", "id", "name")

#: The field the secure variant withholds from everybody but its owner. One
#: field, so that the difference between the variants is one value at one path
#: and a run can name where it found it.
PRIVATE = "email"


def _session(header: str | None) -> str | None:
    """The user a cookie header names, or None for every other header."""
    for part in (header or "").split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name == COOKIE:
            return SESSIONS.get(value)
    return None


def _identifier(query: str) -> str | None:
    """The `id` argument the selection names, by the crudest reading that works."""
    _, separator, rest = query.partition("id:")
    if not separator:
        return None
    wanted = rest.strip().strip('"').split(")")[0].split(",")[0].strip().strip('"')
    return wanted or None


def _selection(query: str) -> tuple[list[str], list[str]]:
    """The known and unknown field names the query mentions, in the order declared."""
    inside = query.partition("{")[2]
    words = {word.strip('{}(),:"') for word in inside.replace("\n", " ").split()}
    known = [field for field in FIELDS if field in words]
    unknown = sorted(
        word
        for word in words
        if word and word not in FIELDS and word not in ("user", "id") and word.isalpha()
    )
    return known, unknown


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    withholds = variant == "secure"

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            if urlsplit(self.path).path != "/graphql":
                self.answer(404, {"errors": [{"message": "no such route"}]})
                return
            length = int(self.headers.get("Content-Length") or 0)
            try:
                document = json.loads(self.rfile.read(length) or b"{}")
                query = str(document["query"])
            except (ValueError, KeyError, TypeError):
                self.answer(400, {"errors": [{"message": "a request carries a query"}]})
                return

            caller = _session(self.headers.get("Cookie"))
            if caller is None:
                # Both variants, and the control: a `null` under the second
                # session says nothing unless that session was working.
                self.answer(401, {"errors": [{"message": "not authenticated"}]})
                return

            wanted = _identifier(query)
            if wanted not in USERS:
                self.answer(200, {"data": {"user": None}})
                return
            known, unknown = _selection(query)
            if unknown:
                # `200` with a refusal inside it. The fixture holds this on both
                # variants because it is the shape of the endpoint, not a defect:
                # a run that reads the status line has read nothing.
                self.answer(200, {
                    "data": None,
                    "errors": [
                        {"message": f"cannot query field {name!r} on type 'User'"}
                        for name in unknown
                    ],
                })
                return

            user = USERS[wanted]
            owns = user["name"] == caller
            fields = {name: user[name] for name in known}
            errors = []
            if withholds and PRIVATE in fields and not owns:
                # The one difference between the variants, and it is a value at
                # a path rather than a status: the field comes back `null` with
                # a reason beside it.
                fields[PRIVATE] = None
                errors = [{
                    "message": "not authorised to read this field",
                    "path": ["user", PRIVATE],
                }]
            answer: dict = {"data": {"user": fields}}
            if errors:
                answer["errors"] = errors
            self.answer(200, answer)

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
