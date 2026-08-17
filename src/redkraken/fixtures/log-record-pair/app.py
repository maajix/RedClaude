"""The log-record fixture, both variants, from one source.

One process-wide record of the requests that reached this application, and a
view that reads it back. One variant hands every caller the whole record; the
other hands each caller the entries they made.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit


VARIANTS = ("vulnerable", "secure")

SESSIONS = {"s-alice-4d18": "alice", "s-bob-9e02": "bob"}
COOKIE = "session"

#: How many entries the record holds before the oldest is dropped. Large enough
#: that the seeds survive any reading of this fixture, small enough to be a ring.
CAPACITY = 32

#: The record before any reading starts, so the leak is present rather than
#: waiting for the reading to create it.
#:
#: Alice's entry carries `SAMPLE_KEY` and Bob's does not, which makes the
#: credential decoy the reading Identity's own: it is in both variants, in the
#: caller's own record, and it is honoured by nothing here. A reading that files
#: it has filed `information_disclosure.credential_material`, which is `secrets`'
#: class and `credential-material-pair`'s target, on a string that buys nothing
#: and never differed between the two halves.
SAMPLE_KEY = "rk_sample_000000000000"
SEED = (
    {"identity": "alice", "method": "GET", "path": "/api/notes",
     "query": f"ref=onboarding-2026&sample_token={SAMPLE_KEY}"},
    {"identity": "bob", "method": "GET", "path": "/api/notes", "query": "ref=quarterly-2026"},
)

#: Each caller's own notes, so `/api/notes` is a route worth making a request to
#: and is never itself a leak.
NOTES = {
    "alice": [{"id": "n-11", "title": "Onboarding checklist"}],
    "bob": [{"id": "n-24", "title": "Quarterly numbers"}],
}

#: Public metadata: the strings this application publishes to everybody. On both
#: variants, and a finding on neither.
PUBLISHED = {"build": "2026.8.3", "region": "eu-central"}

#: A path the view names and no variant serves. Naming is not serving, and a
#: reading that reports this as exposed without asking for it has claimed
#: something neither variant holds.
ARCHIVE = "/api/activity/archive"

UNAUTHENTICATED = {"error": "not authenticated"}
NO_ROUTE = {"error": "no such route"}


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
    view_is_scoped = variant == "secure"

    #: The record. Process-wide, which is the point: one store, two readers.
    record = [dict(entry) for entry in SEED]

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            split = urlsplit(self.path)
            caller = _session(self.headers.get("Cookie"))
            if caller is None:
                self.answer(401, UNAUTHENTICATED)
                return
            # Every request that reaches the application is recorded, which is
            # what makes the view grow while a reading works.
            record.append({
                "identity": caller,
                "method": "GET",
                "path": split.path,
                "query": split.query,
            })
            del record[:-CAPACITY]
            if split.path == "/api/activity":
                self.activity(caller)
            elif split.path == "/api/notes":
                self.answer(200, {"notes": NOTES.get(caller, [])})
            else:
                # `/api/activity/archive` lands here on both variants. The view
                # names it; nothing serves it.
                self.answer(404, NO_ROUTE)

        def activity(self, caller: str) -> None:
            """The subject. The one clause the variants disagree about."""
            if view_is_scoped:
                # The defence: the entries this caller made, and no others.
                entries = [dict(entry) for entry in record if entry["identity"] == caller]
            else:
                # The defect: the view was written to show activity, and it
                # shows all of it.
                entries = [dict(entry) for entry in record]
            self.answer(200, dict(PUBLISHED) | {"archive": ARCHIVE, "entries": entries})

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
