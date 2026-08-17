"""The diagnostic-detail fixture, both variants, from one source.

A summary route with a numeric window. One variant lets the conversion fail and
reports the failure it caught; the other decides what a window is before it
converts, and says the same sentence about every value that is not one.

The second target for `information_disclosure.error_detail`. `error-detail-pair`
is the first, and it is an anonymous search route whose failure is a raw
traceback -- written for ticket 46 as an out-of-class negative for the
authorization family, so it carries no session and no controls. This one is
authenticated, carries the three precision controls ticket 54 asks for, and
discloses the build and the host beside the frame.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit


VARIANTS = ("vulnerable", "secure")

#: The application's own rule about the window, which both variants enforce and
#: which is the only thing the harmless-error control trips.
SMALLEST = 1
LARGEST = 100

#: What the vulnerable variant is willing to say about itself. A real handler
#: gets these from the traceback and the process; here they are constants so the
#: body is stable across runs and a reading can compare two of them.
SOURCE = "/srv/reports/summary.py"
LINE = 41
FUNCTION = "summarise"
BUILD = "reports 4.2.1"
HOST = "app-7c2f"

SESSIONS = {"s-alice-8e57": "alice"}
COOKIE = "session"

#: Fixed bodies on both variants. The pair's signal is what a *failure* says, so
#: every failure that is not the subject's has to say the same bounded thing on
#: both sides, or the fixture would be grading itself.
UNAUTHENTICATED = {"error": "not authenticated"}
NO_ROUTE = {"error": "no such route"}
OUT_OF_RANGE = {"error": f"limit is between {SMALLEST} and {LARGEST}"}

#: What the secure variant says about every value that is not a whole number,
#: whatever the value was.
NOT_A_NUMBER = {"error": "limit is a whole number"}

ROWS = [
    {"day": "2026-04-01", "orders": 18},
    {"day": "2026-04-02", "orders": 24},
    {"day": "2026-04-03", "orders": 11},
]


def _session(header: str | None) -> str | None:
    """The user a cookie header names, or None for every other header."""
    for part in (header or "").split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name == COOKIE:
            return SESSIONS.get(value)
    return None


def _limit(query: str) -> str:
    """The window the caller asked for, defaulting to a value that passes."""
    return (parse_qs(query, keep_blank_values=True).get("limit") or ["3"])[0]


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    reports_itself = variant == "vulnerable"

    #: The counter behind `/reports/live`. It exists to be noisy.
    reads = [0]

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            parts = urlsplit(self.path)
            if self.caller() is None:
                return
            if parts.path == "/reports/summary":
                self.summarise(_limit(parts.query))
            elif parts.path == "/reports/echo":
                # The decoy. The value comes back inside a failure, and the
                # failure is the route's own sentence: nothing about the process
                # that produced it is in there.
                self.answer(400, {
                    "error": f"limit {_limit(parts.query)!r} is not a whole number",
                })
            elif parts.path == "/reports/live":
                # Noise, identically on both variants.
                reads[0] += 1
                self.answer(200, {"reads": reads[0]})
            else:
                self.answer(404, NO_ROUTE)

        def summarise(self, limit: str) -> None:
            """The subject. The two variants differ in where the failure goes."""
            if reports_itself:
                # The defect: the conversion is allowed to fail, and what it
                # raised is handed to the caller along with where it happened.
                try:
                    window = int(limit)
                except ValueError as failed:
                    self.answer(500, {
                        "error": f"{type(failed).__name__}: {failed}",
                        "trace": [
                            f'File "{SOURCE}", line {LINE}, in {FUNCTION}',
                            "    window = int(limit)",
                        ],
                        "build": BUILD,
                        "host": HOST,
                    })
                    return
            else:
                # The defence: what a window may be is decided here, and every
                # value that is not one gets the same sentence.
                if not limit.isdigit():
                    self.answer(400, NOT_A_NUMBER)
                    return
                window = int(limit)
            if not SMALLEST <= window <= LARGEST:
                # The application's own rule, identical on both variants. This is
                # the ordinary failure a reading needs beside the other one.
                self.answer(400, OUT_OF_RANGE)
                return
            self.answer(200, {"rows": ROWS[:window]})

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
