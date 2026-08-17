"""The edge-rule fixture, both variants, from one source.

Two programs in one process: a front end holding a path rule, and an application
behind it that holds none. One variant matches the rule against the bytes that
arrived; the other matches it against the path those bytes resolve to.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import unquote, urlsplit


VARIANTS = ("vulnerable", "secure")

#: The one path the deployment refuses. Held by the front end, because the
#: application behind it has no rule of its own -- which is the arrangement this
#: class is about.
RESTRICTED = "/admin/config"

#: What the application serves, keyed by resolved path. The application resolves
#: identically on both variants; it always did, and that is the half of the
#: disagreement that is not the defect.
PAGES = {
    RESTRICTED: {"config": {"region": "eu-central", "workers": 4}},
    "/public/index": {"page": "index"},
}

EDGE = "edge"
APPLICATION = "application"

#: Fixed bodies from both programs. Neither names the rule, the pattern or the
#: build, so that nothing here carries `information_disclosure.error_detail`
#: beside the class this pair declares.
FORBIDDEN = {"error": "forbidden"}
NO_ROUTE = {"error": "no such route"}


def _resolve(path: str) -> str:
    """The path a segment-by-segment resolver arrives at.

    Percent-decoding first, then per segment: a matrix parameter is dropped, an
    empty or `.` segment is skipped, `..` climbs one, and a trailing dot or space
    is trimmed. This is the application's resolution, and on the secure variant
    it is also the front end's.
    """
    resolved: list[str] = []
    for raw in unquote(path).split("/"):
        segment = raw.split(";", 1)[0]
        if segment in ("", ".", ".."):
            if segment == ".." and resolved:
                resolved.pop()
            continue
        resolved.append(segment.rstrip(". "))
    return "/" + "/".join(resolved)


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    edge_resolves_first = variant == "secure"

    #: The counter behind `/status`. It exists to be noisy.
    requests = [0]

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            arrived = urlsplit(self.path).path
            # The front end. The one line the variants disagree about: which
            # spelling of the path the rule is compared against.
            matched = _resolve(arrived) if edge_resolves_first else arrived
            if matched == RESTRICTED:
                self.answer(403, FORBIDDEN, EDGE)
                return
            self.application(_resolve(arrived))

        def application(self, path: str) -> None:
            """What is behind the front end. Identical on both variants."""
            if path == "/status":
                # Noise, identically on both variants.
                requests[0] += 1
                self.answer(200, {"requests": requests[0]}, APPLICATION)
                return
            page = PAGES.get(path)
            if page is None:
                self.answer(404, NO_ROUTE, APPLICATION)
                return
            self.answer(200, page, APPLICATION)

        def answer(self, status: int, document: dict, served_by: str) -> None:
            payload = json.dumps(document).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            # Which of the two programs produced this answer. Stated because the
            # claim is about exactly that, and a reading that had to guess would
            # be graded on its guess.
            self.send_header("X-Served-By", served_by)
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            """Silent, for the reason the other fixtures' are."""

    return Fixture
