"""The unclaimed-reference fixture, both variants, from one source.

A page that loads a widget from an asset host, and the application's own report
of what that host answers. The vulnerable variant still points at a provider
slot nobody holds any more, and reports the provider's unclaimed-namespace error
verbatim; the secure variant points at a host it holds and reports the asset.

Nothing here claims anything, and nothing here can be claimed: the "provider" is
a route on this same fixture, serving the body a provider serves for a name that
is free. That is deliberate. The reading this class exists for is the reference
plus the provider's own answer, and taking the name is refused everywhere in
this harness.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit


VARIANTS = ("vulnerable", "secure")

#: The asset host each variant's page references. The vulnerable one is a name
#: the application stopped holding; the secure one is the name it holds now.
ABANDONED = "legacy-assets-4f2c.fixture.invalid"
HELD = "assets.fixture.invalid"

WIDGET = "widget.js"

#: What an S3-compatible provider answers for a bucket name that is not taken.
#: Quoted as the shape of the answer, not as any provider's exact document.
UNCLAIMED = (
    "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
    "<Error><Code>NoSuchBucket</Code>"
    "<Message>The specified bucket does not exist</Message>"
    "<BucketName>legacy-assets-4f2c</BucketName></Error>"
)

ASSET = "window.widget = function () { return 'ok'; };\n"

PAGE = """<!doctype html>
<html><head><title>Dashboard</title>
<script src="https://{host}/{widget}"></script>
</head><body><h1>Dashboard</h1><div id="widget"></div></body></html>
"""


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    dangling = variant == "vulnerable"
    host = ABANDONED if dangling else HELD

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            path = urlsplit(self.path).path
            if path == "/dashboard":
                self.html(200, PAGE.format(host=host, widget=WIDGET))
                return
            if path == "/assets/manifest":
                # The reference, stated by the application rather than only
                # embedded in markup, so a reading does not depend on parsing a
                # page. Both variants publish it, in the same shape.
                self.answer(200, {"asset_host": host, "assets": [WIDGET]})
                return
            if path == "/assets/status":
                self.status()
                return
            if path.startswith("/provider/"):
                self.provider(path[len("/provider/"):])
                return
            self.answer(404, {"error": "no such route"})

        def status(self) -> None:
            """What the application got the last time it fetched its own asset host."""
            if dangling:
                # The whole reading, and it is the provider's words rather than
                # this fixture's opinion of them: a name in the provider's
                # namespace that answers `NoSuchBucket` is unheld, and the
                # application is still pointing at it.
                self.answer(200, {
                    "asset_host": host,
                    "provider": "s3-compatible object storage",
                    "upstream_status": 404,
                    "upstream_body": UNCLAIMED,
                })
                return
            self.answer(200, {
                "asset_host": host,
                "provider": "s3-compatible object storage",
                "upstream_status": 200,
                "upstream_bytes": len(ASSET.encode("utf-8")),
            })

        def provider(self, name: str) -> None:
            """The provider's own answer for one name, so the reading is checkable."""
            if name == HELD:
                self.script(200, ASSET)
                return
            self.xml(404, UNCLAIMED)

        def html(self, status: int, body: str) -> None:
            self.send(status, "text/html; charset=utf-8", body.encode("utf-8"))

        def script(self, status: int, body: str) -> None:
            self.send(status, "application/javascript", body.encode("utf-8"))

        def xml(self, status: int, body: str) -> None:
            self.send(status, "application/xml", body.encode("utf-8"))

        def answer(self, status: int, document: dict) -> None:
            self.send(status, "application/json", json.dumps(document).encode("utf-8"))

        def send(self, status: int, kind: str, payload: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            """Silent, for the reason the other fixtures' are."""

    return Fixture
