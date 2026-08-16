"""The federation-trust fixture, both variants, from one source.

An assertion consumer with two readers over one document: a signature check over
the `signed` object, and a subject extraction that the vulnerable variant lets a
sibling key override. That is signature wrapping with the XML removed -- the
defect is the disagreement between the verified region and the region the
application acts on, and the tree shape is not what makes it one.

Both variants verify the signature with the same key and refuse the same broken
one. Nothing here can be forged: a run's material is the assertion the fixture
minted for its own leased subject.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import hmac
import json
from hashlib import sha256
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit


VARIANTS = ("vulnerable", "secure")

#: The identity provider's signing key, held by the fixture because the fixture
#: plays both halves of the flow. A run never needs it: every variant it sends
#: is the minted document with one edit.
KEY = b"fixture-idp-signing-key"

#: The one subject this fixture will mint an assertion for. An endpoint that
#: minted assertions for a subject named by the caller would be a defect of its
#: own, and this pair declares one class.
SUBJECT = "alice@fixture.invalid"

#: The subject a wrapping variant names. Present in the fixture so its ground
#: truth can say which name a successful variant comes back as.
OTHER = "mallory@fixture.invalid"

COOKIE = "session"


def _canonical(signed: dict) -> bytes:
    """The bytes the signature covers: the `signed` object and nothing else."""
    return json.dumps(signed, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sign(signed: dict) -> str:
    return hmac.new(KEY, _canonical(signed), sha256).hexdigest()


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
    reads_inside = variant == "secure"

    #: Sessions this consumer has minted, by value, holding the subject each one
    #: was logged in as. `GET /whoami` reads it, which is how a run sees *who*
    #: came back rather than that something did.
    sessions: dict[str, str] = {}

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            path = urlsplit(self.path).path
            if path == "/sso/assertion":
                # The one honest login: the document the provider mints for the
                # leased subject, identical on both variants.
                signed = {"subject": SUBJECT, "issuer": "fixture-idp", "audience": "fixture-sp"}
                self.answer(200, {"signed": signed, "signature": _sign(signed)})
            elif path == "/whoami":
                presented = _cookie(self.headers.get("Cookie"), COOKIE)
                if presented not in sessions:
                    self.answer(401, {"error": "not authenticated"})
                    return
                self.answer(200, {"subject": sessions[presented]})
            else:
                self.answer(404, {"error": "no such route"})

        def do_POST(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            if urlsplit(self.path).path != "/sso/acs":
                self.answer(404, {"error": "no such route"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            try:
                document = json.loads(self.rfile.read(length) or b"{}")
                signed = document["signed"]
                signature = str(document["signature"])
            except (ValueError, KeyError, TypeError):
                self.answer(400, {"error": "a request carries a signed assertion"})
                return
            if not isinstance(signed, dict) or "subject" not in signed:
                self.answer(400, {"error": "a signed assertion names a subject"})
                return

            if not hmac.compare_digest(_sign(signed), signature):
                # The control, on both variants: this consumer verifies
                # something, so a session out of a wrapping variant is a
                # statement about which region it read.
                self.answer(401, {"error": "signature is not valid"})
                return

            outside = document.get("subject")
            if reads_inside:
                if outside is not None:
                    # A document that states the subject twice is refused
                    # outright rather than resolved: the secure variant has one
                    # reader and it is the verified region.
                    self.answer(400, {"error": "a subject outside the signature"})
                    return
                subject = str(signed["subject"])
            else:
                # The defect. The signature covered `signed`; the application
                # takes the sibling key when there is one, so the identity it
                # acts on is the copy nothing verified.
                subject = str(outside if outside is not None else signed["subject"])

            value = f"s-{sha256(subject.encode('utf-8')).hexdigest()[:8]}"
            sessions[value] = subject
            self.answer(
                200,
                {"subject": subject},
                cookie=f"{COOKIE}={value}; Path=/",
            )

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
