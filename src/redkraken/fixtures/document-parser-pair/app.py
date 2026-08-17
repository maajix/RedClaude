"""The document-parser fixture, both variants, from one source.

An order intake that reads an XML body safely on both halves and then builds a
second document -- a lookup predicate -- out of one of its fields. One variant
concatenates the field's text into that predicate and one escapes it first.

The body reader recognises one element and no declarations at all, so nothing
here resolves an entity on either half. The predicate reader below is what the
class is about: it is the parser a caller's bytes reach.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit


VARIANTS = ("vulnerable", "secure")

#: The one element the body reader lifts. It matches text and nothing else, which
#: is why no doctype, entity or processing instruction means anything here.
REFERENCE = re.compile(r"<reference>([^<]*)</reference>")

#: The orders the predicate selects from, held in this process.
ORDERS = (
    {"ref": "A-1001", "state": "picked"},
    {"ref": "A-1002", "state": "shipped"},
)

#: Fixed bodies on both variants, so that nothing here carries
#: `information_disclosure.error_detail` beside the class this pair declares.
NO_ROUTE = {"error": "no such route"}
NO_REFERENCE = {"error": "a request carries one reference element"}


class Unreadable(Exception):
    """A predicate the reader stopped part-way through, and where it stopped.

    The offset is the whole of what this fixture's parser ever discloses, so it
    is an attribute rather than a message: a reading that cites it is citing a
    number the parser reported, not a sentence somebody wrote.
    """

    def __init__(self, offset: int) -> None:
        super().__init__(f"the predicate stopped being one predicate at {offset}")
        self.offset = offset


def _reference(body: bytes) -> str | None:
    """The text of `<reference>`, or None when the body carries none."""
    found = REFERENCE.search(body.decode("utf-8", "replace"))
    return found.group(1) if found else None


def _select(predicate: str) -> list[dict]:
    """Read `ref[@id='<literal>']` and return what it selects.

    Raises `Unreadable` carrying the offset it stopped at.
    """
    opened = predicate.find("[@id='")
    if not predicate.startswith("ref") or opened != len("ref"):
        raise Unreadable(len("ref"))
    rest = predicate[opened + len("[@id='"):]
    closed = rest.find("'")
    if closed < 0 or rest[closed:] != "']":
        # An unbalanced quote, or structure after the literal the grammar has no
        # room for. Either way the predicate is not one predicate any more.
        raise Unreadable(opened + len("[@id='") + max(closed, 0))
    wanted = rest[:closed]
    return [order for order in ORDERS if order["ref"] == wanted]


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    escapes = variant == "secure"

    #: The number behind `/services/ack`. It exists to be noisy.
    acknowledged = [0]

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            path = urlsplit(self.path).path
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            if path == "/services/ack":
                # Noise, identically on both variants.
                acknowledged[0] += 1
                self.answer(200, {"acknowledgement": acknowledged[0]})
                return
            reference = _reference(body)
            if reference is None:
                self.answer(400, NO_REFERENCE)
                return
            if path == "/services/orders":
                self.orders(reference)
            elif path == "/services/echo":
                # The decoy. The field comes back and no predicate is built.
                self.answer(200, {"reference": reference})
            else:
                self.answer(404, NO_ROUTE)

        def orders(self, reference: str) -> None:
            """The subject. What reaches the predicate reader differs."""
            if escapes:
                # The defence: the quote becomes a character in the literal, so
                # the predicate is one predicate whatever the field held.
                literal = reference.replace("&", "&amp;").replace("'", "&apos;")
            else:
                # The defect: the field's text is the predicate's text.
                literal = reference
            try:
                selected = _select("ref[@id='" + literal + "']")
            except Unreadable as stopped:
                self.answer(400, {"error": "the lookup could not be read",
                                  "offset": stopped.offset})
                return
            # The subject does not reflect. `/services/echo` is where a value
            # comes back, and keeping them apart is what makes a difference here
            # a difference in what the predicate selected rather than in what
            # the caller sent.
            self.answer(200, {"orders": selected})

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
