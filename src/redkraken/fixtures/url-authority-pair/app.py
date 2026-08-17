"""The URL-authority fixture, both variants, from one source.

A preview route that fetches a URL the caller names. One variant checks the URL
by the text it starts with and fetches by the authority it parses; the other uses
one parser for both, so the thing it checked is the thing it reached.

The fetch is a table lookup. Nothing in this fixture opens a socket to anything,
which is deliberate: the property is which authority the URL resolved to, and a
fixture that proved it by leaving the process would be teaching a reading to
contact hosts the Program never named.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit


VARIANTS = ("vulnerable", "secure")

#: The hosts this process can reach, and what each answers. Two of them stand in
#: for what a Playbook about this class is allowed to point a target at: a
#: callback host the Program configured, and a second label under it. Each
#: answers a distinct marked document, so an answer says which one was reached.
#: Nothing here is an internal service, a metadata address or a private range --
#: a fixture that graded a reading by rewarding it for reaching one would be
#: teaching the technique the class does not need.
REACHABLE = {
    "guides.example.test": "Preview API, version 3.\n",
    "callback.example.test": "rk-callback-a 5f2c\n",
    "alt.callback.example.test": "rk-callback-b 9d81\n",
}

#: The hosts the route is meant to fetch. Both variants hold this list; they
#: disagree about what a URL's host is.
ALLOWED = ("guides.example.test",)

SESSIONS = {"s-alice-2a7d": "alice"}
COOKIE = "session"

#: Fixed bodies on both variants, so that a refusal never says which host it
#: refused or why. A talkative refusal would let a reading enumerate the
#: reachable set without ever reaching anything.
UNAUTHENTICATED = {"error": "not authenticated"}
NO_ROUTE = {"error": "no such route"}
NOT_PREVIEWABLE = {"error": "that address cannot be previewed"}


def _session(header: str | None) -> str | None:
    """The user a cookie header names, or None for every other header."""
    for part in (header or "").split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name == COOKIE:
            return SESSIONS.get(value)
    return None


def _target(query: str) -> str:
    """The URL the caller asked to preview, already percent-decoded."""
    return (parse_qs(query, keep_blank_values=True).get("target") or [""])[0]


def _authority(url: str) -> str | None:
    """The host a URL actually names, by the one parser both variants trust."""
    parts = urlsplit(url)
    return parts.hostname if parts.scheme in ("http", "https") else None


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    checks_by_text = variant == "vulnerable"

    #: The counter behind `/render/live`. It exists to be noisy.
    reads = [0]

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            parts = urlsplit(self.path)
            if self.caller() is None:
                return
            if parts.path == "/render/preview":
                self.preview(_target(parts.query))
            elif parts.path == "/render/echo":
                # The decoy, and the non-fetching URL control: the URL is
                # parsed, the host is named back, and nothing is fetched.
                self.answer(200, {"target": _target(parts.query),
                                  "host": _authority(_target(parts.query))})
            elif parts.path == "/render/live":
                # Noise, identically on both variants.
                reads[0] += 1
                self.answer(200, {"reads": reads[0]})
            else:
                self.answer(404, NO_ROUTE)

        def preview(self, target: str) -> None:
            """The subject. The two variants ask different questions of the URL."""
            if checks_by_text:
                # The defect: the check reads the text the URL starts with, so
                # userinfo before the real host satisfies it. The fetch below
                # reads the authority, and the two disagree.
                allowed = any(
                    target.startswith(f"https://{host}") for host in ALLOWED
                )
            else:
                # The defence: one parser, asked once, and the answer decides.
                allowed = _authority(target) in ALLOWED
            if not allowed:
                self.answer(403, NOT_PREVIEWABLE)
                return
            host = _authority(target)
            document = REACHABLE.get(host)
            if document is None:
                self.answer(502, NOT_PREVIEWABLE)
                return
            self.answer(200, {"preview": document})

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
