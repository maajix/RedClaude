"""The error-detail fixture, both variants, from one source.

The out-of-class negative. Nothing here is about a caller, an object or a
session, so a Playbook of the authorization family that fires on this fixture is
reporting its class against a route that cannot carry it.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixture's source gives.
"""

from __future__ import annotations

import json
import traceback
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit


VARIANTS = ("vulnerable", "secure")

#: Static rows. The term is compared against them in Python and reaches no query
#: language, no template and no shell, so the only class this fixture contains is
#: the one its ground truth declares.
ROWS = (
    {"id": 1, "title": "quarterly report"},
    {"id": 2, "title": "quarterly forecast"},
    {"id": 3, "title": "onboarding checklist"},
)

DEFAULT_LIMIT = 10
BAD_REQUEST = {"error": "limit must be an integer"}


def _matches(term: str, limit: int) -> list[dict]:
    found = [row for row in ROWS if term.lower() in row["title"]]
    return found[:limit]


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    tells = variant == "vulnerable"

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            parts = urlsplit(self.path)
            if parts.path != "/search":
                self.answer(404, {"error": "no such route"})
                return
            query = parse_qs(parts.query)
            term = (query.get("q") or [""])[0]
            raw = (query.get("limit") or [str(DEFAULT_LIMIT)])[0]
            try:
                limit = int(raw)
            except ValueError:
                # The one difference between the variants, and it is the whole
                # fixture: the same failure, told two ways.
                if tells:
                    self.answer(500, {"error": traceback.format_exc()})
                else:
                    self.answer(400, BAD_REQUEST)
                return
            self.answer(200, {"q": term, "rows": _matches(term, limit)})

        def answer(self, status: int, document: dict) -> None:
            payload = json.dumps(document).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            """Silent, for the reason the other fixture's is."""

    return Fixture
