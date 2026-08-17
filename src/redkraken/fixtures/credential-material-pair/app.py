"""The credential-material fixture, both variants, from one source.

A single-page shell, the bundle it embeds, and a route that accepts a key. One
variant ships the key inside the bundle; the other ships the name of a place the
key will arrive from. Both ship a documented sample of the same shape.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit


VARIANTS = ("vulnerable", "secure")

#: The key `/api/reports` accepts. It is the same key on both variants, because
#: what differs between them is not what the service trusts but what the bundle
#: hands out.
KEY = "rk_live_7d41b9c0a2e64f18"

#: A string of exactly the key's shape that nothing accepts. It sits in a comment
#: in both bundles, which is what makes matching insufficient here.
SAMPLE = "rk_sample_000000000000"

HEADER = "X-Report-Key"

SHELL = (
    "<!doctype html><title>Reports</title>"
    '<div id="app"></div>'
    '<script src="/static/app.js"></script>'
)

#: The two bundles. The only line that differs is where `RK_REPORTS_KEY` comes
#: from; the comment above it is identical on both sides.
BUNDLE = """// Reports console.
// A report key looks like {sample}; ask an administrator for yours.
const RK_REPORTS_KEY = {source};

async function reports() {{
  const answer = await fetch("/api/reports", {{
    headers: {{ "{header}": RK_REPORTS_KEY }},
  }});
  document.getElementById("app").textContent = await answer.text();
}}

reports();
"""

REPORTS = {"reports": [{"day": "2026-04-02", "orders": 24}]}

NO_ROUTE = {"error": "no such route"}
REFUSED = {"error": "that key was not accepted"}


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    #: The defect: the key is a literal in a file anyone may fetch. The defence
    #: names a place instead, and that place is behind a session.
    source = f'"{KEY}"' if variant == "vulnerable" else "window.__rkConfig.reportsKey"
    bundle = BUNDLE.format(sample=SAMPLE, source=source, header=HEADER)

    #: The counter behind `/static/live.js`. It exists to be noisy.
    builds = [0]

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            path = urlsplit(self.path).path
            if path == "/":
                self.serve("text/html; charset=utf-8", SHELL)
            elif path == "/static/app.js":
                self.serve("application/javascript; charset=utf-8", bundle)
            elif path == "/static/live.js":
                # Noise, identically on both variants.
                builds[0] += 1
                self.serve("application/javascript; charset=utf-8",
                           f"export const build = {builds[0]};\n")
            elif path == "/api/reports":
                self.report()
            else:
                self.answer(404, NO_ROUTE)

        def report(self) -> None:
            """What a key is worth. Identical on both variants.

            The sample and no key at all get the same refusal, which is what
            lets a reading say the difference it saw was the key and not the
            request.
            """
            if self.headers.get(HEADER) == KEY:
                self.answer(200, REPORTS)
            else:
                self.answer(401, REFUSED)

        def serve(self, kind: str, text: str, status: int = 200) -> None:
            """Every response this fixture writes goes through here."""
            payload = text.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def answer(self, status: int, document: dict) -> None:
            self.serve("application/json", json.dumps(document), status)

        def log_message(self, format: str, *args: object) -> None:
            """Silent, for the reason the other fixtures' are."""

    return Fixture
