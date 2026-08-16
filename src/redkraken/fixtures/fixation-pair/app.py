"""The session-fixation fixture, both variants, from one source.

A whole authorisation round trip inside one application: a client that starts a
flow, an issuer that hands back a code, and a callback that turns the code into
a session. Both variants exchange only codes this fixture minted and refuse
everything else, so the pair is not about forging a code.

The difference is whether the callback checks that the browser presenting the
code is the browser that started the flow. The vulnerable variant does not, so
the callback is a URL that mints a session wherever it is opened.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit


VARIANTS = ("vulnerable", "secure")

SUBJECT = "alice@fixture.invalid"

#: The cookie the client sets before it leaves, holding the value it will
#: compare against `state` when the flow comes back. The binding lives here, in
#: browser state, which is why the class is read in a browser on a real target.
FLOW = "flow"
COOKIE = "session"


def _cookie(header: str | None, name: str) -> str | None:
    """The value a cookie header carries under one name, or None."""
    for part in (header or "").split(";"):
        found, separator, value = part.strip().partition("=")
        if separator and found == name:
            return value
    return None


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    binds = variant == "secure"

    #: Flows started, and codes minted, both keyed by the `state` they belong
    #: to. Counted rather than random so that two repeats of an evaluation see
    #: the same values and a run can name what it sent.
    started: list[str] = []
    codes: dict[str, str] = {}
    sessions: dict[str, str] = {}

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            split = urlsplit(self.path)
            query = parse_qs(split.query)
            if split.path == "/oauth/start":
                self.start()
            elif split.path == "/oauth/authorize":
                self.authorize(query)
            elif split.path == "/oauth/callback":
                self.callback(query)
            elif split.path == "/whoami":
                self.whoami()
            else:
                self.answer(404, {"error": "no such route"})

        def start(self) -> None:
            """The client half: mint `state`, keep it in the browser, hand back the URL."""
            state = f"st-{len(started) + 1:04d}"
            started.append(state)
            self.answer(
                200,
                {"authorize": f"/oauth/authorize?state={state}", "state": state},
                cookie=f"{FLOW}={state}; Path=/",
            )

        def authorize(self, query: dict[str, list[str]]) -> None:
            """The issuer half: a code for a flow that was started, and a redirect back."""
            state = (query.get("state") or [""])[0]
            if state not in started:
                self.answer(400, {"error": "no such flow"})
                return
            code = f"c-{state}"
            codes[code] = state
            self.send_response(302)
            self.send_header("Location", f"/oauth/callback?code={code}&state={state}")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def callback(self, query: dict[str, list[str]]) -> None:
            code = (query.get("code") or [""])[0]
            state = (query.get("state") or [""])[0]
            if code not in codes:
                # The control, on both variants: a code nobody minted buys
                # nothing, so a session out of a delivered callback is a
                # statement about the binding rather than about a route that
                # hands sessions to anyone.
                self.answer(401, {"error": "code is not valid"})
                return
            if binds:
                held = _cookie(self.headers.get("Cookie"), FLOW)
                if held is None or held != state or codes[code] != state:
                    # The one difference. The browser that started the flow is
                    # the only one holding this value.
                    self.answer(400, {"error": "this browser did not start this flow"})
                    return

            value = f"s-{code}"
            sessions[value] = SUBJECT
            self.answer(
                200,
                {"subject": SUBJECT},
                cookie=f"{COOKIE}={value}; Path=/",
            )

        def whoami(self) -> None:
            presented = _cookie(self.headers.get("Cookie"), COOKIE)
            if presented not in sessions:
                self.answer(401, {"error": "not authenticated"})
                return
            self.answer(200, {"subject": sessions[presented]})

        def answer(self, status: int, document: dict, cookie: str | None = None) -> None:
            payload = json.dumps(document).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            if cookie is not None:
                self.send_header("Set-Cookie", cookie)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            """Silent, for the reason the other fixtures' are."""

    return Fixture
