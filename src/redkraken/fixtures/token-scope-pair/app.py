"""The token-scope fixture, both variants, from one source.

Both variants issue the same three tokens, verify them with the same key, and
refuse the same tampered signature. The difference is what happens after the
signature checks out: the vulnerable variant treats a valid signature as the
whole authorisation decision, so a token minted for another audience, another
scope, or minted before its own expiry is honoured at a route that never asked
for any of that.

Nothing here is forged. Every reading a run does is a token this fixture handed
it, presented somewhere it does not claim to be valid.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import base64
import hmac
import json
import time
from hashlib import sha256
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit


VARIANTS = ("vulnerable", "secure")

#: The issuer's key. Held by the fixture, never served: `alg: none` and a
#: re-signed payload are refused by both variants, which keeps this pair about
#: scope rather than about signature verification.
KEY = b"fixture-issuer-signing-key"

#: What `GET /api/v1/profile` requires. The route is the subject and these two
#: values are what a token has to carry to be for it.
AUDIENCE = "profile"
SCOPE = "profile:read"

SUBJECT = "alice@fixture.invalid"

#: One second of the past, as a fixed offset rather than a fixed timestamp: an
#: absolute one would drift out of the future as the corpus ages and turn the
#: valid tokens into expired ones.
LIFETIME = 3600


def _token(payload: dict) -> str:
    body = base64.urlsafe_b64encode(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).rstrip(b"=")
    return f"{body.decode('ascii')}.{hmac.new(KEY, body, sha256).hexdigest()}"


def _payload(token: str) -> dict | None:
    """The claims a token carries, or None when the signature does not check out."""
    body, separator, signature = token.partition(".")
    if not separator:
        return None
    encoded = body.encode("ascii", "replace")
    if not hmac.compare_digest(hmac.new(KEY, encoded, sha256).hexdigest(), signature):
        return None
    try:
        claims = json.loads(base64.urlsafe_b64decode(encoded + b"=" * (-len(encoded) % 4)))
    except ValueError:
        return None
    return claims if isinstance(claims, dict) else None


def _presented(header: str | None) -> str | None:
    """The bearer token an Authorization header carries, or None."""
    kind, separator, value = (header or "").partition(" ")
    return value.strip() if separator and kind.lower() == "bearer" else None


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    enforces = variant == "secure"

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            path = urlsplit(self.path).path
            if path == "/tokens":
                self.mint()
            elif path == "/api/v1/profile":
                self.profile()
            else:
                self.answer(404, {"error": "no such route"})

        def mint(self) -> None:
            """The three tokens, identical on both variants.

            This is the fixture standing in for an Identity slot: a run works
            with credentials it was issued, and the interesting readings are all
            about presenting one of these somewhere it does not claim to be for.
            """
            now = int(time.time())
            self.answer(200, {
                "profile": _token({
                    "sub": SUBJECT, "aud": AUDIENCE, "scope": SCOPE, "exp": now + LIFETIME,
                }),
                "reports": _token({
                    "sub": SUBJECT, "aud": "reports", "scope": "reports:read",
                    "exp": now + LIFETIME,
                }),
                "expired": _token({
                    "sub": SUBJECT, "aud": AUDIENCE, "scope": SCOPE, "exp": now - LIFETIME,
                }),
            })

        def profile(self) -> None:
            token = _presented(self.headers.get("Authorization"))
            if token is None:
                self.answer(401, {"error": "not authenticated"})
                return
            claims = _payload(token)
            if claims is None:
                # The control, on both variants: the signature is verified, so
                # an answer to a re-scoped token is a statement about the claims
                # rather than about a route that reads nothing.
                self.answer(401, {"error": "token is not valid"})
                return

            if enforces:
                if int(claims.get("exp", 0)) < int(time.time()):
                    self.answer(401, {"error": "token has expired"})
                    return
                if claims.get("aud") != AUDIENCE or claims.get("scope") != SCOPE:
                    # The one difference. The vulnerable variant reaches the
                    # answer below with any token this issuer signed.
                    self.answer(403, {"error": "token is not for this audience or scope"})
                    return

            self.answer(200, {
                "sub": claims.get("sub"),
                "email": SUBJECT,
                "recovery_email": "alice-recovery@fixture.invalid",
            })

        def answer(self, status: int, document: dict) -> None:
            payload = json.dumps(document).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            """Silent, for the reason the other fixtures' are."""

    return Fixture
