"""The query-operator fixture, both variants, from one source.

A document-store search whose filter value either keeps whatever type the caller
sent or is required to be a string. The matcher below knows one operator; the
class does not turn on how many there are, it turns on a value being read as an
operator at all.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit


VARIANTS = ("vulnerable", "secure")

#: The records, rebuilt per process so that every reading starts from one state.
RECORDS = (
    {"id": 1, "owner": "alice", "title": "Q1 plan"},
    {"id": 2, "owner": "alice", "title": "Notes"},
    {"id": 3, "owner": "bob", "title": "Roadmap"},
)

SESSIONS = {"s-alice-7e04": "alice"}
COOKIE = "session"

#: Fixed bodies on both variants, so that nothing here carries
#: `information_disclosure.error_detail` beside the class this pair declares.
UNAUTHENTICATED = {"error": "not authenticated"}
NO_ROUTE = {"error": "no such route"}
NOT_AN_OBJECT = {"error": "a request carries a JSON object"}
NOT_A_STRING = {"error": "owner is a string"}


def _session(header: str | None) -> str | None:
    """The user a cookie header names, or None for every other header."""
    for part in (header or "").split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name == COOKIE:
            return SESSIONS.get(value)
    return None


def _matches(record: dict, criterion: object) -> bool:
    """Whether one record satisfies a criterion for its owner.

    A string is an equality. A one-key object is an operator if the store knows
    the key, and a field lookup if it does not -- which is what makes `$ne` and
    `eq` two different questions written in the same shape.
    """
    if isinstance(criterion, dict) and len(criterion) == 1:
        (key, wanted), = criterion.items()
        if key == "$ne":
            return record["owner"] != wanted
        return record.get(key) == wanted
    return record["owner"] == criterion


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    checks_type = variant == "secure"

    #: The cursor behind `/search/live`. It exists to be noisy.
    searches = [0]

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            path = urlsplit(self.path).path
            document = self.document()
            if document is None:
                return
            if self.caller() is None:
                return
            if path == "/search":
                self.search(document.get("owner"))
            elif path == "/search/live":
                # Noise, identically on both variants.
                searches[0] += 1
                self.answer(200, {"cursor": f"c-{searches[0]}", "records": len(RECORDS)})
            elif path == "/search/echo":
                # The decoy. The body comes back and nothing matches on it.
                self.answer(200, {"submitted": document, "records": []})
            else:
                self.answer(404, NO_ROUTE)

        def search(self, criterion: object) -> None:
            """The subject. One check differs between the variants."""
            if checks_type and not isinstance(criterion, str):
                # The defence: a filter value that is not a value is refused
                # before anything can read it as an instruction.
                self.answer(400, NOT_A_STRING)
                return
            matched = [record for record in RECORDS if _matches(record, criterion)]
            self.answer(200, {"records": matched})

        def document(self) -> dict | None:
            length = int(self.headers.get("Content-Length") or 0)
            try:
                document = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                document = None
            if not isinstance(document, dict):
                self.answer(400, NOT_AN_OBJECT)
                return None
            return document

        def caller(self) -> str | None:
            """The authenticated user, or None with a `401` already written."""
            caller = _session(self.headers.get("Cookie"))
            if caller is None:
                self.answer(401, UNAUTHENTICATED)
            return caller

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
