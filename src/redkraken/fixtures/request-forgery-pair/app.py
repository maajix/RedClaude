"""The request-forgery fixture, both variants, from one source.

A webhook registration that verifies the URL it was given by fetching it, and
hands the caller what came back.

The fetch opens no socket. The "network" this fixture reaches is the dict below,
resolved in process, and that is deliberate: a fixture that made real outbound
requests would send traffic to wherever a test pointed it, which is exactly the
behaviour under study and not a thing a test suite should do. What the class
needs is that the caller chooses the destination and learns the answer, and a
resolved map has both.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit


VARIANTS = ("vulnerable", "secure")

#: The network the verification request reaches, resolved in process. Two
#: addresses a deployment would consider internal, holding the kind of document
#: that makes this class worth a report rather than a note.
INTERNAL = {
    "169.254.169.254": {
        "/latest/meta-data/iam/security-credentials/deploy": {
            "AccessKeyId": "AKIAFIXTUREEXAMPLE",
            "SecretAccessKey": "rk-fixture-secret-8f14e45fceea167a",
            "Expiration": "2026-08-16T23:59:59Z",
        },
    },
    "consul.svc.cluster.local": {
        # Not spelled with a real vendor's live-key prefix. A fixture secret is
        # invented and worthless, and a scanner that pattern-matches the prefix
        # cannot know that -- so the shape stays recognisable to a reader and
        # unrecognisable to push protection.
        "/v1/kv/billing/stripe": {"value": "rk-fixture-payment-key-4bea2543"},
    },
}

#: The one host a webhook may point at. The secure variant checks against this
#: list before it verifies anything; the vulnerable variant does not check.
ALLOWED_HOSTS = ("hooks.fixture.invalid",)

#: What has been registered on this process, keyed by the identifier handed
#: back. Module level and cleared in `handler`, for the reason `ANSWERED` in the
#: model-instruction fixture is: a repeat gets a fresh process, and state that
#: survived one would make the second repeat a different subject from the first.
REGISTERED: dict[str, str] = {}

NOT_FOUND = {"error": "no such route"}
BAD_REQUEST = {"error": "a registration carries a url"}
REFUSED = {"error": "webhook host is not allowed"}

#: What an address outside the resolved map answers with. Both variants, so that
#: an allowed host behaves identically on each of them.
UNREACHABLE = {"status": None, "error": "connection refused"}


def _verify(url: str) -> dict:
    """What the verification request saw, by resolving the caller's URL in process."""
    parts = urlsplit(url)
    routes = INTERNAL.get(parts.hostname or "")
    if routes is None or parts.path not in routes:
        return dict(UNREACHABLE)
    return {"status": 200, "body": routes[parts.path]}


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    checks_host = variant == "secure"
    REGISTERED.clear()

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            if urlsplit(self.path).path != "/webhooks":
                self.answer(404, NOT_FOUND)
                return
            length = int(self.headers.get("Content-Length") or 0)
            try:
                url = str(json.loads(self.rfile.read(length) or b"{}")["url"])
                parts = urlsplit(url)
            except (ValueError, KeyError, TypeError):
                self.answer(400, BAD_REQUEST)
                return
            if parts.scheme not in ("http", "https") or not parts.hostname:
                self.answer(400, BAD_REQUEST)
                return
            if checks_host and parts.hostname not in ALLOWED_HOSTS:
                # The one difference between the variants, and it is a decision
                # taken before anything is fetched.
                self.answer(400, REFUSED)
                return
            identifier = f"wh-{len(REGISTERED) + 1}"
            REGISTERED[identifier] = url
            self.answer(201, {"id": identifier, "url": url, "verification": _verify(url)})

        def do_DELETE(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            prefix, _, identifier = urlsplit(self.path).path.rpartition("/")
            if prefix != "/webhooks" or identifier not in REGISTERED:
                self.answer(404, NOT_FOUND)
                return
            # Both variants. A run that writes has somewhere to put it back.
            del REGISTERED[identifier]
            self.answer(204, None)

        def answer(self, status: int, document: dict | None) -> None:
            payload = b"" if document is None else json.dumps(document).encode("utf-8")
            self.send_response(status)
            if payload:
                self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            """Silent, for the reason the other fixtures' are."""

    return Fixture
