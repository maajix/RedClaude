"""The quantity-or-price fixture, both variants, from one source.

A cart API that publishes its own prices and its own quantity rule, and computes
the total itself. Both variants authenticate the caller, refuse a product that
is not in the catalogue and refuse a quantity that is not a whole number; the
only difference is whether the published quantity rule is enforced before the
line is stored.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit


VARIANTS = ("vulnerable", "secure")

#: sku -> unit price in minor units. Published by `GET /cart`, because a reading
#: that cannot say what the price should have been cannot say the total it got
#: is wrong.
CATALOGUE = {
    "sku-desk": 22000,
    "sku-lamp": 4500,
}

#: The quantity rule, published beside the prices and enforced by one variant.
MINIMUM = 1
MAXIMUM = 10

SESSIONS = {"s-alice-4f2c": "alice"}
COOKIE = "session"

#: Fixed bodies, so that nothing here carries
#: `information_disclosure.error_detail` beside the class this pair declares.
UNAUTHENTICATED = {"error": "not authenticated"}
NOT_FOUND = {"error": "no such product"}
NO_ROUTE = {"error": "no such route"}
NOT_AN_OBJECT = {"error": "a request carries a JSON object"}
NOT_A_WHOLE_NUMBER = {"error": "quantity is a whole number"}
OUTSIDE_THE_RULE = {"error": "quantity is outside the range this cart accepts"}


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
    enforces = variant == "secure"

    #: sku -> quantity, rebuilt per process. The cart starts empty so that the
    #: pristine total is zero and every reading below is a difference from it.
    lines: dict[str, int] = {}

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            if urlsplit(self.path).path != "/cart":
                self.answer(404, NO_ROUTE)
                return
            if self.caller() is None:
                return
            self.answer(200, self.cart())

        def do_POST(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            path = urlsplit(self.path).path
            document = self.document()
            if document is None:
                return
            if self.caller() is None:
                return
            if path != "/cart/items":
                self.answer(404, NO_ROUTE)
                return
            sku = document.get("sku")
            if sku not in CATALOGUE:
                self.answer(404, NOT_FOUND)
                return
            quantity = document.get("quantity")
            if not isinstance(quantity, int) or isinstance(quantity, bool):
                # Both variants. A body that is not a quantity at all is a
                # malformed request rather than a quantity the rules forbid.
                self.answer(400, NOT_A_WHOLE_NUMBER)
                return
            if enforces and not MINIMUM <= quantity <= MAXIMUM:
                # The whole of the difference between the two variants: the
                # vulnerable one publishes this rule and then stores whatever
                # arrived, so the total it computes is a number the rule forbids.
                self.answer(400, OUTSIDE_THE_RULE)
                return
            lines[str(sku)] = lines.get(str(sku), 0) + quantity
            self.answer(200, self.cart())

        def do_DELETE(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            """The removal route a reading cleans up through."""
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            path = urlsplit(self.path).path
            if self.caller() is None:
                return
            if not path.startswith("/cart/items/"):
                self.answer(404, NO_ROUTE)
                return
            sku = path[len("/cart/items/"):]
            if sku not in CATALOGUE:
                self.answer(404, NOT_FOUND)
                return
            lines.pop(sku, None)
            self.answer(200, self.cart())

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

            Both variants, so that a total which did not move under the variant
            cannot be explained by a session that was not valid.
            """
            caller = _session(self.headers.get("Cookie"))
            if caller is None:
                self.answer(401, UNAUTHENTICATED)
            return caller

        def cart(self) -> dict:
            """The authoritative total, which is the only place the claim lives.

            Computed here on every read rather than carried alongside the lines:
            a total stored beside the quantities could disagree with them, and
            then the fixture would hold a second defect nobody declared.
            """
            return {
                "items": [
                    {"sku": sku, "quantity": quantity, "unit_price": CATALOGUE[sku],
                     "line_total": CATALOGUE[sku] * quantity}
                    for sku, quantity in lines.items()
                ],
                "total": sum(CATALOGUE[sku] * quantity for sku, quantity in lines.items()),
                "rules": {"minimum_quantity": MINIMUM, "maximum_quantity": MAXIMUM},
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
