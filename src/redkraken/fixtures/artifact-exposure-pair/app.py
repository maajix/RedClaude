"""The artifact-exposure fixture, both variants, from one source.

A deployment that shipped its build output and the map beside it. The map is the
artifact: it carries the pre-build source of the module it was generated from,
and that source carries a deploy credential that was never meant to leave the
build host.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler


VARIANTS = ("vulnerable", "secure")

#: The bundle. Served identically by both variants, because a fixture whose two
#: halves disagreed about what the application is would be two applications.
BUNDLE = b"""(()=>{const t=async e=>(await fetch("/api/v3/notes/"+e)).json();window.n=t})();
//# sourceMappingURL=app.js.map
"""

#: The map. This is the whole fixture: a build-time document, reachable by
#: anybody, carrying the source it was built from. The credential inside it is
#: the reason `information_disclosure.artifact_exposure` is a class and not a
#: note about hygiene -- what leaked is not the shape of the code, it is a value
#: that still works.
SOURCE_MAP = {
    "version": 3,
    "file": "app.js",
    "sources": ["src/notes.ts"],
    "names": [],
    "mappings": "AAAA,MAAM,IAAI,MAAO,GAAM",
    "sourcesContent": [
        "// notes.ts -- internal build, do not ship\n"
        "const DEPLOY_KEY = 'rk-deploy-8f14e45fceea167a5a36dedd4bea2543';\n"
        "const INTERNAL_API = 'http://notes-internal.svc.cluster.local:8080';\n"
        "export const note = async (id: string) =>\n"
        "  (await fetch(`/api/v3/notes/${id}`)).json();\n"
    ],
}

NOT_FOUND = {"error": "not found"}


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    ships_map = variant == "vulnerable"

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            path, _, _ = self.path.partition("?")
            if path == "/static/app.js":
                # Both variants, and the reason the pair is evaluable at all: a
                # `404` on the map is only evidence of a stripped build if the
                # bundle beside it was there to be stripped from.
                self.raw(200, "application/javascript", BUNDLE)
                return
            if path == "/static/app.js.map":
                if ships_map:
                    self.answer(200, SOURCE_MAP)
                else:
                    self.answer(404, NOT_FOUND)
                return
            self.answer(404, NOT_FOUND)

        def answer(self, status: int, document: dict) -> None:
            self.raw(status, "application/json", json.dumps(document).encode("utf-8"))

        def raw(self, status: int, content_type: str, payload: bytes) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            """Silent, for the reason the other fixtures' are."""

    return Fixture
