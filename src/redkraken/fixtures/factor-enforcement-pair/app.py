"""The factor-enforcement fixture, both variants, from one source.

A step-up route: changing the recovery address is supposed to need the account's
enrolled authenticator, not just its session. Both variants log in the same way,
issue the same receipt for a completed factor, and refuse a receipt that was not
issued here.

The vulnerable variant's guard is the one that appears in real code -- check the
receipt when the client sent one -- and it fails three ways at once, all of them
the same class: an omitted receipt, a receipt for a weaker factor, and a receipt
that was already spent.

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

EMAIL = "alice@fixture.invalid"
PASSWORD = "correct-horse-fixture"

COOKIE = "session"
SESSION = "s-alice-8a41"

#: The key the receipt is issued under. A receipt a run invented does not verify
#: on either variant, which is the control this pair rests on.
KEY = b"fixture-step-up-key"

#: The factors the account has enrolled, and the one the sensitive route is
#: supposed to require. `backup_code` is deliberately weaker and deliberately
#: real: an account that can fall back to it is the ordinary case, and letting
#: the client choose which one counts is the defect.
FACTORS = {"webauthn": "assertion-a3f1", "backup_code": "91827364"}
REQUIRED = "webauthn"


def _receipt(method: str) -> str:
    return hmac.new(KEY, method.encode("utf-8"), sha256).hexdigest()


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
    enforces = variant == "secure"

    #: The account state a run reads back to see whether the action happened,
    #: and the receipts the secure variant has already spent.
    account = {"recovery_email": "alice-recovery@fixture.invalid"}
    spent: set[str] = set()

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            if urlsplit(self.path).path != "/account":
                self.answer(404, {"error": "no such route"})
                return
            if _cookie(self.headers.get("Cookie"), COOKIE) != SESSION:
                self.answer(401, {"error": "not authenticated"})
                return
            self.answer(200, {"email": EMAIL} | account)

        def do_POST(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            path = urlsplit(self.path).path
            document = self.document()
            if document is None:
                return
            if path == "/session":
                self.login(document)
            elif path == "/factor/verify":
                self.verify(document)
            elif path == "/account/recovery-email":
                self.recovery(document)
            else:
                self.answer(404, {"error": "no such route"})

        def document(self) -> dict | None:
            length = int(self.headers.get("Content-Length") or 0)
            try:
                document = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                document = None
            if not isinstance(document, dict):
                self.answer(400, {"error": "a request carries a JSON object"})
                return None
            return document

        def login(self, document: dict) -> None:
            if document.get("email") != EMAIL or not hmac.compare_digest(
                PASSWORD, str(document.get("password", ""))
            ):
                self.answer(401, {"error": "authentication failed"})
                return
            self.answer(200, {"email": EMAIL}, cookie=f"{COOKIE}={SESSION}; Path=/")

        def verify(self, document: dict) -> None:
            """One completed factor, in exchange for the material it needs.

            Both variants issue receipts for both enrolled factors. Which of
            them the sensitive route accepts is the difference, and putting it
            here would hide it behind a step a run cannot see.
            """
            if _cookie(self.headers.get("Cookie"), COOKIE) != SESSION:
                self.answer(401, {"error": "not authenticated"})
                return
            method = str(document.get("method", ""))
            if method not in FACTORS or document.get("assertion") != FACTORS[method]:
                self.answer(401, {"error": "factor was not completed"})
                return
            self.answer(200, {"method": method, "receipt": _receipt(method)})

        def recovery(self, document: dict) -> None:
            if _cookie(self.headers.get("Cookie"), COOKIE) != SESSION:
                self.answer(401, {"error": "not authenticated"})
                return
            address = document.get("email")
            if not isinstance(address, str) or "@" not in address:
                self.answer(400, {"error": "a request carries an email"})
                return
            presented = document.get("receipt")

            if enforces:
                if presented != _receipt(REQUIRED):
                    # Required, of the right factor, and not the client's word
                    # about which factor ran.
                    self.answer(401, {"error": f"this action requires {REQUIRED}"})
                    return
                if presented in spent:
                    self.answer(401, {"error": "that factor was already used"})
                    return
                spent.add(str(presented))
            elif presented is not None and presented not in {
                _receipt(method) for method in FACTORS
            }:
                # The defect, in one clause: the receipt is checked only when
                # the client sent one, any enrolled factor's receipt counts, and
                # nothing is ever spent.
                self.answer(401, {"error": "factor receipt is not valid"})
                return

            account["recovery_email"] = address
            self.answer(200, {"recovery_email": address})

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
