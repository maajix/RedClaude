"""The markup fixture, both variants, from one source.

The reflection is on both variants and only the escaping differs. A run that
reports `injection.markup` because the search term came back has reported what
both halves do, which is the point: the class is about what the parser built,
not about what the body contains.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixture's source gives.
"""

from __future__ import annotations

from html import escape
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit


VARIANTS = ("vulnerable", "secure")

#: Static rows, compared in Python. The term reaches no query language, no
#: template engine and no shell, so the only class this fixture contains is the
#: one its ground truth declares.
ROWS = ("quarterly report", "quarterly forecast", "onboarding checklist")

PAGE = """<!doctype html>
<html><head><title>search</title></head>
<body>
<form method="get" action="/search">
<input name="q" id="q" value="{value}">
<button id="go" type="submit">search</button>
</form>
<div id="result">{result}</div>
<ul id="rows">{rows}</ul>
</body></html>
"""


def _rows(term: str) -> str:
    found = [row for row in ROWS if term.lower() in row] if term else []
    return "".join(f"<li>{escape(row)}</li>" for row in found)


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    raw = variant == "vulnerable"

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            parts = urlsplit(self.path)
            if parts.path != "/search":
                self.answer(404, "<!doctype html><html><body>no such route</body></html>")
                return
            term = (parse_qs(parts.query).get("q") or [""])[0]
            # The one difference between the variants, and it is the whole
            # fixture: the same value, in the same place, escaped or not. The
            # form field is escaped on both halves so that the difference is one
            # sink rather than two.
            shown = term if raw else escape(term)
            self.answer(
                200,
                PAGE.format(value=escape(term), result=shown, rows=_rows(term)),
            )

        def answer(self, status: int, document: str) -> None:
            payload = document.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            # Identical on both variants. A Content Security Policy that differed
            # would make one half refuse a script the other ran, which is a
            # second class and a second difference.
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            """Silent, for the reason the other fixture's is."""

    return Fixture
