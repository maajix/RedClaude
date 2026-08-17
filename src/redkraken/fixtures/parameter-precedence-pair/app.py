"""The parameter-precedence fixture, both variants, from one source.

An export route that takes one parameter name from two carriers. One variant
checks the value the query string carried and builds from the value the body
carried; the other resolves the name once and uses that answer for both.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit


VARIANTS = ("vulnerable", "secure")

#: The formats this application offers, which is what the check is written
#: against. `xml` is not among them: the builder below can render it, and no
#: request that was checked properly ever asks it to.
OFFERED = ("csv", "json")

#: The authority every absolute link is built from, on both variants, whatever
#: `X-Forwarded-Host` says. A caller-supplied authority reaching a link is a
#: different question with different evidence, and this fixture answers it in
#: the negative on both halves so that a reading which reports it has reported
#: something neither variant does.
AUTHORITY = "https://orders.acme.example"

#: What every export contains, whichever way it is serialised. Fixed, so the
#: only thing that moves between two sends is the identifier.
ORDERS = (
    {"id": "ord-3312", "total": "48.00"},
    {"id": "ord-3319", "total": "12.50"},
)

NO_ROUTE = {"error": "no such route"}


def _first(carriers: tuple[dict[str, list[str]], ...], name: str) -> str | None:
    """The name's first occurrence, reading the carriers in the order given.

    The two halves of the subject differ in nothing but that order, which is
    what a parameter-precedence defect is: one name, two readers, two answers.
    """
    for carrier in carriers:
        if carrier.get(name):
            return carrier[name][0]
    return None


def _as_csv() -> tuple[str, bytes]:
    rows = ["id,total", *(f"{order['id']},{order['total']}" for order in ORDERS)]
    return "text/csv", ("\r\n".join(rows) + "\r\n").encode("utf-8")


def _as_json() -> tuple[str, bytes]:
    return "application/json", json.dumps({"orders": [dict(order) for order in ORDERS]}).encode("utf-8")


def _as_xml() -> tuple[str, bytes]:
    parts = "".join(f"<order id=\"{order['id']}\" total=\"{order['total']}\"/>" for order in ORDERS)
    return "application/xml", f"<orders>{parts}</orders>".encode("utf-8")


#: What the builder knows how to serialise, which is not the same list the check
#: is written against, and that gap is the whole point of this fixture. A builder
#: asked for something it cannot render falls back to the first offered format.
RENDERERS = {"csv": _as_csv, "json": _as_json, "xml": _as_xml}


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    resolves_once = variant == "secure"

    #: The exports made so far, keyed by identifier, and the counter that names
    #: them. Deterministic, so a reading that repeats an arm can say which
    #: artefact belongs to which receipt.
    exports: dict[str, tuple[str, bytes]] = {}
    made = [0]

    #: The counter behind `/metrics/live`. Deliberately not on the subject.
    scrapes = [0]

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            path = urlsplit(self.path).path
            if path == "/metrics/live":
                # Noise, identically on both variants.
                scrapes[0] += 1
                self.answer(200, {"scrapes": scrapes[0]})
                return
            if path.startswith("/exports/"):
                self.artefact(path.removeprefix("/exports/"))
                return
            self.answer(404, NO_ROUTE)

        def do_POST(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            split = urlsplit(self.path)
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode("utf-8", "replace")
            query = parse_qs(split.query, keep_blank_values=True)
            form = parse_qs(body, keep_blank_values=True)
            if split.path == "/orders/export":
                self.export(query, form)
            elif split.path == "/orders/report":
                self.report(query, form)
            else:
                self.answer(404, NO_ROUTE)

        def export(self, query: dict[str, list[str]], form: dict[str, list[str]]) -> None:
            """The subject. One name, two carriers, and two readers of it."""
            checked = _first((query, form), "format")
            # The defect is here and it is one line: the vulnerable variant hands
            # the builder a second resolution of the same name, taken from the
            # carriers in the other order, so what was checked and what was used
            # need not be the same string.
            built = checked if resolves_once else _first((form, query), "format")
            if checked is None:
                self.answer(400, {"error": "format is required"})
                return
            if checked not in OFFERED:
                # The check the application actually has, and it is correct as
                # far as it goes. On both variants, a request whose only
                # occurrence of the name is an unoffered format is refused here.
                self.answer(400, {"error": "unsupported format", "format": checked, "offered": list(OFFERED)})
                return
            made[0] += 1
            identifier = f"exp-{made[0]:04d}"
            exports[identifier] = RENDERERS.get(built or "", RENDERERS[OFFERED[0]])()
            self.answer(
                201,
                # The receipt names what was checked, because that is the value
                # the half of the application that answers the caller holds.
                {"export": identifier, "format": checked, "link": f"{AUTHORITY}/exports/{identifier}"},
                {"Location": f"/exports/{identifier}"},
            )

        def report(self, query: dict[str, list[str]], form: dict[str, list[str]]) -> None:
            """The control: a route that refuses a repeated name outright."""
            for name in sorted(set(query) | set(form)):
                if len(query.get(name, [])) + len(form.get(name, [])) > 1:
                    self.answer(400, {"error": "duplicate parameter", "name": name})
                    return
            self.answer(201, {"report": "rep-0001", "link": f"{AUTHORITY}/reports/rep-0001"})

        def artefact(self, identifier: str) -> None:
            """What the export was actually built as, served as what it is."""
            if identifier not in exports:
                self.answer(404, NO_ROUTE)
                return
            content_type, payload = exports[identifier]
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def answer(self, status: int, document: dict, headers: dict[str, str] | None = None) -> None:
            payload = json.dumps(document).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            """Silent, for the reason the other fixtures' are."""

    return Fixture
