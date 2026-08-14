"""The production door, run inside a container so a browser can have one peer.

Run as `python3 -m tests.browser_door`, with the repository mounted read only
and every coordinate in the environment. It exists as a module rather than as a
string the suite hands to `python3 -c` for the same reason `control_upstream`
does: what runs in the container is the code under test, and code under test
belongs in a file a reviewer can read.

`proxy.serve` refuses a non-loopback bind, and it is right to -- a capability on
a routable interface is bearer material anyone who can reach the interface can
spend. This binds wide inside a container whose egress network has exactly one
other peer, and reaches for `proxy.listen`, the seam underneath `serve`, rather
than relaxing that rule for a test.

The outbound side dials the fixture twin by container name and verifies the
authority the suite issued its certificate from. The name the mission asked for
is still the name that is verified -- `server_hostname` is the plan's host, never
the container's -- so a mission that reached the right address with the wrong
certificate fails here rather than reporting the target's behaviour.
"""

import http.client
import os
import socket
import ssl
import sys
from pathlib import Path

#: The repository, as it is mounted in the container. Added conditionally
#: because the suite imports this module on the host for the marker below, and a
#: test module that rearranged the host's import path on import would be a
#: fixture with an opinion about everything else that runs beside it.
REPOSITORY = "/repo"
if os.path.isdir(REPOSITORY):
    sys.path[:0] = [f"{REPOSITORY}/src", REPOSITORY]

from redkraken import pg, proxy, seal, tls  # noqa: E402
from redkraken.store import Store  # noqa: E402

#: Printed once the socket is bound, which is what the suite waits for. A
#: readiness marker rather than a sleep: a door that is still binding when the
#: first mission starts is a flake nobody can reproduce.
LISTENING = "listening"

#: What the Receipt pins as the address the request went to. Nothing is ever
#: sent there -- `connector` below dials the twin -- but the door refuses to
#: resolve a name to an address it may not dial, and the documentation ranges
#: are among the ones it refuses, so the fixture answers with a public one.
ADDRESS = "93.184.216.34"


def connector(host, port, timeout, protocol, address, client_certificate):
    """The door's outbound side, verifying the authority the fixture issued from."""
    context = ssl.create_default_context(cafile=os.environ["RK_DOOR_TARGET_CA"])
    if client_certificate is not None:
        client_certificate.install(context)
    connection = http.client.HTTPSConnection(host, port, timeout=timeout, context=context)
    connection.sock = context.wrap_socket(
        socket.create_connection((os.environ["RK_DOOR_TARGET"], 443), timeout=timeout),
        server_hostname=host,
    )
    return connection, None


def main() -> int:
    connection = pg.connect(pg.settings_from_url(os.environ["RK_DOOR_URL"]))
    server = proxy.listen(
        ("0.0.0.0", int(os.environ["RK_DOOR_LISTEN"])),
        fence=proxy.Fence(connection),
        store=Store(Path(os.environ["RK_DOOR_STORE"])),
        connector=connector,
        resolver=lambda host, port: (ADDRESS,),
        authority=tls.authority(os.environ["RK_DOOR_AUTHORITY"]),
        # The installation's root secret, which is what lets the door open the
        # Program's required-header value. Without it every request this door
        # sees is refused as `required header missing`, so a mission that
        # reaches a page at all has already proved the door opened a credential
        # the browser was never given.
        root_secret=seal.load_root(os.environ["RK_DOOR_KEY"]),
    )
    print(LISTENING, flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
