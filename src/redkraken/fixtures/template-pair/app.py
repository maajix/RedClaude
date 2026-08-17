"""The template fixture, both variants, from one source.

A preview route whose message is either pasted into the template source or passed
to the renderer as a value. The engine below evaluates one arithmetic form and
substitutes one name; it is small because the class turns on which side of the
renderer the caller's bytes arrive on.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit


VARIANTS = ("vulnerable", "secure")

#: The one expression form the engine evaluates, and the one it substitutes.
EXPRESSION = re.compile(r"\{\{\s*(?:(\d+)\s*\*\s*(\d+)|([a-z_]+))\s*\}\}")

#: The fixed source the secure variant renders, with the message as a value.
SOURCE = "Hello, {{ name }}. Your note: {{ message }}"

SESSIONS = {"s-alice-5c17": "alice"}
COOKIE = "session"

#: Fixed bodies on both variants, so that nothing here carries
#: `information_disclosure.error_detail` beside the class this pair declares.
UNAUTHENTICATED = {"error": "not authenticated"}
NO_ROUTE = {"error": "no such route"}
NOT_AN_OBJECT = {"error": "a request carries a JSON object"}


def _session(header: str | None) -> str | None:
    """The user a cookie header names, or None for every other header."""
    for part in (header or "").split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name == COOKIE:
            return SESSIONS.get(value)
    return None


def _render(source: str, values: dict[str, str]) -> str:
    """Evaluate every expression in a source against a set of values.

    An unknown name renders as nothing, which is what a forgiving engine does and
    what keeps a malformed template from erroring instead of rendering.
    """
    def one(match: re.Match[str]) -> str:
        left, right, name = match.groups()
        if name is not None:
            return values.get(name, "")
        return str(int(left) * int(right))

    return EXPRESSION.sub(one, source)


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    concatenates = variant == "vulnerable"

    #: The draft number behind `/preview/live`. It exists to be noisy.
    drafts = [0]

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            path = urlsplit(self.path).path
            document = self.document()
            if document is None:
                return
            if self.caller() is None:
                return
            message = str(document.get("message", ""))
            if path == "/preview":
                self.preview(message)
            elif path == "/preview/live":
                # Noise, identically on both variants.
                drafts[0] += 1
                self.answer(200, {"draft": drafts[0]})
            elif path == "/preview/quote":
                # The decoy. The message comes back and no engine sees it.
                self.answer(200, {"quoted": message})
            else:
                self.answer(404, NO_ROUTE)

        def preview(self, message: str) -> None:
            """The subject. Which side of the renderer the message arrives on."""
            if concatenates:
                # The defect: the message becomes template source, so an
                # expression written in it is an expression the engine runs.
                rendered = _render("Hello, {{ name }}. Your note: " + message, {"name": "alice"})
            else:
                # The same greeting, with the message passed in as a value.
                rendered = _render(SOURCE, {"name": "alice", "message": message})
            # Both variants reflect, which is what makes the probe's own output
            # the only thing that separates them.
            self.answer(200, {"submitted": message, "preview": rendered})

        def document(self) -> dict | None:
            length = int(self.headers.get("Content-Length") or 0)
            try:
                document = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                document = None
            if not isinstance(document, dict):
                self.answer(400, NOT_AN_OBJECT)
                return None
            return document

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
