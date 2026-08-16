"""The tenant-isolation fixture, both variants, from one source.

A machine-to-machine route: a workload token proves which runner is calling, and
a header says which project's metrics to return. Both variants verify the token
with the same key and refuse a caller that has none.

The difference is whether anything compares the two. The vulnerable variant
selects the project the header names, so a token issued inside one project reads
another project's rows -- which is the class, and it is a defect of the
application rather than of the credential.

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

#: The key the workload tokens are issued under. Held by the fixture: a run's
#: material is what `GET /internal/tokens` handed it, presented against a
#: project it was not issued in.
KEY = b"fixture-workload-issuer-key"

#: The header that selects a tenant, and the two projects the fixture holds.
#: Both are the engagement's own, which is the precondition the Playbook states:
#: the second tenant is what makes the reading a comparison.
HEADER = "X-Project"

PROJECTS = {
    "alpha": {"runner": "alpha-runner", "builds": 41, "queue": ["build-a17", "build-a18"]},
    "beta": {"runner": "beta-runner", "builds": 7, "queue": ["build-b03"]},
}


def _token(project: str) -> str:
    return f"{project}.{hmac.new(KEY, project.encode('utf-8'), sha256).hexdigest()}"


def _project(token: str | None) -> str | None:
    """The project a workload token was issued in, or None when it was not."""
    project, separator, _ = (token or "").partition(".")
    if not separator or project not in PROJECTS:
        return None
    return project if hmac.compare_digest(_token(project), str(token)) else None


def _presented(header: str | None) -> str | None:
    """The bearer token an Authorization header carries, or None."""
    kind, separator, value = (header or "").partition(" ")
    return value.strip() if separator and kind.lower() == "bearer" else None


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    confines = variant == "secure"

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            path = urlsplit(self.path).path
            if path == "/internal/tokens":
                # The fixture standing in for the operator's slots: both tokens
                # belong to the engagement, and neither is harvested.
                self.answer(200, {name: _token(name) for name in sorted(PROJECTS)})
            elif path == "/internal/metrics":
                self.metrics()
            else:
                self.answer(404, {"error": "no such route"})

        def metrics(self) -> None:
            issued = _project(_presented(self.headers.get("Authorization")))
            if issued is None:
                # The control, on both variants. A route that answered an
                # unauthenticated caller would be `function_access`, and a
                # differential read against it would say nothing about tenants.
                self.answer(401, {"error": "not authenticated"})
                return

            # `http.client` folds repeated headers into one comma-joined value,
            # which is what a duplicated tenant header looks like on the wire.
            asked = [
                part.strip()
                for part in (self.headers.get(HEADER) or issued).split(",")
                if part.strip()
            ]
            if confines:
                if len(asked) != 1:
                    self.answer(400, {"error": f"one {HEADER} per request"})
                    return
                if asked[0] != issued:
                    # The one difference. The token says which project this
                    # workload belongs to and the header does not get to
                    # disagree with it.
                    self.answer(403, {"error": "token is not issued for that project"})
                    return
            wanted = asked[-1]
            if wanted not in PROJECTS:
                self.answer(404, {"error": "no such project"})
                return
            self.answer(200, {"project": wanted} | PROJECTS[wanted])

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
