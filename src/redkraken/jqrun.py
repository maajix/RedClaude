"""The half of a `jq` call that runs inside the container.

This file is not imported by anything. It is staged into `/input` and run by
the container's own interpreter, for `jsscan.py`'s reason: the boundary an
offline tool runs behind has no `redkraken` on its path. It imports nothing
outside the standard library, and the registry row that names it --
`offline_tools.analyser` -- is what puts it there.

It exists because of one fact about this harness that jq cannot know. Every
Artifact the door files is the whole exchange -- `artifacts.content_type` is
`message/http` for all of them -- so a JSON response arrives with a status line
and a header block in front of it, and jq meets `HTTP/1.1 200 OK` where it
expects a value. Measured on this engagement before the file existed: forty-two
`jq` runs, forty-two `parse error: Invalid numeric literal at line 1, column 9`,
exit 5 every time.

`jsscan.py` already applies this rule and reports how many bytes it skipped.
jq is a binary and has nowhere to keep it, so the rule lives here and jq is
handed the body on stdin. What jq writes is passed through untouched: this file
decides what jq reads and nothing about what jq answers.

The carrier rule is `jsscan.carried_body`'s, deliberately character for
character, and `tests/test_jqrun.py` holds the two against each other. Two
copies of a rule is one place to forget; a test that fails when they disagree
is the cheapest thing that is not a shared import, and a shared import is not
available to a file that is mounted alone.
"""

from __future__ import annotations

import os
import subprocess
import sys

#: The wrapper's own version, and the shape `offline_tools.version_pattern`
#: admits. jq's version is asked of jq and printed beside it, so the row
#: records both what this harness shipped and what the image holds -- a
#: wrapper that reported only itself would hide the tool it is wrapping.
VERSION = "rk2-jq 1"

#: Where jq is in the tool image. A fixed path rather than a search, for the
#: reason the registry gives `offline_tools.executable`: what ran is a fact the
#: run records, and a `PATH` lookup is a fact about the environment.
JQ = "/usr/bin/jq"

#: What `proxy.transcript` writes in front of a response, and the separator it
#: puts between the head and the body. `jsscan.CARRIER` and
#: `jsscan.CARRIER_BREAK`, which is what the test compares.
CARRIER = b"HTTP/1."
CARRIER_BREAK = b"\r\n\r\n"


def carried_body(raw: bytes) -> tuple[bytes, int]:
    """The bytes to read, and how many an HTTP carrier took in front of them.

    Zero means the input was not a response and is returned whole, which is the
    case for anything an operator filed by hand.

    Deliberately strict about what a response is, for `jsscan.carried_body`'s
    reason: a rule that cut at the first blank line would discard the top of
    any file that happens to hold one. The start line and the CRLF separator
    together are what `transcript` writes and what nothing else does.
    """
    if not raw.startswith(CARRIER):
        return raw, 0
    cut = raw.find(CARRIER_BREAK)
    if cut < 0:
        return raw, 0
    return raw[cut + len(CARRIER_BREAK):], cut + len(CARRIER_BREAK)


def version() -> int:
    """Say what this is, and what jq underneath it is.

    Asked of jq rather than pinned here, because the registry's whole reason
    for a version probe is that the image answers for what the image holds.
    """
    try:
        asked = subprocess.run(
            [JQ, "--version"], capture_output=True, text=True, check=False, timeout=10
        )
    except OSError as error:
        sys.stderr.write(f"{JQ} is not in this image: {error}\n")
        return 2
    reported = asked.stdout.strip().splitlines()
    if asked.returncode != 0 or not reported:
        sys.stderr.write(f"{JQ} cannot say what version it is\n")
        return 2
    sys.stdout.write(f"{VERSION} ({reported[0].strip()})\n")
    return 0


def main(argv: list[str]) -> int:
    if len(argv) > 1 and argv[1] == "--version":
        return version()
    # `[analyser, tool, filter, input]`, which is what `open_offline_tool_run`
    # builds: the analyser path and the registry key first, then the arguments
    # in `offline_tool_arguments.position` order.
    if len(argv) != 4 or argv[1] != "jq":
        sys.stderr.write(f"usage: {os.path.basename(argv[0])} jq <filter> <artifact>\n")
        return 2

    try:
        with open(argv[3], "rb") as handle:
            raw = handle.read()
    except OSError as error:
        sys.stderr.write(f"the input could not be read: {error}\n")
        return 2

    body, carried = carried_body(raw)
    if carried:
        # On stderr, because stdout is jq's answer and nothing else. The run
        # keeps both streams, so this is where a reader finds out that what jq
        # was given is not what the Artifact holds byte for byte.
        sys.stderr.write(f"{VERSION}: skipped {carried} carrier byte(s) of {len(raw)}\n")

    try:
        answer = subprocess.run([JQ, argv[2]], input=body, capture_output=True, check=False)
    except OSError as error:
        sys.stderr.write(f"{JQ} could not be run: {error}\n")
        return 2

    # Passed through whole, including the exit code: jq's 1, 4 and 5 each mean
    # something a caller acts on, and a wrapper that flattened them would turn
    # "the filter matched nothing" into "the tool failed".
    sys.stdout.flush()
    sys.stdout.buffer.write(answer.stdout)
    sys.stdout.buffer.flush()
    sys.stderr.buffer.write(answer.stderr)
    sys.stderr.buffer.flush()
    return answer.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
