"""The state-transition fixture, both variants, from one source.

An order API where cancelling is allowed while an order is open and forbidden
once it has shipped. Both variants authenticate the caller and both check the
order's owner, so the ownership question is settled the same way on each; the
only difference is whether the order's own state is consulted before the
cancellation is applied.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit


VARIANTS = ("vulnerable", "secure")

#: order reference -> (owner, starting state). Two of `alice`'s orders in two
#: states, because a transition reading needs both ends of one; `bob`'s is the
#: foreign-owner control and nothing here ever moves it.
ORDERS = {
    "ord-7c2a": ("alice", "open"),
    "ord-3b91": ("alice", "shipped"),
    "ord-5e08": ("bob", "open"),
}

#: The states a cancellation is allowed from, published by `GET /orders` on both
#: variants. An invariant the target does not state is one a reading would have
#: to guess, and a guessed invariant is not evidence of anything.
CANCELLABLE = ("open",)

#: session cookie -> user. Opaque and fixed, like the other pairs': the sessions
#: are how the caller is told apart and not something this fixture is asking a
#: question about.
SESSIONS = {
    "s-alice-4f2c": "alice",
    "s-bob-9d17": "bob",
}

COOKIE = "session"

#: Fixed bodies, so that nothing here carries
#: `information_disclosure.error_detail` beside the class this pair declares.
#: The refusal below names no state for the same reason: what the caller may
#: read about an order is what `GET /orders/{reference}` returns.
UNAUTHENTICATED = {"error": "not authenticated"}
FORBIDDEN = {"error": "forbidden"}
NOT_FOUND = {"error": "no such order"}
NO_ROUTE = {"error": "no such route"}
NOT_CANCELLABLE = {"error": "this order is not in a state a cancellation is allowed from"}


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
    checks_state = variant == "secure"

    #: The state a run moves, rebuilt per process: the fixture is restarted per
    #: repeat, and a repeat that inherited the previous one's cancellations
    #: would be measuring the harness.
    state = {reference: start for reference, (_, start) in ORDERS.items()}

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            path = urlsplit(self.path).path
            caller = self.caller()
            if caller is None:
                return
            if path == "/orders":
                self.answer(200, {
                    "orders": [
                        self.view(reference)
                        for reference, (owner, _) in ORDERS.items()
                        if owner == caller
                    ],
                    "cancellable_from": list(CANCELLABLE),
                })
                return
            reference = self.named(path, "")
            if reference is None:
                self.answer(404, NO_ROUTE)
            elif self.reachable(reference, caller):
                self.answer(200, self.view(reference))

        def do_POST(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            reference = self.named(urlsplit(self.path).path, "/cancel")
            caller = self.caller()
            if caller is None:
                return
            if reference is None:
                self.answer(404, NO_ROUTE)
                return
            if not self.reachable(reference, caller):
                return
            if checks_state and state[reference] not in CANCELLABLE:
                # The whole of the difference between the two variants. The
                # vulnerable one falls through to the write, having established
                # who the caller is and that the order is theirs.
                self.answer(409, NOT_CANCELLABLE)
                return
            state[reference] = "cancelled"
            self.answer(200, self.view(reference))

        def named(self, path: str, suffix: str) -> str | None:
            """The order reference a route names, or None if it names no order."""
            if not path.startswith("/orders/") or not path.endswith(suffix):
                return None
            reference = path[len("/orders/"): len(path) - len(suffix)]
            if not reference or "/" in reference:
                return None
            return reference

        def caller(self) -> str | None:
            """The authenticated user, or None with a `401` already written.

            Both variants. A refusal under the second Identity means nothing
            unless a working session is told apart from a broken one, which is
            what makes the controls in this pair evaluable.
            """
            caller = _session(self.headers.get("Cookie"))
            if caller is None:
                self.answer(401, UNAUTHENTICATED)
            return caller

        def reachable(self, reference: str, caller: str) -> bool:
            """Whether this caller may see this order, answering if they may not.

            The nonexistent and foreign-owner controls, identical on both
            variants: an order nobody has answers `404` and an order belonging
            to somebody else answers `403`, so a run holding a real reference
            can tell which of the two it is looking at.
            """
            if reference not in ORDERS:
                self.answer(404, NOT_FOUND)
                return False
            if ORDERS[reference][0] != caller:
                self.answer(403, FORBIDDEN)
                return False
            return True

        def view(self, reference: str) -> dict:
            """The authoritative after-state, which is what the claim is read from."""
            return {
                "reference": reference,
                "owner": ORDERS[reference][0],
                "state": state[reference],
            }

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
