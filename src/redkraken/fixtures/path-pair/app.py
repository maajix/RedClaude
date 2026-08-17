"""The path fixture, both variants, from one source.

An export route that names a document by path. One variant resolves the caller's
name and serves whatever the resolution reaches; the other resolves it and then
checks where the resolution landed.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import json
import posixpath
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit


VARIANTS = ("vulnerable", "secure")

#: The directory this route is meant to serve out of.
BASE = "exports"

#: The store, keyed by resolved path. Two documents live under `BASE` and two do
#: not, and no route anywhere serves the latter two by their own name -- reaching
#: them is only ever the resolution's doing.
DOCUMENTS = {
    "exports/report.txt": "April orders, 24 rows.\n",
    "exports/notes/summary.txt": "April was flat.\n",
    "vault/ledger.txt": "opening 41200, closing 39980\n",
    "vault/keys.txt": "rotation due 2026-07-01\n",
}

SESSIONS = {"s-alice-1f42": "alice"}
COOKIE = "session"

#: Fixed bodies on both variants, so that a refusal never says which of the
#: reasons to refuse applied. A fixture whose refusals differed would be handing
#: the reading `information_disclosure.error_detail` instead of this class.
UNAUTHENTICATED = {"error": "not authenticated"}
NO_ROUTE = {"error": "no such route"}
NO_DOCUMENT = {"error": "no such document"}


def _session(header: str | None) -> str | None:
    """The user a cookie header names, or None for every other header."""
    for part in (header or "").split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name == COOKIE:
            return SESSIONS.get(value)
    return None


def _file(query: str) -> str:
    """The document name the caller asked for, already percent-decoded."""
    return (parse_qs(query, keep_blank_values=True).get("file") or [""])[0]


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    checks_where_it_landed = variant == "secure"

    #: The counter behind `/documents/live`. It exists to be noisy.
    reads = [0]

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            parts = urlsplit(self.path)
            if self.caller() is None:
                return
            if parts.path == "/documents/export":
                self.export(_file(parts.query))
            elif parts.path == "/documents/name":
                # The decoy. The name comes back and nothing is resolved from it.
                self.answer(200, {"file": _file(parts.query)})
            elif parts.path == "/documents/live":
                # Noise, identically on both variants.
                reads[0] += 1
                self.answer(200, {"reads": reads[0]})
            else:
                self.answer(404, NO_ROUTE)

        def export(self, name: str) -> None:
            """The subject. Both variants resolve; one of them then looks."""
            resolved = posixpath.normpath(posixpath.join(BASE, name))
            if checks_where_it_landed and not (
                resolved == BASE or resolved.startswith(BASE + "/")
            ):
                # The defence: normalising is not the check. Where the
                # normalised path landed is the check.
                self.answer(404, NO_DOCUMENT)
                return
            document = DOCUMENTS.get(resolved)
            if document is None:
                self.answer(404, NO_DOCUMENT)
                return
            self.answer(200, {"document": resolved, "text": document})

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
