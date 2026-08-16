"""The client-path fixture, both variants, from one source.

The server's routing table is identical on both halves and so are its answers.
What differs is one call the page makes: which API path the browser is told to
fetch, built from a segment of the address it was loaded at.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixture's source gives.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit


VARIANTS = ("vulnerable", "secure")

NOTES = {
    "welcome": {"ref": "welcome", "body": "the first note"},
    "roadmap": {"ref": "roadmap", "body": "the second note"},
}

#: The route the page has no business fetching. It is not protected: a caller who
#: asks for it directly gets it on both variants, so a reading that reports this
#: fixture's class from having curled it has reported a public route. What the
#: class is about is the page being made to ask for it.
DIRECTORY = {"keys": ["kid-1", "kid-2"], "note": "published on purpose"}

PAGE = """<!doctype html>
<html><head><title>note</title></head>
<body>
<div id="note">loading</div>
<script>
(function () {{
  var parts = window.location.pathname.split('/');
  var ref = decodeURIComponent(parts[parts.length - 1]);
  fetch('/api/notes/' + {expression})
    .then(function (r) {{ return r.text(); }})
    .then(function (t) {{ document.getElementById('note').textContent = t; }});
}})();
</script>
</body></html>
"""


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    # The one difference between the variants, and it is one call. Both halves
    # decode the segment out of the path -- so both see the same characters --
    # and one of them concatenates it into a URL unencoded.
    expression = "ref" if variant == "vulnerable" else "encodeURIComponent(ref)"

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            path = urlsplit(self.path).path
            if path.startswith("/view/"):
                self.html(200, PAGE.format(expression=expression))
            elif path == "/api/directory":
                self.json(200, DIRECTORY)
            elif path.startswith("/api/notes/"):
                found = NOTES.get(path[len("/api/notes/"):])
                if found is None:
                    self.json(404, {"error": "no such note"})
                else:
                    self.json(200, found)
            else:
                self.html(404, "<!doctype html><html><body>no such route</body></html>")

        def html(self, status: int, document: str) -> None:
            self.answer(status, document.encode("utf-8"), "text/html; charset=utf-8")

        def json(self, status: int, document: dict) -> None:
            self.answer(status, json.dumps(document).encode("utf-8"), "application/json")

        def answer(self, status: int, payload: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            """Silent, for the reason the other fixture's is."""

    return Fixture
