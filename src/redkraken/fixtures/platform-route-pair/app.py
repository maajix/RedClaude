"""The parallel-route fixture, both variants, from one source.

An application list route with a session check and a status filter, beside the
content platform's own read route over the same two records. One variant serves
the platform's route to anybody; the other puts it behind the same check and the
same filter.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit


VARIANTS = ("vulnerable", "secure")

SESSIONS = {"s-alice-7c21": "alice"}
COOKIE = "session"

#: The store both doors read. `pricing-change-2027` is the record the
#: application's own route never returns, which is what makes the platform route
#: serving it a leak rather than a second copy of a public page.
ARTICLES = (
    {"slug": "quarterly-outlook", "title": "Quarterly outlook", "status": "published"},
    {"slug": "pricing-change-2027", "title": "Pricing change", "status": "draft"},
)

#: Fixed bodies on both variants, so that nothing here carries
#: `information_disclosure.error_detail` beside the class this pair declares. In
#: particular no refusal names the platform, its version or the route that would
#: have answered.
UNAUTHENTICATED = {"error": "not authenticated"}
NO_ROUTE = {"error": "no such route"}


def _session(header: str | None) -> str | None:
    """The user a cookie header names, or None for every other header."""
    for part in (header or "").split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name == COOKIE:
            return SESSIONS.get(value)
    return None


def _published() -> list[dict]:
    """What the application's own route is willing to show."""
    return [dict(article) for article in ARTICLES if article["status"] == "published"]


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    platform_checks_the_session = variant == "secure"

    #: The counter behind `/cms/rest/status`. It exists to be noisy.
    reads = [0]

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            path = urlsplit(self.path).path
            if path == "/api/articles":
                self.application_list()
            elif path == "/cms/rest/content":
                self.platform_list()
            elif path == "/cms/rest/health":
                # The decoy. A platform route that exists, answers a caller
                # holding nothing, and carries no records at all.
                self.answer(200, {"platform": "cms", "items": []})
            elif path == "/cms/rest/status":
                # Noise, identically on both variants.
                reads[0] += 1
                self.answer(200, {"platform": "cms", "reads": reads[0]})
            else:
                self.answer(404, NO_ROUTE)

        def application_list(self) -> None:
            """The application's own door. Identical on both variants."""
            if _session(self.headers.get("Cookie")) is None:
                self.answer(401, UNAUTHENTICATED)
                return
            self.answer(200, {"articles": _published()})

        def platform_list(self) -> None:
            """The platform's door. The one thing the variants disagree about."""
            if platform_checks_the_session:
                # The defence: the same check and the same filter the
                # application's own route applies, on the store's second door.
                if _session(self.headers.get("Cookie")) is None:
                    self.answer(401, UNAUTHENTICATED)
                    return
                self.answer(200, {"articles": _published()})
                return
            # The defect: the platform's route reads the store directly, with no
            # session and no status filter, and hands back everything in it.
            self.answer(200, {"articles": [dict(article) for article in ARTICLES]})

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
