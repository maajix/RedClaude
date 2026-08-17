"""The undeclared-field fixture, both variants, from one source.

An orders route beside the contract that says what an order is. One variant
serialises the stored record whole; the other serialises the fields the contract
declares.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit


VARIANTS = ("vulnerable", "secure")

#: The published contract. `_links` is in it on purpose: a field that reads like
#: an internal name and is declared anyway is the decoy this pair needs.
DECLARED = ("id", "placed", "total", "status", "_links")

CONTRACT = {
    "openapi": "3.1.0",
    "info": {"title": "Orders", "version": "2.0.0"},
    "paths": {
        "/api/v2/orders": {
            "get": {
                "responses": {
                    "200": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            name: {"type": "string"}
                                            for name in DECLARED
                                        },
                                    },
                                }
                            }
                        }
                    }
                }
            }
        }
    },
}

#: What the store holds. Two fields are not in the contract, and they are the
#: two a reading is meant to find.
RECORDS = [
    {
        "id": "o-4181",
        "placed": "2026-04-02",
        "total": "412.00",
        "status": "shipped",
        "_links": {"self": "/api/v2/orders/o-4181"},
        "internal_margin": "0.31",
        "fraud_score": 12,
    },
    {
        "id": "o-4182",
        "placed": "2026-04-03",
        "total": "88.50",
        "status": "packing",
        "_links": {"self": "/api/v2/orders/o-4182"},
        "internal_margin": "0.44",
        "fraud_score": 3,
    },
]

SESSIONS = {"s-alice-5d16": "alice"}
COOKIE = "session"

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
    serialises_the_record = variant == "vulnerable"

    #: The counter behind `/api/v2/live`. It exists to be noisy.
    reads = [0]

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            path = urlsplit(self.path).path
            if path == "/api/v2/openapi.json":
                # The contract is public, as a contract is. It says the same
                # thing on both variants: only one side keeps to it.
                self.answer(200, CONTRACT)
                return
            if self.caller() is None:
                return
            if path == "/api/v2/orders":
                self.orders()
            elif path == "/api/v2/live":
                # Noise, identically on both variants.
                reads[0] += 1
                self.answer(200, {"reads": reads[0]})
            else:
                self.answer(404, NO_ROUTE)

        def orders(self) -> None:
            """The subject. One line differs between the variants."""
            if serialises_the_record:
                # The defect: whatever the record holds is what goes out.
                self.answer(200, {"orders": RECORDS})
                return
            # The defence: the contract is the projection, applied here.
            self.answer(200, {"orders": [
                {name: record[name] for name in DECLARED} for record in RECORDS
            ]})

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
