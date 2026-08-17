"""The command fixture, both variants, from one source.

A conversion route that either formats the uploaded name into a command line or
passes it as one argument. The interpreter below is a dozen lines of Python: it
splits on a separator, honours `echo` and a capped `sleep`, and converts
everything else. Nothing outside this process runs, because the class turns on a
caller's bytes being parsed as a command rather than on which shell parses them.

Standard library only, and digested rather than imported by the corpus compiler,
for the reasons the other fixtures' sources give.
"""

from __future__ import annotations

import json
import re
import time
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit


VARIANTS = ("vulnerable", "secure")

#: The most this fixture will ever wait, in seconds. The cap is here rather than
#: in the reading: a fixture that could be made to hold a connection for an
#: arbitrary time would punish the suite for a reading's mistake.
CEILING = 2.0

#: `filename="..."` in a multipart part header, which is all this route reads.
FILENAME = re.compile(rb'filename="([^"]*)"')

SESSIONS = {"s-alice-4c17": "alice"}
COOKIE = "session"

#: Fixed bodies on both variants, so that nothing here carries
#: `information_disclosure.error_detail` beside the class this pair declares.
UNAUTHENTICATED = {"error": "not authenticated"}
NO_ROUTE = {"error": "no such route"}
NO_FILE = {"error": "a request carries one file"}


def _session(header: str | None) -> str | None:
    """The user a cookie header names, or None for every other header."""
    for part in (header or "").split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name == COOKIE:
            return SESSIONS.get(value)
    return None


def _filename(body: bytes) -> str | None:
    """The submitted name, or None when the body carries no file part."""
    found = FILENAME.search(body)
    return found.group(1).decode("utf-8", "replace") if found else None


def _interpret(line: str) -> str:
    """Run one command line, for the smallest value of `run` that is honest.

    `;` ends one command and begins another, `echo` writes its argument out and
    `sleep` waits. Everything else is the conversion this route exists for.
    """
    written = []
    for command in line.split(";"):
        command = command.strip()
        if command.startswith("echo "):
            written.append(command[len("echo "):])
        elif command.startswith("sleep "):
            try:
                time.sleep(min(float(command[len("sleep "):]), CEILING))
            except ValueError:
                written.append("sleep: not a number")
        else:
            written.append("converted")
    return " ".join(written)


def _interpret_argv(argv: list[str]) -> str:
    """Run one argument list. Nothing here splits, so nothing here is a grammar."""
    return "converted" if argv and argv[0] == "convert" else "unknown command"


def handler(variant: str) -> type[BaseHTTPRequestHandler]:
    """The request handler for one variant of this fixture."""
    if variant not in VARIANTS:
        raise ValueError(f"variant is one of {list(VARIANTS)}, not {variant!r}")
    formats = variant == "vulnerable"

    #: The depth behind `/documents/queue`. It exists to be noisy.
    converted = [0]

    class Fixture(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            if self.caller() is None:
                return
            if urlsplit(self.path).path != "/documents/queue":
                self.answer(404, NO_ROUTE)
                return
            # Noise, identically on both variants: the depth moves whether or not
            # anything was submitted.
            converted[0] += 1
            self.answer(200, {"depth": converted[0] % 3, "served": converted[0]})

        def do_POST(self) -> None:  # noqa: N802 -- BaseHTTPRequestHandler's spelling
            path = urlsplit(self.path).path
            body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            if self.caller() is None:
                return
            name = _filename(body)
            if name is None:
                self.answer(400, NO_FILE)
                return
            if path == "/documents/convert":
                self.convert(name)
            elif path == "/documents/name":
                # The decoy. The name comes back and no interpreter sees it.
                self.answer(200, {"filename": name})
            else:
                self.answer(404, NO_ROUTE)

        def convert(self, name: str) -> None:
            """The subject. How the converter is called differs, not what it is."""
            if formats:
                # The defect: the name becomes part of the line, so a separator
                # in it ends the conversion and starts something else. The name
                # is the last word, as it is in every converter that takes its
                # output as an option, so what follows a separator in it is a
                # whole command rather than a command with a stray argument.
                written = _interpret("convert --output out.pdf " + name)
            else:
                # The same conversion, called with an argument list. The name is
                # one element and the interpreter never splits it.
                written = _interpret_argv(["convert", "--output", "out.pdf", name])
            # The subject does not reflect the name. `/documents/name` is where a
            # filename comes back, and keeping them apart is what stops a probe
            # token in the name from appearing in the answer on both halves.
            self.answer(200, {"output": written})

        def caller(self) -> str | None:
            """The authenticated user, or None with a `401` already written.

            The route is behind a session because the reading that grades it
            interleaves two arms and calls the separation between them a
            property of one caller's conversions.
            """
            caller = _session(self.headers.get("Cookie"))
            if caller is None:
                self.answer(401, UNAUTHENTICATED)
            return caller

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
