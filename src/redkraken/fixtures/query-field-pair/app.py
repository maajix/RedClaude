"""The query-field fixture, both variants, from one source.

An account list whose sort column is either whatever the caller names or one of
the two the route publishes. No expression is built and no quote means anything;
what the caller chooses here is an identifier, which is the part of a query an
ORM cannot bind.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit


VARIANTS = ("vulnerable", "secure")

#: The stored records. `risk_score` is the column no route returns and no
#: interface offers, and it is the one the vulnerable variant will order by.
ACCOUNTS = (
    {"id": 1, "name": "Umbra Ltd", "created": "2026-01-04", "risk_score": 71},
    {"id": 2, "name": "Barrow Co", "created": "2026-02-11", "risk_score": 12},
    {"id": 3, "name": "Calder AG", "created": "2026-03-02", "risk_score": 44},
)

#: What the route publishes as sortable, and what the secure variant enforces.
OFFERED = ("name", "created")

#: Every column the store holds, which is what the vulnerable variant will order
#: by. Stated rather than read off a record, so that the set a caller can reach
#: is in one place beside the set the route offers.
STORED = ("id", "name", "created", "risk_score")

#: The fields a caller ever sees back. `risk_score` is not among them on either
#: variant: the leak this class describes is in the order, not in the body.
SHOWN = ("id", "name", "created")

SESSIONS = {"s-alice-2d68": "alice"}
COOKIE = "session"

#: Fixed bodies on both variants, so that nothing here carries
#: `information_disclosure.error_detail` beside the class this pair declares.
UNAUTHENTICATED = {"error": "not authenticated"}
NO_ROUTE = {"error": "no such route"}


def _session(header: str | None) -> str | None:
    """The user a cookie header names, or None for every other header."""
    for part in (header or "").split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name == COOKIE:
            return SESSIONS.get(value)
    return None


def _shown(account: dict) -> dict:
    """One record, reduced to the fields a caller sees."""
    return {field: account[field] for field in SHOWN}


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    publishes_only = variant == "secure"

    #: The counter behind `/accounts/live`. It exists to be noisy.
    reads = [0]

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            parts = urlsplit(self.path)
            query = parse_qs(parts.query)
            if self.caller() is None:
                return
            if parts.path == "/accounts":
                self.accounts(query.get("sort", [""])[0])
            elif parts.path == "/accounts/live":
                # Noise, identically on both variants.
                reads[0] += 1
                self.answer(200, {"reads": reads[0], "accounts": len(ACCOUNTS)})
            elif parts.path == "/accounts/filter":
                # The decoy. The name comes back and the order never moves.
                self.answer(200, {
                    "field": query.get("field", [""])[0],
                    "accounts": [_shown(account) for account in ACCOUNTS],
                })
            else:
                self.answer(404, NO_ROUTE)

        def accounts(self, sort: str) -> None:
            """The subject. One lookup differs between the variants."""
            if publishes_only:
                # The defence: the column comes from the list the route
                # publishes, so a name outside it orders nothing.
                column = sort if sort in OFFERED else None
            else:
                # The defect: any column the store holds will do, including the
                # one nothing returns.
                column = sort if sort in STORED else None
            ordered = ACCOUNTS if column is None else sorted(ACCOUNTS, key=lambda a: a[column])
            self.answer(200, {
                "sortable": list(OFFERED),
                "accounts": [_shown(account) for account in ordered],
            })

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
