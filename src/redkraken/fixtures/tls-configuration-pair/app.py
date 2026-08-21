"""The tls-configuration fixture, both variants, from one source.

An application shell behind a terminating front end, advertising a strict
transport posture to every caller. Both variants answer byte for byte the same
thing. What differs is the handshake underneath: one front end still terminates
at TLS 1.2, the other terminates at TLS 1.3 and nothing else.

That is why this file has a second entry point. Every other fixture in this
corpus is a `handler(variant)` and nothing more, because every other class it
grades is settled by what came back. `transport.tls_configuration` is settled by
what was negotiated, and 025 says so in the shape of the answer: its
`allowed_fields` are `tls_version`, `cipher` and `alpn`, none of which any
handler can write. So `tls(variant, context)` configures the socket the handler
is served over, and the two functions divide the fixture the way the class does
-- the bytes are the application's, the handshake is the front end's.

`tls` configures a context rather than building one, and that split is
deliberate. The certificate is the evaluator's: it is minted per run, it names
the origin the evaluator chose, and a fixture that issued its own would be a
fixture deciding who it is. What this file decides is the protocol floor, the
cipher list and the ALPN offer, which is the whole of what the class is about.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import json
import ssl
from http.server import BaseHTTPRequestHandler


VARIANTS = ("vulnerable", "secure")

#: What the deployment tells every caller about its transport posture, on both
#: variants, identically. Two years, subdomains included, preload requested: a
#: deployment saying it has no cleartext and no weak transport anywhere. It is
#: an advertisement rather than a measurement, which is the distinction the
#: whole reading rests on -- one variant honours it and the other does not, and
#: nothing in this header says which.
HSTS = "max-age=63072000; includeSubDomains; preload"

#: The shell the subject route serves. A single-page application's entry
#: document: the markup is a mount point and the behaviour is in the bundle,
#: which is what `spa_surface` names.
SHELL = (
    "<!doctype html>\n"
    "<html><head><title>Acme Console</title>\n"
    '<script defer src="/static/console.js"></script>\n'
    "</head><body><div id=\"root\"></div></body></html>\n"
)

#: What the front end says about itself, on both variants. A recognised token
#: rather than an invented product name, because `tech_edge_proxy` is computed
#: from the technology tokens 055 maps -- `nginx`, `haproxy`, `traefik`, `envoy`,
#: `apache`, `iis` -- and this pair's own `bb:facts` declares that fact. A
#: fixture declaring a fact no reading of its responses could reach would be
#: declaring it against nothing, and `http-desync` names it in `bb:triggers_all`.
EDGE = "nginx/1.27.2"

#: The bundle the shell loads. It exists so the subject is a shell with
#: something behind it rather than one document, and it is byte-stable.
BUNDLE = 'export const build = "2026.9.1";\n'

#: What the status route answers. The same string for every caller on both
#: variants, so a reading that compared bodies across the pair finds nothing.
STATUS = {"status": "ok", "build": "2026.9.1"}

#: The one route whose body moves. It exists so a reading that skipped its
#: baseline has somewhere to be wrong, exactly as the other pairs provide.
COUNTER = "/api/metrics/live"

SHELL_ROUTE = "/app"
BUNDLE_ROUTE = "/static/console.js"
STATUS_ROUTE = "/api/public/status"


def tls(variant: str, context: ssl.SSLContext) -> None:
    """Configure the handshake this variant terminates, on the evaluator's context.

    The context arrives holding the certificate chain and nothing else decided.
    What is set here is the three things `transport.tls_configuration` is
    settled over, and the difference between the halves is two of them.

    **vulnerable** still terminates at TLS 1.2. The suite it then negotiates is
    a perfectly respectable AEAD one -- this is not a fixture about a broken
    cipher, and a reading that reported the cipher as the defect would be
    reporting the consequence. The defect is the floor: a deployment
    advertising `includeSubDomains; preload` is claiming a posture that a 1.2
    terminator does not have, and the version is the field that says so.

    **secure** terminates at TLS 1.3 and refuses everything under it. Its suite
    follows from that rather than being chosen, which is the honest shape: in
    1.3 the cipher is not the server's to pick from a list the client sent.

    ALPN is `http/1.1` on both and that is not laziness. The application behind
    this front end speaks HTTP/1.1, so a front end offering `h2` would be
    advertising a protocol nothing here can frame, and the pair would differ in
    whether it works rather than in what it negotiated. A fixture whose
    vulnerable half is simply broken grades nothing.
    """
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    context.set_alpn_protocols(["http/1.1"])
    if variant == "secure":
        context.minimum_version = ssl.TLSVersion.TLSv1_3
        context.maximum_version = ssl.TLSVersion.TLSv1_3
        return
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.maximum_version = ssl.TLSVersion.TLSv1_2
    # Named rather than left to the default list, so what the vulnerable half
    # negotiates is a decision this file made and a reader can check, rather
    # than whatever the linked OpenSSL happens to prefer this year. The
    # certificate is a P-256 leaf, so the suite is an ECDSA one.
    context.set_ciphers("ECDHE-ECDSA-AES128-GCM-SHA256")


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture.

    The variant is validated and then not used, and that is the fixture rather
    than an oversight: the two halves return the same bytes on every route,
    including the same advertisement. Everything that differs between them
    happened before the first byte of the request arrived, in `tls`.
    """
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")

    #: The counter behind `/api/metrics/live`. It exists to be noisy.
    requests = [0]

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            path = self.path.split("?", 1)[0]
            if path == SHELL_ROUTE:
                self.answer(200, SHELL.encode(), "text/html; charset=utf-8")
            elif path == BUNDLE_ROUTE:
                self.answer(200, BUNDLE.encode(), "application/javascript")
            elif path == STATUS_ROUTE:
                self.answer(200, json.dumps(STATUS).encode(), "application/json")
            elif path == COUNTER:
                requests[0] += 1
                body = json.dumps({"requests": requests[0]}).encode()
                self.answer(200, body, "application/json")
            else:
                self.answer(404, b'{"error":"not found"}', "application/json")

        def do_HEAD(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            self.do_GET()

        def answer(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            # The advertisement, on every response of both variants. It is
            # what a reading writes down before it measures anything.
            self.send_header("Strict-Transport-Security", HSTS)
            self.send_header("Server", EDGE)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            """Silent, like every other fixture in this corpus."""

    return Fixture
