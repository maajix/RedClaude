"""The stored-file fixture, both variants, from one source.

An upload route whose destination name the caller chooses. One variant lets that
name decide how the stored bytes are served back; the other stores under a name
it generated and serves every upload the same way.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import json
import posixpath
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit


VARIANTS = ("vulnerable", "secure")

#: What the vulnerable variant reads off the caller's chosen name. This is the
#: whole of the defect: an extension the caller wrote decides what the server
#: later says the bytes are.
TYPES = {
    ".txt": "text/plain",
    ".html": "text/html",
    ".svg": "image/svg+xml",
    ".csv": "text/csv",
}
OPAQUE = "application/octet-stream"

#: The ceiling on what may be kept, so that a reading which forgets to clean up
#: cannot fill the process. Uploads are held in memory and nothing is written to
#: a disk anywhere.
LARGEST = 4096

SESSIONS = {"s-alice-0c93": "alice"}
COOKIE = "session"

UNAUTHENTICATED = {"error": "not authenticated"}
NO_ROUTE = {"error": "no such route"}
TOO_LARGE = {"error": "upload is too large"}
NO_UPLOAD = {"error": "no such upload"}


def _session(header: str | None) -> str | None:
    """The user a cookie header names, or None for every other header."""
    for part in (header or "").split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name == COOKIE:
            return SESSIONS.get(value)
    return None


def _name(query: str) -> str:
    """The destination name the caller asked for, reduced to its last segment.

    Both variants do this, so that a traversal in the name is nobody's finding
    here: the class this pair grades is what the name makes of the bytes, not
    where the name resolves.
    """
    asked = (parse_qs(query, keep_blank_values=True).get("name") or ["upload"])[0]
    return posixpath.basename(asked.replace("\\", "/")) or "upload"


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    keeps_the_name = variant == "vulnerable"

    #: The store, and the counter behind `/uploads/live`. Both are per-server,
    #: which is per-variant, because the two halves never share a process.
    stored: dict[str, tuple[str, bytes]] = {}
    reads = [0]

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_POST(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            parts = urlsplit(self.path)
            if self.caller() is None:
                return
            asked = _name(parts.query)
            if parts.path == "/uploads/name":
                # The decoy. The name that would be used comes back and nothing
                # is stored under it.
                self.answer(200, {"name": asked})
                return
            if parts.path != "/uploads":
                self.answer(404, NO_ROUTE)
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length > LARGEST:
                self.answer(413, TOO_LARGE)
                return
            self.store(asked, self.rfile.read(length))

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            path = urlsplit(self.path).path
            if self.caller() is None:
                return
            if path == "/uploads/live":
                # Noise, identically on both variants.
                reads[0] += 1
                self.answer(200, {"reads": reads[0]})
            elif path.startswith("/uploads/"):
                self.retrieve(path[len("/uploads/"):])
            else:
                self.answer(404, NO_ROUTE)

        def do_DELETE(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            """Cleanup, so that a reading can honour the ceiling it declared."""
            path = urlsplit(self.path).path
            if self.caller() is None:
                return
            if not path.startswith("/uploads/"):
                self.answer(404, NO_ROUTE)
            elif stored.pop(path[len("/uploads/"):], None) is None:
                self.answer(404, NO_UPLOAD)
            else:
                self.answer(200, {"removed": path[len("/uploads/"):]})

        def store(self, asked: str, body: bytes) -> None:
            """The subject. One assignment differs between the variants."""
            if keeps_the_name:
                # The defect: the caller's name is the stored name, and the
                # extension on it is what the retrieval will call these bytes.
                key = asked
                served = TYPES.get(posixpath.splitext(asked)[1].lower(), OPAQUE)
            else:
                # The defence: the stored name is this route's, the caller's
                # name is kept as a label, and what is served is not read off it.
                key = f"u{len(stored) + 1:04d}"
                served = OPAQUE
            stored[key] = (served, body)
            self.answer(201, {"stored": key, "label": asked})

        def retrieve(self, key: str) -> None:
            """The bytes back, described by whatever `store` decided."""
            found = stored.get(key)
            if found is None:
                self.answer(404, NO_UPLOAD)
                return
            served, body = found
            self.send(200, served, body,
                      () if keeps_the_name else (("Content-Disposition", "attachment"),))

        def caller(self) -> str | None:
            """The authenticated user, or None with a `401` already written."""
            caller = _session(self.headers.get("Cookie"))
            if caller is None:
                self.answer(401, UNAUTHENTICATED)
            return caller

        def answer(self, status: int, document: dict) -> None:
            self.send(status, "application/json", json.dumps(document).encode("utf-8"))

        def send(self, status: int, kind: str, body: bytes,
                 extra: tuple[tuple[str, str], ...] = ()) -> None:
            """Every response this fixture writes goes through here.

            `extra` exists for the one header the secure variant adds to a
            retrieval, which is part of what that variant does rather than a
            second way of answering.
            """
            self.send_response(status)
            self.send_header("Content-Type", kind)
            for name, value in extra:
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            """Silent, for the reason the other fixtures' are."""

    return Fixture
