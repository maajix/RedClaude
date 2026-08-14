"""The two fixture twins ticket 31 measures a browser against, over TLS.

Run as `python3 -m tests.browser_target <secure|vulnerable>`, with the
repository mounted read only and the fixture authority beside it. One page and
one form, differing in one line: the vulnerable twin writes back what it was
sent, and the secure twin escapes it. Everything else -- the markup, the
selectors, the script, the headers -- is identical, so a mission that
distinguishes them distinguished the behaviour and not the recording.

They run in containers rather than as threads in the suite because the door is
in a container too, and a fixture the door reached through the host gateway
would have to be bound on every interface of the machine running the tests.
"""

import html
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

#: The repository, as it is mounted in the container. Conditional for the reason
#: `browser_door` states: the suite imports this module on the host for the
#: marker and the selectors, and importing it must not move anything.
REPOSITORY = "/repo"
if os.path.isdir(REPOSITORY):
    sys.path[:0] = [f"{REPOSITORY}/src", REPOSITORY]

from redkraken import tls  # noqa: E402

#: Printed once the socket is bound, which is what the suite waits for.
LISTENING = "listening"

#: What the door was told the target is called, and what the fixture authority
#: issued the certificate for. The scope in `VALID` admits this host under
#: `/api/`, so both the page and the form it submits to are in scope.
HOST = "app.example.com"

#: Where the twins live and what they are asked. The form posts rather than
#: gets, which is what makes a browser mission derive `POST` from its own plan.
PAGE = "/api/orders"
SEARCH = "/api/search"

#: What the Program declares it must send this target on every request. The
#: twins answer nothing without it, so a mission that saw a page at all is a
#: mission whose door opened a sealed value and put it on the wire -- and the
#: browser, which never held it, could not have.
HEADER = "X-Bounty-Id"

#: The document. `form#login`, `input[name=q]` and `button[type=submit]` are the
#: selectors the plan names, so the plan the database compiles is the plan a
#: browser can walk without a second copy of it living here.
BODY = """<!doctype html><html><head><title>%(twin)s</title></head><body>
<h1 id="who">%(twin)s</h1>
<form id="login" method="POST" action="%(action)s">
  <input name="q" value="">
  <button type="submit">go</button>
</form>
<div id="result">%(result)s</div>
<script>console.log("fixture ready: %(twin)s");</script>
</body></html>"""


class Twin(BaseHTTPRequestHandler):
    """One page that answers a search, in whichever way this twin answers it."""

    protocol_version = "HTTP/1.1"
    twin = "secure"
    expected = ""

    def render(self, result: str, status: int = 200) -> None:
        body = (BODY % {"twin": self.twin, "action": SEARCH, "result": result}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def identified(self) -> bool:
        """Whether the door put this Program's required header on the wire.

        The value is compared rather than the name, and the refusal says
        neither: a fixture that echoed what it expected would put a sealed
        value into a document the mission keeps.
        """
        return self.headers.get(HEADER) == self.expected

    def refuse(self) -> None:
        self.send_response(403)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:
        if not self.identified():
            return self.refuse()
        self.render("nothing yet")

    def do_POST(self) -> None:
        if not self.identified():
            return self.refuse()
        size = int(self.headers.get("Content-Length") or 0)
        asked = parse_qs(self.rfile.read(size).decode("utf-8", "replace")).get("q", [""])[0]
        # The one line the twins differ in.
        self.render(asked if self.twin == "vulnerable" else html.escape(asked))

    def log_message(self, *arguments: object) -> None:
        pass


def main(twin: str) -> int:
    handler = type(
        "Vulnerable" if twin == "vulnerable" else "Secure",
        (Twin,),
        {"twin": twin, "expected": os.environ["RK_TARGET_HEADER"]},
    )
    server = ThreadingHTTPServer(("0.0.0.0", 443), handler)
    server.daemon_threads = True
    server.socket = tls.authority("/authority").context(HOST).wrap_socket(
        server.socket, server_side=True
    )
    print(LISTENING, flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
