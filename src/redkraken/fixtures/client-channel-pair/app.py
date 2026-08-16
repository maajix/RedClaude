"""The client-channel fixture, both variants, from one source.

Nothing the reading types reaches this process. The preview is rendered by the
page, from the field, with no request in between -- so the Receipt list of a run
against this fixture holds the navigation and nothing else, on both variants.
That absence is what the class is.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixture's source gives.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit


VARIANTS = ("vulnerable", "secure")

#: The parent. It exists so the widget is an embedded document rather than a page
#: that happens to be small, and it is never the subject: nothing about the
#: parent differs between the variants.
PARENT = """<!doctype html>
<html><head><title>notes</title></head>
<body>
<h1>notes</h1>
<iframe id="composer" src="/widget" width="480" height="240"></iframe>
</body></html>
"""

WIDGET = """<!doctype html>
<html><head><title>composer</title></head>
<body>
<textarea id="draft" rows="4" cols="60"></textarea>
<div id="preview"></div>
<script>
(function () {{
  var draft = document.getElementById('draft');
  var preview = document.getElementById('preview');
  draft.addEventListener('input', function () {{
    preview.{sink} = draft.value;
  }});
  window.addEventListener('message', function (event) {{
    draft.value = String(event.data);
    preview.{sink} = draft.value;
  }});
}})();
</script>
</body></html>
"""


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    # The one difference between the variants, and it is one property name. Both
    # halves read the same two sources -- the field and a cross-document message
    # -- and write to the same element; one builds markup out of the value and
    # one does not.
    sink = "innerHTML" if variant == "vulnerable" else "textContent"

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            path = urlsplit(self.path).path
            if path == "/":
                self.answer(200, PARENT)
            elif path == "/widget":
                self.answer(200, WIDGET.format(sink=sink))
            else:
                self.answer(404, "<!doctype html><html><body>no such route</body></html>")

        def answer(self, status: int, document: str) -> None:
            payload = document.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            # Framable on both variants, deliberately: the widget has to be
            # embeddable for the parent above to embed it, and a policy that
            # differed between the halves would be a second class in the pair.
            self.send_header("Content-Security-Policy", "frame-ancestors 'self'")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            """Silent, for the reason the other fixture's is."""

    return Fixture
