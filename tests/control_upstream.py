"""`fixtures.ControlUpstream` as a container peer, for the contained Agent run.

An Agent child starts inside `redkraken.isolation`, which verifies that the
proxy named in its URL is the one other container attached to an internal
network. So the model API a real child talks to cannot be a thread on the test
process's loopback: it has to be a peer. This is the entry point that makes it
one.

Nothing about the upstream changes here. The authority is mounted in rather
than minted, so the supervisor can hand the child the certificate it will be
shown; every request line is printed as it arrives, because the process
asserting on them is on the other side of a container boundary and reads them
back from the log; and the process then does nothing at all, because the run
under test is the one that ends.

Run as `python -m tests.control_upstream <tool> <authority-dir> <port>
[arguments-json] [marker]`. The fourth is what the scripted call carries, for
the runs whose subject is a gate that decides on an argument rather than on a
name; the fifth is a line the upstream reports having seen in what the child
sent up, for the runs whose subject is what reached the model.
"""

from __future__ import annotations

import json
import sys
import threading

from redkraken import tls
from tests import fixtures


#: Printed once the socket is accepting, so a supervisor can wait for the peer
#: rather than for a duration it guessed.
LISTENING = "control-upstream listening"


def main(argv: list[str]) -> int:
    tool, directory, port = argv[1], argv[2], int(argv[3])
    fixtures.ControlUpstream(
        tool,
        arguments=json.loads(argv[4]) if len(argv) > 4 else None,
        authority=tls.authority(directory),
        bind=("0.0.0.0", port),
        watch=lambda host, line: print(f"{host}\t{line}", flush=True),
        marker=argv[5] if len(argv) > 5 else "",
    )
    print(LISTENING, flush=True)
    threading.Event().wait()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
