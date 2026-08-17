"""The dependency-manifest fixture, both variants, from one source.

A single-page shell, the bundle it embeds, and the source map that bundle points
at. One variant's map names packages and a registry that exist only inside one
organisation; the other's names only what the public already has.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit


VARIANTS = ("vulnerable", "secure")

#: The shell. It embeds one bundle, and `/static/legacy.js` is deliberately not
#: in it: a file the origin serves and the shell never loads is the reachability
#: control this pair carries.
SHELL = (
    "<!doctype html>\n"
    "<html><head><title>acme</title></head>\n"
    "<body><div id=\"root\"></div>\n"
    "<script src=\"/static/app.js\"></script>\n"
    "</body></html>\n"
)

#: A string of exactly credential shape, in the bundle both variants serve, that
#: nothing in this fixture honours. It is the credential decoy: a reading that
#: files it has filed `information_disclosure.credential_material`, which is
#: `secrets`' class and `credential-material-pair`'s target, on a string that
#: buys nothing and is identical on both halves, so it can never be the
#: difference this pair grades.
SAMPLE_KEY = "rk_sample_000000000000"

#: The entry bundle, ending in the pointer its builder wrote. The reading is
#: meant to follow this rather than guess at a path, which is why the pointer is
#: the only thing that names the map.
APP_BUNDLE = (
    f"// sample key, rotated out of this build: {SAMPLE_KEY}\n"
    "(function(){var r=document.getElementById(\"root\");"
    "r.textContent=\"acme\";})();\n"
    "//# sourceMappingURL=app.js.map\n"
)

#: The bundle nothing loads.
LEGACY_BUNDLE = (
    "(function(){return 0;})();\n"
    "//# sourceMappingURL=legacy.js.map\n"
)

#: What the public already has: the application's own files, and one package
#: anybody can install. In both maps, and a finding in neither.
PUBLIC_SOURCES = [
    "webpack://acme/src/app.ts",
    "webpack://acme/src/checkout.ts",
    "webpack://acme/node_modules/preact/dist/preact.module.js",
]

#: What only exists inside the organisation. Two scoped packages no public
#: registry serves, and the host they were fetched from.
PRIVATE_SOURCES = [
    "webpack://acme/node_modules/@acme-internal/billing-client/src/index.ts",
    "webpack://acme/node_modules/@acme-internal/feature-flags/src/index.ts",
]
PRIVATE_ROOT = "https://registry.acme.internal/acme/web"

#: The map for the bundle nothing loads. Public names on both variants, so the
#: reachability control is about what loads it rather than about what it says.
LEGACY_MAP = {
    "version": 3,
    "file": "legacy.js",
    "sourceRoot": "",
    "sources": ["webpack://acme/src/legacy.ts"],
    "names": [],
    "mappings": "AAAA",
}

NO_ROUTE = "no such route"


def _map(names_the_organisation: bool) -> dict:
    """The entry bundle's map. The one thing the variants disagree about.

    No `sourcesContent` on either variant, and no credential anywhere in either:
    the difference between them is a list of names, which is what this class is.
    """
    return {
        "version": 3,
        "file": "app.js",
        "sourceRoot": PRIVATE_ROOT if names_the_organisation else "",
        "sources": PUBLIC_SOURCES + (PRIVATE_SOURCES if names_the_organisation else []),
        "names": [],
        "mappings": "AAAA",
    }


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    app_map = json.dumps(_map(variant == "vulnerable"))

    #: The counter behind `/build/status`. It exists to be noisy.
    builds = [0]

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            path = urlsplit(self.path).path
            if path == "/":
                self.answer(200, "text/html", SHELL)
            elif path == "/static/app.js":
                self.answer(200, "application/javascript", APP_BUNDLE)
            elif path == "/static/app.js.map":
                # The subject.
                self.answer(200, "application/json", app_map)
            elif path == "/static/legacy.js":
                # Served, and never embedded by the shell.
                self.answer(200, "application/javascript", LEGACY_BUNDLE)
            elif path == "/static/legacy.js.map":
                self.answer(200, "application/json", json.dumps(LEGACY_MAP))
            elif path == "/build/status":
                # Noise, identically on both variants.
                builds[0] += 1
                self.answer(200, "application/json", json.dumps({"builds": builds[0]}))
            else:
                self.answer(404, "application/json", json.dumps({"error": NO_ROUTE}))

        def answer(self, status: int, content_type: str, body: str) -> None:
            payload = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: object) -> None:
            """Silent, for the reason the other fixtures' are."""

    return Fixture
