"""The object-graph fixture, both variants, from one source.

A preferences-restore route that takes a serialised object graph. One variant
reads the type name out of the graph and constructs whatever it names; the other
reads the graph as data into a shape it decided in advance.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import base64
import binascii
import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit


VARIANTS = ("vulnerable", "secure")

#: The wire format: `rk1:<type>:<json>`, base64 encoded. That is as much of a
#: serialisation as this class needs -- a type name travelling beside the state
#: is what every real object-graph format carries, and it is what makes the type
#: the caller's choice rather than the route's.
PREFIX = "rk1:"

#: What the vulnerable variant is willing to construct. `AuditProbe` is
#: registered and is not part of any preferences document the client stores,
#: which is what makes it a type a caller can reach and a client never sends.
CONSTRUCTORS = {
    "Preferences": ("theme", "density"),
    "Cart": ("items",),
    "AuditProbe": ("probe",),
}

#: The shape the secure variant reads into, decided here rather than by the blob.
SESSION_SHAPE = ("theme", "density")

SESSIONS = {"s-alice-3b90": "alice"}
COOKIE = "session"

#: Fixed bodies on both variants, so that nothing here carries
#: `information_disclosure.error_detail` beside the class this pair declares. In
#: particular a type name the route will not construct is never quoted back: the
#: signal in this pair is a document that came back, not a sentence about one.
UNAUTHENTICATED = {"error": "not authenticated"}
NO_ROUTE = {"error": "no such route"}
UNREADABLE = {"error": "saved preferences were not readable"}


def _session(header: str | None) -> str | None:
    """The user a cookie header names, or None for every other header."""
    for part in (header or "").split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name == COOKIE:
            return SESSIONS.get(value)
    return None


def _graph(body: bytes) -> tuple[str, dict] | None:
    """The type name and the state a blob carries, or None if it is not one."""
    try:
        decoded = base64.b64decode(body, validate=True).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return None
    if not decoded.startswith(PREFIX):
        return None
    name, separator, state = decoded[len(PREFIX):].partition(":")
    if not separator:
        return None
    try:
        loaded = json.loads(state)
    except json.JSONDecodeError:
        return None
    return (name, loaded) if isinstance(loaded, dict) else None


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    reads_the_shape = variant == "secure"

    #: The counter behind `/preferences/live`. It exists to be noisy.
    restores = [0]

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            path = urlsplit(self.path).path
            if self.caller() is None:
                return
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            graph = _graph(body)
            if path == "/preferences/restore":
                self.restore(graph)
            elif path == "/preferences/echo":
                # The decoy. The type name comes back and nothing is built from
                # it: the fields listed are the ones the request itself carried.
                if graph is None:
                    self.answer(400, UNREADABLE)
                else:
                    named, state = graph
                    self.answer(200, {"type": named, "fields": sorted(state)})
            else:
                self.answer(404, NO_ROUTE)

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            if self.caller() is None:
                return
            if urlsplit(self.path).path == "/preferences/live":
                # Noise, identically on both variants.
                restores[0] += 1
                self.answer(200, {"restores": restores[0]})
            else:
                self.answer(404, NO_ROUTE)

        def restore(self, graph: tuple[str, dict] | None) -> None:
            """The subject. One lookup differs between the variants."""
            if graph is None:
                self.answer(400, UNREADABLE)
                return
            named, state = graph
            if reads_the_shape:
                # The defence: the type name is data about the caller's client,
                # not a constructor to call. What comes back is the one shape
                # this route stores, whatever the blob said it was.
                self.answer(200, {
                    "restored": "preferences",
                    "state": {field: state.get(field) for field in SESSION_SHAPE},
                })
                return
            # The defect: the blob names the type and the route builds it.
            fields = CONSTRUCTORS.get(named)
            if fields is None:
                self.answer(400, UNREADABLE)
                return
            self.answer(200, {
                "restored": named,
                "state": {field: state.get(field) for field in fields},
            })

        def caller(self) -> str | None:
            """The authenticated user, or None with a `401` already written.

            The route is behind a session because saved preferences belong to
            somebody, and because the reading that grades it compares two
            restores that have to have been the same caller's.
            """
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
