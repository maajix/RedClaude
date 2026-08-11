"""The Program configuration the runtime tests are written against."""

import atexit
import shutil
import ssl
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from redkraken import tls


VALID = """\
schema_version = 1

[program]
name = "acme-web"
platform = "hackerone"

[rules_of_engagement]
mutation = true

[budgets]
requests = 5000
tokens = 2000000
concurrency = 2
burst = 500
window_seconds = 3600

[[scope.include]]
host = "app.example.com"
ports = [443]
protocols = ["https"]
paths = ["/api/"]

[[scope.exclude]]
host = "admin.example.com"
ports = [443]
protocols = ["https"]
paths = ["/"]

[[identity]]
name = "member"
slot_ref = "slot://identity/member"

[[required_header]]
name = "X-Bounty-Id"
value_ref = "slot://header/bounty-id"

[[callback]]
name = "oob-dns"
kind = "dns"
host = "oob.example.net"
"""


#: The configuration the scope matrix below is decided against. Wider than
#: `VALID` on purpose: a wildcard inclusion and its apex, an exclusion narrower
#: than the inclusion it sits inside, one protocol authorised and one not, a
#: path-qualified inclusion, and both kinds of callback channel. Each of those is
#: a way the Python evaluator and the SQL one could answer differently.
SCOPED = """\
schema_version = 1

[program]
name = "matrix-web"
platform = "hackerone"

[rules_of_engagement]
mutation = true

[budgets]
requests = 100
tokens = 10000
concurrency = 1
burst = 100
window_seconds = 60

[[scope.include]]
host = "*.example.com"
ports = [80, 443]
protocols = ["http", "https"]
paths = ["/"]

[[scope.include]]
host = "api.example.net"
ports = [443]
protocols = ["https"]
paths = ["/v1/"]

[[scope.exclude]]
host = "admin.example.com"
ports = [80, 443]
protocols = ["http", "https"]
paths = ["/"]

[[scope.exclude]]
host = "*.example.com"
ports = [443]
protocols = ["https"]
paths = ["/internal/"]

# An address rather than a name, which is the only kind of rule a request can
# be measured against *after* its name has been resolved. Nothing ever dials it:
# every test that reaches it is testing that the connection was not opened.
[[scope.exclude]]
host = "93.184.216.35"
ports = [80, 443]
protocols = ["http", "https"]
paths = ["/"]

[[required_header]]
name = "X-Bounty-Id"
value_ref = "slot://header/bounty-id"

[[callback]]
name = "oob-http"
kind = "http"
host = "callback.example.org"

[[callback]]
name = "oob-dns"
kind = "dns"
host = "dns.example.org"
"""

#: What every name in the egress suites resolves to, and the one address the
#: configuration above withdraws. Here rather than in either suite, because the
#: second of them has to be the address the `[[scope.exclude]]` rule names: a
#: test asserting "the Program withdrew this" and a rule written about a
#: different address would pass while proving nothing. Public, because the door
#: refuses to dial an address that is not, and deliberately not where any fixture
#: listens -- the connector is what puts a request on the loopback port, and
#: keeping the decided address apart from the dialled socket is what lets a test
#: assert that the one decided is the one handed over. One octet apart, so a rule
#: that matched loosely would match both.
PINNED = "93.184.216.34"
WITHDRAWN = "93.184.216.35"

#: The configuration is a literal so that it reads as one, so this is what keeps
#: the two agreeing: a name changed in one place and not the other would leave
#: every withdrawal test passing against a rule about some other machine.
assert f'host = "{WITHDRAWN}"' in SCOPED, "SCOPED must exclude the withdrawn address"
assert PINNED not in SCOPED, "SCOPED must say nothing about the pinned address"

#: One request, and the verdict every evaluator must reach about it: the URL,
#: the scope class and the reason. Decided in Python, through the CLI and in SQL,
#: because "the policy" is only one policy if the three agree.
SCOPE_REQUESTS = (
    ("https://app.example.com/", "target", "matched_target"),
    ("http://app.example.com/", "target", "matched_target"),
    # The trailing dot, the uppercase label and the default port are three
    # spellings of the row above.
    ("https://APP.example.com./", "target", "matched_target"),
    ("https://app.example.com:443/", "target", "matched_target"),
    # A narrower exclusion inside a wildcard inclusion wins, whatever order the
    # two were written in.
    ("https://app.example.com/internal/secrets", "denied", "excluded"),
    # ...and only where it applies: that exclusion names https on 443.
    ("http://app.example.com/internal/secrets", "target", "matched_target"),
    ("https://admin.example.com/", "denied", "excluded"),
    ("http://admin.example.com/anything", "denied", "excluded"),
    # The apex trap: `*.example.com` never covers `example.com`.
    ("https://example.com/", "denied", "unlisted"),
    ("https://api.example.net/v1/users", "target", "matched_target"),
    ("https://api.example.net/v2/users", "denied", "unlisted"),
    ("https://api.example.net:8443/v1/users", "denied", "unlisted"),
    ("http://api.example.net/v1/users", "denied", "unlisted"),
    # A traversal out of an authorised prefix is not authorised by its raw form.
    ("https://api.example.net/v1/%2e%2e/v2/users", "denied", "unlisted"),
    # The HTTP callback endpoint is reachable and is never a target.
    ("https://callback.example.org/", "egress_support", "matched_egress_support"),
    # A label beneath it is not: the listener is one endpoint, and what arrives
    # at the canary is decided by `decide_callback`, not by a request rule.
    ("https://token.callback.example.org/", "denied", "unlisted"),
    # A DNS channel is not an HTTP destination.
    ("https://dns.example.org/", "denied", "unlisted"),
    (f"https://{PINNED}/", "denied", "unlisted"),
    # An address rule matches the address it names and no neighbour of it: there
    # is no candidate ladder under an address, so `*.216.34` is not a rule and
    # the pinned address is not covered by the exclusion one octet away.
    (f"https://{WITHDRAWN}/", "denied", "excluded"),
)

#: One URL that cannot be canonicalised, and the reason. These never reach SQL:
#: the refusal happens before a rule is consulted, which is what makes the path
#: and host normalisation the caller's job in both implementations.
SCOPE_REFUSALS = (
    ("ftp://app.example.com/", "unsupported_protocol"),
    ("app.example.com/api/", "unsupported_protocol"),
    ("https://user:secret@app.example.com/", "malformed_url"),
    ("https://app.example.com:99999/", "malformed_port"),
    ("https:///v1/", "no_host"),
    ("https://app..example.com/", "malformed_host"),
    ("https://exämple.com/", "malformed_host"),
)

#: One stored entity, and the verdict the projection must reach: selector kind,
#: selector, port, path, class and reason. A host asks whether it is reachable at
#: all; a wildcard seed asks the same of a whole subtree.
SCOPE_ENTITIES = (
    ("host", "app.example.com", None, "/", "target", "matched_target"),
    ("host", "admin.example.com", None, "/", "denied", "excluded"),
    # A path-qualified inclusion still makes its host worth queueing, which is
    # the question a `host` entity asks.
    ("host", "api.example.net", None, "/", "target", "matched_target"),
    ("host", "api.example.net", None, "/v1/", "target", "matched_target"),
    ("host", "api.example.net", None, "/v2/", "denied", "unlisted"),
    ("host", "example.com", None, "/", "denied", "unlisted"),
    ("host", "other.example.org", None, "/", "denied", "unlisted"),
    ("host", "callback.example.org", None, "/", "egress_support", "matched_egress_support"),
    ("host", "app.example.com", 8080, "/", "denied", "unlisted"),
    ("host", "app.example.com", 80, "/", "target", "matched_target"),
    ("wildcard_domain", "example.com", None, "/", "target", "matched_target"),
    ("wildcard_domain", "sub.example.com", None, "/", "target", "matched_target"),
    # An exact inclusion authorises requests to the host it names and never the
    # subtree beneath it.
    ("wildcard_domain", "api.example.net", None, "/", "denied", "unlisted"),
    ("wildcard_domain", "example.org", None, "/", "denied", "unlisted"),
)


class Target(BaseHTTPRequestHandler):
    """The counterparty an egress test needs: it records and it answers.

    Shared because both proxy suites need the same thing from a target and want
    to assert different things about it -- the offline one reads what arrived,
    the live one reads what was stored -- and two copies would be two chances for
    "what the target saw" to mean two different sets of bytes.

    Appends `(command, path, headers)` to the server's own `seen` list, which the
    test owns and clears. Subclass and set `answer` to change the body.
    """

    protocol_version = "HTTP/1.1"
    answer = b'{"note":"target answered"}'
    response_headers: tuple[tuple[str, str], ...] = ()

    def do_GET(self) -> None:
        self.server.seen.append(
            (
                self.command,
                self.path,
                [(name.lower(), value) for name, value in self.headers.items()],
            )
        )
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        for name, value in self.response_headers:
            self.send_header(name, value)
        self.send_header("Content-Length", str(len(self.answer)))
        self.end_headers()
        self.wfile.write(self.answer)

    do_POST = do_GET
    do_HEAD = do_GET

    def log_message(self, format: str, *arguments: object) -> None:
        return


class Redirecting(Target):
    """A target that points somewhere else, and records having been asked.

    Answers the first request with a 303 to `elsewhere` and everything after it
    the way `Target` does, so one fixture serves both halves of a redirect chain
    and the `seen` list counts the two exchanges separately. The door does not
    follow a redirect -- the client does, back through the fence -- so a test
    that reads `seen` is reading how many times a client came back through it.
    """

    #: What the `Location` says, and what this target answers 200 for. Two names
    #: because a redirect may point at another host entirely, and then nothing
    #: comes back here at all: the second request is a request to somewhere else,
    #: decided on its own, and the door is what it has to pass through to arrive.
    elsewhere = "/followed"
    answered = "/followed"

    def do_GET(self) -> None:
        # The 200 half is `Target`'s, called rather than copied: what the target
        # saw is recorded in one place, so a suite reading `seen` after a
        # redirect is reading the same tuple as a suite reading it after a plain
        # exchange.
        if self.path == self.answered:
            super().do_GET()
            return
        self.server.seen.append(
            (
                self.command,
                self.path,
                [(name.lower(), value) for name, value in self.headers.items()],
            )
        )
        self.send_response(303)
        self.send_header("Location", self.elsewhere)
        self.send_header("Content-Length", "0")
        self.end_headers()

    do_POST = do_GET
    do_HEAD = do_GET


def counterparty(
    handler: type[BaseHTTPRequestHandler] = Target,
    context: ssl.SSLContext | None = None,
) -> tuple[ThreadingHTTPServer, threading.Thread]:
    """One target, on a port of its own, already serving and already recording.

    The `seen` list has to exist before the first request arrives and the port
    has to be bound before it is named in a URL, so the four lines that arrange
    that live here rather than in each suite's setup: a copy that forgot `seen`
    fails inside a handler thread, where the failure is a log line and not a test.

    With a `context` the listening socket is wrapped rather than each accepted
    connection, so a handshake that fails -- which is what a client trusting the
    wrong root looks like -- fails inside `get_request`, where `TCPServer`
    already answers `OSError` by dropping the connection instead of printing a
    traceback. It is wrapped before the thread starts, because a socket the
    serving thread is already selecting on is not one to replace.
    """
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.seen = []
    server.daemon_threads = True
    if context is not None:
        server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def tls_counterparty(
    handler: type[BaseHTTPRequestHandler] = Target,
) -> tuple[ThreadingHTTPServer, threading.Thread, Path]:
    """The same target, behind TLS, under an authority that is not the run's.

    Not the run's on purpose. The door's authority exists so the *agent* accepts
    the door; a target that shared it would make a client trusting only the run
    root succeed against the target directly, and the trust boundary this ticket
    is about would be untested. So there are two roots here: one the agent is
    given, and one only the door's own outbound side would have.
    """
    made = tls.authority(scratch() / "target-authority")
    server, thread = counterparty(handler, made.context("127.0.0.1"))
    return server, thread, made.certificate


def scratch() -> Path:
    """A directory of this run's own, removed when the run ends."""
    return Path(tempfile.mkdtemp(dir=_ROOT))


def write(text: str, name: str = "program.toml") -> Path:
    """Put one configuration in a directory of its own, so writes are visible."""
    source = scratch() / name
    source.write_text(text, encoding="utf-8")
    return source


#: One root for everything the suite writes, so a run leaves nothing behind.
_ROOT = tempfile.mkdtemp(prefix="redkraken-tests-")
atexit.register(shutil.rmtree, _ROOT, ignore_errors=True)
