"""The query-language fixture, both variants, from one source.

A report filter whose WHERE clause is either assembled from the caller's bytes or
built once and bound. The evaluator below understands a conjunction of equality
terms and nothing else; it is small on purpose, because the property this class
turns on is that an expression is parsed at all, not which dialect parses it.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit


VARIANTS = ("vulnerable", "secure")

#: The rows, rebuilt per process so that every reading starts from one state.
ROWS = (
    {"id": 1, "day": "2026-04-01", "title": "March close"},
    {"id": 2, "day": "2026-04-02", "title": "Weekly rollup"},
    {"id": 3, "day": "2026-04-02", "title": "Retention"},
    {"id": 4, "day": "2026-04-09", "title": "Weekly rollup"},
)

SESSIONS = {"s-alice-9b31": "alice"}
COOKIE = "session"

#: Fixed bodies on both variants, so that nothing here carries
#: `information_disclosure.error_detail` beside the class this pair declares.
UNAUTHENTICATED = {"error": "not authenticated"}
NO_ROUTE = {"error": "no such route"}
MALFORMED = {"error": "the filter could not be read"}


def _session(header: str | None) -> str | None:
    """The user a cookie header names, or None for every other header."""
    for part in (header or "").split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name == COOKIE:
            return SESSIONS.get(value)
    return None


def _term(side: str, row: dict) -> str:
    """One side of an equality: a quoted literal, or the column it names."""
    side = side.strip()
    if len(side) >= 2 and side[0] == "'" and side[-1] == "'":
        return side[1:-1]
    if side in row:
        return str(row[side])
    raise ValueError(f"neither a literal nor a column: {side!r}")


def _matches(expression: str, row: dict) -> bool:
    """Whether a conjunction of equality terms holds for one row.

    Deliberately tiny. It parses; that is the whole of what the vulnerable
    variant hands it and the whole of what the secure variant never does.
    """
    for clause in expression.split(" AND "):
        left, separator, right = clause.partition("=")
        if not separator:
            raise ValueError(f"not an equality: {clause!r}")
        if _term(left, row) != _term(right, row):
            return False
    return True


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    concatenates = variant == "vulnerable"

    #: The counter behind `/reports/live`. It exists to be noisy, so a reading
    #: that never established what "the same response" looks like has a route it
    #: can be wrong about.
    reads = [0]

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            parts = urlsplit(self.path)
            query = parse_qs(parts.query)
            if self.caller() is None:
                return
            if parts.path == "/reports":
                self.report(query.get("day", [""])[0])
            elif parts.path == "/reports/live":
                # Noise, identically on both variants: two identical requests
                # never return the same bytes.
                reads[0] += 1
                self.answer(200, {"reads": reads[0], "rows": len(ROWS)})
            elif parts.path == "/reports/search":
                # The decoy. The value comes back and nothing filters on it.
                self.answer(200, {"query": query.get("q", [""])[0], "rows": []})
            else:
                self.answer(404, NO_ROUTE)

        def report(self, day: str) -> None:
            """The subject. One line differs between the variants."""
            try:
                if concatenates:
                    # The defect: the caller's bytes become part of the
                    # expression, so a quote in them ends the literal and what
                    # follows is parsed as more expression.
                    matched = [row for row in ROWS if _matches("day = '" + day + "'", row)]
                else:
                    # The same filter, compared rather than parsed.
                    matched = [row for row in ROWS if str(row["day"]) == day]
            except ValueError:
                self.answer(400, MALFORMED)
                return
            # The subject does not reflect. `/reports/search` is where a value
            # comes back, and keeping them apart is what makes a difference here
            # a difference in what the filter selected rather than in what the
            # caller sent.
            self.answer(200, {"rows": matched})

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
