"""The formula fixture, both variants, from one source.

A contact list and the spreadsheet it exports. Nothing here evaluates anything on
either half; the difference is whether the export writer prefixes an apostrophe
when a stored value begins with a character a spreadsheet application reads as
the start of a formula.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit


VARIANTS = ("vulnerable", "secure")

#: The characters a spreadsheet application reads as the start of a formula.
FORMULA = ("=", "+", "-", "@")

SESSIONS = {"s-alice-6f2a": "alice"}
COOKIE = "session"

#: Fixed bodies on both variants, so that nothing here carries
#: `information_disclosure.error_detail` beside the class this pair declares.
UNAUTHENTICATED = {"error": "not authenticated"}
NO_ROUTE = {"error": "no such route"}
NO_NAME = {"error": "a contact carries a name"}


def _session(header: str | None) -> str | None:
    """The user a cookie header names, or None for every other header."""
    for part in (header or "").split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name == COOKIE:
            return SESSIONS.get(value)
    return None


def _cell(value: str, guards: bool) -> str:
    """One value, written for a spreadsheet.

    The whole of the difference between the variants. `guards` decides whether a
    value that begins like a formula is marked as text before it is quoted.
    """
    if guards and value.startswith(FORMULA):
        value = "'" + value
    return '"' + value.replace('"', '""') + '"'


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    guards = variant == "secure"

    #: The stored contacts, rebuilt per process.
    contacts: list[str] = []
    #: The count behind `/contacts/live`. It exists to be noisy.
    reads = [0]

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            path = urlsplit(self.path).path
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            if self.caller() is None:
                return
            if path != "/contacts":
                self.answer(404, NO_ROUTE)
                return
            name = parse_qs(body.decode("utf-8", "replace")).get("name", [""])[0]
            if not name:
                self.answer(400, NO_NAME)
                return
            contacts.append(name)
            # Both variants reflect, identically. Nothing separates the halves
            # until the file is fetched, which is what this class looks like.
            self.answer(201, {"name": name, "contacts": len(contacts)})

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            parts = urlsplit(self.path)
            if self.caller() is None:
                return
            if parts.path == "/contacts.csv":
                self.export()
            elif parts.path == "/contacts/live":
                # Noise, identically on both variants.
                reads[0] += 1
                self.answer(200, {"reads": reads[0], "contacts": len(contacts)})
            elif parts.path == "/contacts/echo":
                # The decoy. The value comes back and is never stored, so it
                # never reaches the export.
                self.answer(200, {"query": parse_qs(parts.query).get("q", [""])[0]})
            else:
                self.answer(404, NO_ROUTE)

        def export(self) -> None:
            """The subject's file. One call differs between the variants."""
            rows = ["name"] + [_cell(name, guards) for name in contacts]
            payload = "\r\n".join(rows).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="contacts.csv"')
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def caller(self) -> str | None:
            """The authenticated user, or None with a `401` already written.

            The route is behind a session because the reading that grades it
            writes a record and then fetches the export that holds it, and an
            export belonging to a different caller would not hold it.
            """
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
