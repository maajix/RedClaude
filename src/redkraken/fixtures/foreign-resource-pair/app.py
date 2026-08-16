"""The foreign-resource fixture, both variants, from one source.

A page that embeds a script the caller names. Both halves escape the attribute
correctly, so nothing here is markup injection: the value never breaks out of the
quotes it is written into. What differs is whether the host it points at was
checked before the tag was written.

Every address in this file is under the `.invalid` top-level domain, which RFC
2606 reserves and which never resolves. A fixture that named a host somebody owns
would be a fixture that fetched from them every time it was graded.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

from html import escape
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit


VARIANTS = ("vulnerable", "secure")

#: The one host the secure variant will load from, and the digest it insists on.
#: Published so a run that refutes is refuting against a stated rule.
ALLOWED = "https://assets.widgets.invalid"

INTEGRITY = "sha384-oqVuAfXRKap7fdgcCY5uykM6+R9GqQ8K/uxy9rx7HNQlGYl1kPzQho1wx4JwY8wC"

#: What the page shows when the address it was given is not one it will load.
REFUSED = '<div id="refused">that source is not on the list</div>'

PAGE = """<!doctype html>
<html><head><title>embed</title></head>
<body>
<h1>widget</h1>
{tag}
</body></html>
"""

NOT_FOUND = "<!doctype html><html><body>no such route</body></html>"

SUBJECT = "/embed"


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    checks_the_host = variant == "secure"

    def tag(src: str) -> str:
        """The one difference between the variants, and it is one check.

        Both halves write the address into a quoted attribute through the same
        escape, so the value cannot leave the attribute on either. The vulnerable
        half writes whatever it was handed; the secure half writes only the one
        host it trusts, and pins what it expects to receive from it.
        """
        if not checks_the_host:
            return f'<script id="widget" src="{escape(src, quote=True)}"></script>'
        if src.startswith(ALLOWED + "/"):
            return (
                f'<script id="widget" src="{escape(src, quote=True)}"'
                f' integrity="{INTEGRITY}" crossorigin="anonymous"></script>'
            )
        return REFUSED

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            parts = urlsplit(self.path)
            if parts.path != SUBJECT:
                self.answer(404, NOT_FOUND)
                return
            src = (parse_qs(parts.query).get("src") or [ALLOWED + "/widget.js"])[0]
            self.answer(200, PAGE.format(tag=tag(src)))

        def answer(self, status: int, document: str) -> None:
            payload = document.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            # No Content Security Policy on either half. A policy naming allowed
            # script sources would answer this pair's question in a header, which
            # is `transport.header_policy`'s pair and not this one.
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            """Silent, for the reason the other fixtures' are."""

    return Fixture
