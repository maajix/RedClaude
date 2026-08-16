"""The workflow-order fixture, both variants, from one source.

A three-step checkout: fill the cart, pay, confirm. Both variants authenticate
the caller, refuse a payment before there is a cart, normalise every spelling of
a path the same way and answer the same redirect from the payment step; the only
difference is whether the confirmation step requires the payment step before it.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit


VARIANTS = ("vulnerable", "secure")

#: The flow, in the order the interface walks it. Published by `GET /checkout`,
#: because a sequence the target never stated is not an order a reading can say
#: was broken.
FLOW = ("cart", "pay", "confirm")

#: Where the payment step sends the caller next. This is what makes the
#: confirmation step a step rather than a route that happens to come later: the
#: flow itself names its own successor.
NEXT = "/checkout/confirm"

SESSIONS = {"s-alice-4f2c": "alice"}
COOKIE = "session"

#: Fixed bodies, so that nothing here carries
#: `information_disclosure.error_detail` beside the class this pair declares.
UNAUTHENTICATED = {"error": "not authenticated"}
NO_ROUTE = {"error": "no such route"}
NOT_AN_OBJECT = {"error": "a request carries a JSON object"}
OUT_OF_ORDER = {"error": "an earlier step of this checkout has not been taken"}


def _session(header: str | None) -> str | None:
    """The user a cookie header names, or None for every other header."""
    for part in (header or "").split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name == COOKIE:
            return SESSIONS.get(value)
    return None


def _route(path: str) -> str:
    """One spelling per route, on both variants.

    A doubled separator, a `.` segment, a trailing slash and a mixed-case
    segment all arrive here as the same route. That is deliberate: the pair
    grades an ordering rule, and a normalisation the two variants disagreed
    about would put a second class into the fixture that nothing declares.
    """
    segments = [segment for segment in path.lower().split("/") if segment not in ("", ".")]
    return "/" + "/".join(segments)


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    requires_payment = variant == "secure"

    #: The steps this checkout has taken, rebuilt per process so that the
    #: pristine state is an empty flow.
    taken: list[str] = []

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            if _route(urlsplit(self.path).path) != "/checkout":
                self.answer(404, NO_ROUTE)
                return
            if self.caller() is None:
                return
            self.answer(200, self.outcome())

        def do_POST(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            route = _route(urlsplit(self.path).path)
            document = self.document()
            if document is None:
                return
            if self.caller() is None:
                return
            if route == "/checkout/cart":
                self.take("cart")
            elif route == "/checkout/pay":
                self.pay()
            elif route == "/checkout/confirm":
                self.confirm()
            else:
                self.answer(404, NO_ROUTE)

        def do_DELETE(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            """The route a reading unwinds through, so one flow can be finished."""
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            if _route(urlsplit(self.path).path) != "/checkout":
                self.answer(404, NO_ROUTE)
                return
            if self.caller() is None:
                return
            taken.clear()
            self.answer(200, self.outcome())

        def pay(self) -> None:
            """Payment, which both variants refuse before there is a cart.

            Enforced identically on the two variants so that the difference
            between them sits at one step. The `303` is what a recon pass reads
            as this flow naming its own next step.
            """
            if "cart" not in taken:
                self.answer(409, OUT_OF_ORDER)
                return
            self.take("pay", status=303, location=NEXT)

        def confirm(self) -> None:
            if requires_payment and "pay" not in taken:
                # The whole of the difference between the two variants. The
                # vulnerable one confirms a checkout nobody paid for, having
                # established that the caller holds a valid session.
                self.answer(409, OUT_OF_ORDER)
                return
            self.take("confirm")

        def take(self, step: str, status: int = 200, location: str | None = None) -> None:
            if step not in taken:
                taken.append(step)
            self.answer(status, self.outcome(), location=location)

        def outcome(self) -> dict:
            """The authoritative outcome, which is what the claim is read from."""
            return {
                "flow": list(FLOW),
                "taken": list(taken),
                "confirmed": FLOW[-1] in taken,
            }

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
            """The authenticated user, or None with a `401` already written.

            Both variants, so that an outcome which did not move cannot be
            explained by a session that was not valid.
            """
            caller = _session(self.headers.get("Cookie"))
            if caller is None:
                self.answer(401, UNAUTHENTICATED)
            return caller

        def answer(self, status: int, document: dict, location: str | None = None) -> None:
            payload = json.dumps(document).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            if location is not None:
                self.send_header("Location", location)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            """Silent, for the reason the other fixtures' are."""

    return Fixture
