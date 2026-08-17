"""The workload-metadata fixture, both variants, from one source.

An operational endpoint on the application's own ingress. One variant answers it
with a description of the thing running the process; the other answers it with a
health verdict.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit


VARIANTS = ("vulnerable", "secure")

#: What the platform underneath this process is, as the vulnerable variant
#: reports it. Every field is a name: none of them is a credential, and the peer
#: address has nothing behind it. A fixture that rewarded resolving one of these
#: would be teaching a reading to leave the scope it was granted.
WORKLOAD = {
    "pod": "web-7d9f8c-4kq2p",
    "namespace": "acme-prod",
    "node": "ip-10-40-3-118",
    "image": "registry.acme.internal/acme/web:2026.8.3",
    "service_account": "web-runner",
    "peers": ["10.40.3.22:8080"],
}

#: The verdict, which is all an operational endpoint was ever asked for.
HEALTHY = {"status": "ok"}

#: Public metadata: the build string the application prints for everybody. It is
#: on both variants because it is not a finding on either.
VERSION = {"build": "2026.8.3", "commit": "a1b2c3d"}

NO_ROUTE = {"error": "no such route"}


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    answers_the_workload = variant == "vulnerable"

    #: The counter behind `/metrics/live`. It exists to be noisy, and it is
    #: deliberately not in the subject: a subject that moved between two sends
    #: would make every comparison a reading performs ambiguous.
    scrapes = [0]

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            path = urlsplit(self.path).path
            if path == "/healthz":
                self.health()
            elif path == "/readyz":
                # The second operational route, carrying a verdict and nothing
                # else on both variants. A reading that stops at the first name
                # that answers, rather than the first that answers with a
                # workload fact, gets it wrong here.
                self.answer(200, dict(HEALTHY))
            elif path == "/version":
                # The decoy: public metadata, identically on both variants.
                self.answer(200, dict(VERSION))
            elif path == "/metrics/live":
                # Noise, identically on both variants.
                scrapes[0] += 1
                self.answer(200, {"scrapes": scrapes[0]})
            else:
                self.answer(404, NO_ROUTE)

        def health(self) -> None:
            """The subject. The one thing the variants disagree about."""
            if answers_the_workload:
                # The defect: the answer the platform wanted, on the door the
                # callers use.
                self.answer(200, dict(HEALTHY) | WORKLOAD)
                return
            # The defence: a probe asked whether this replica is alive, so the
            # answer is whether this replica is alive.
            self.answer(200, dict(HEALTHY))

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
