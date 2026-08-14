"""The Program configuration the runtime tests are written against."""

import atexit
import contextlib
import json
import os
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from redkraken import _launch, _startup, agent, isolation, tls


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
run_tokens = 40000
run_requests = 50
lane_tokens = 500000
lane_requests = 1000
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
run_tokens = 2000
run_requests = 10
lane_tokens = 5000
lane_requests = 50
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

    def date_time_string(self, timestamp: float | None = None) -> str:
        """A fixed `Date`, so that one answer is one set of bytes.

        `BaseHTTPRequestHandler` stamps every response with the current second,
        which makes two identical answers two different transcripts whenever the
        exchanges that asked for them straddle a second boundary. The store the
        door writes to is content-addressed, so that difference is the
        difference between holding one blob and holding two -- and a suite that
        asserts the store deduped is then asserting how fast it ran.
        """
        return "Thu, 01 Jan 2026 00:00:00 GMT"

    def record(self) -> None:
        """What this target saw, in the one shape every suite reads it back in."""
        self.server.seen.append(
            (
                self.command,
                self.path,
                [(name.lower(), value) for name, value in self.headers.items()],
            )
        )

    def do_GET(self) -> None:
        self.record()
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
        # Both halves record through `Target.record`, called rather than copied:
        # what the target saw is written in one place, so a suite reading `seen`
        # after a redirect is reading the same tuple as a suite reading it after
        # a plain exchange.
        if self.path == self.answered:
            super().do_GET()
            return
        self.record()
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


class ControlUpstream:
    """The model API, on this machine, answering out of a script.

    An Agent run cannot be tested against the real API: the assertion suite has
    to run offline, on a laptop with no subscription, without spending tokens
    and without the answer changing between runs. So this is the whole upstream
    -- a CONNECT proxy that terminates TLS with the run's own authority and
    replies to `POST /v1/messages` with a canned event stream.

    It is not a stub in front of the SDK. It is a socket, and the bundled CLI
    reaches it exactly the way it reaches Anthropic: proxy variables, a root it
    was told to trust, a certificate for `api.anthropic.com`. That makes the
    child under test a real child -- real process, real transport, real
    protocol -- with only the far end replaced.

    The script is two answers. Anything with no tool result in it is answered
    with a call to `tool`, so the model asks for the runtime's tool exactly
    once; everything after that is answered with `SPOKEN` and an end of turn, so
    the run terminates rather than looping until `max_turns`.
    """

    #: What the scripted assistant says once it has its tool result. Asserted
    #: on, so a run that finished for some other reason cannot look like this.
    SPOKEN = "CONTROL_OK"

    def __init__(
        self,
        tool: str,
        *,
        arguments: dict | None = None,
        authority: tls.Authority | None = None,
        bind: tuple[str, int] = ("127.0.0.1", 0),
        watch: Callable[[str, str], None] | None = None,
    ) -> None:
        """The upstream, on loopback by default and anywhere it is asked.

        `bind`, `authority` and `watch` are what it takes to be a *peer* rather
        than a thread. The Agent boundary verifies that the proxy named in the
        URL is the one other container on an internal network, so the far end
        of a contained run reaches every address rather than loopback, is
        handed the run authority from outside instead of minting one only it
        can see, and reports what arrived on its own standard output because
        the process asserting on it is not this one.

        `arguments` is what the scripted call carries. Empty is enough for a
        tool that takes nothing; a gate that decides on an argument -- which
        role a delegation would start, which skill a call would execute -- can
        only be provoked by a call that has one.
        """
        self.tool = tool
        self.arguments = {} if arguments is None else dict(arguments)
        self.authority = authority or tls.authority(scratch() / "control-authority")
        self.certificate = self.authority.certificate
        #: One entry per request that arrived, as (host, request line).
        self.seen: list[tuple[str, str]] = []
        self._watch = watch
        self._listener = socket.socket()
        self._listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._listener.bind(bind)
        self._listener.listen(32)
        # Where the process holding this object reaches it, which is not the
        # address it was bound to: a wildcard bind is reachable from everywhere,
        # and everywhere's local name for it is loopback. A peer is reached by
        # its container name instead, which only its supervisor knows.
        host = "127.0.0.1" if bind[0] in ("", "0.0.0.0") else bind[0]
        self.url = f"http://{host}:{self._listener.getsockname()[1]}"
        self._running = True
        threading.Thread(target=self._accept, daemon=True).start()

    def stop(self) -> None:
        self._running = False
        self._listener.close()

    @property
    def completions(self) -> int:
        """How many times the scripted model was asked for one."""
        return sum(1 for _, line in self.seen if line.startswith("POST /v1/messages"))

    def _accept(self) -> None:
        while self._running:
            try:
                client, _ = self._listener.accept()
            except OSError:
                return
            threading.Thread(target=self._tunnel, args=(client,), daemon=True).start()

    def _tunnel(self, client: socket.socket) -> None:
        """One CONNECT, then the far end of it, speaking TLS for whatever it named."""
        stream = client.makefile("rb")
        line = stream.readline().decode("latin-1").strip()
        while stream.readline() not in (b"\r\n", b"\n", b""):
            pass
        if not line.startswith("CONNECT "):
            client.close()
            return
        host = line.split()[1].rsplit(":", 1)[0]
        client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        try:
            wrapped = self.authority.context(host).wrap_socket(client, server_side=True)
        except (OSError, ssl.SSLError):
            client.close()
            return
        self._serve(host, wrapped)

    def _serve(self, host: str, connection: ssl.SSLSocket) -> None:
        stream = connection.makefile("rb")
        try:
            while True:
                line, body = _request(stream)
                if not line:
                    return
                self.seen.append((host, line))
                if self._watch is not None:
                    self._watch(host, line)
                if line.startswith("POST /v1/messages"):
                    answer = self._completion(body)
                    kind = b"text/event-stream"
                else:
                    answer = b'{"control":"upstream"}'
                    kind = b"application/json"
                connection.sendall(
                    b"HTTP/1.1 200 OK\r\ncontent-type: " + kind + b"\r\n"
                    b"cache-control: no-cache\r\n"
                    + f"content-length: {len(answer)}\r\n\r\n".encode()
                    + answer
                )
        except (OSError, ssl.SSLError):
            return
        finally:
            connection.close()

    def _completion(self, body: bytes) -> bytes:
        """Ask for the tool, or speak. Whichever the conversation has not had yet."""
        if b'"tool_result"' in body:
            blocks = [
                {"type": "content_block_start", "index": 0,
                 "content_block": {"type": "text", "text": ""}},
                {"type": "content_block_delta", "index": 0,
                 "delta": {"type": "text_delta", "text": self.SPOKEN}},
                {"type": "content_block_stop", "index": 0},
            ]
            stop = "end_turn"
        else:
            blocks = [
                {"type": "content_block_start", "index": 0,
                 "content_block": {"type": "tool_use", "id": "toolu_control",
                                   "name": self.tool, "input": {}}},
                {"type": "content_block_delta", "index": 0,
                 # An object rather than an empty string: the deltas are
                 # concatenated and parsed, and `""` is not a document.
                 "delta": {"type": "input_json_delta",
                           "partial_json": json.dumps(self.arguments)}},
                {"type": "content_block_stop", "index": 0},
            ]
            stop = "tool_use"
        events = [
            {"type": "message_start",
             "message": {"id": "msg_control", "type": "message", "role": "assistant",
                         "model": "control", "content": [], "stop_reason": None,
                         "stop_sequence": None,
                         "usage": {"input_tokens": 1, "output_tokens": 1}}},
            *blocks,
            {"type": "message_delta", "delta": {"stop_reason": stop, "stop_sequence": None},
             "usage": {"output_tokens": 1}},
            {"type": "message_stop"},
        ]
        return "".join(
            f"event: {event['type']}\ndata: {json.dumps(event)}\n\n" for event in events
        ).encode()


def _request(stream) -> tuple[str, bytes]:
    """One HTTP/1.1 request off a stream, as its first line and its body."""
    line = stream.readline().decode("latin-1").strip()
    headers = {}
    while True:
        raw = stream.readline().decode("latin-1")
        if raw in ("\r\n", "\n", ""):
            break
        name, _, value = raw.partition(":")
        headers[name.strip().lower()] = value.strip()
    length = int(headers.get("content-length") or 0)
    return line, stream.read(length) if length else b""


def subscription(home: Path) -> Path:
    """A home directory holding a credential that is not one.

    The bundled CLI will not start a session without something that looks like
    an authenticated operator, so the run is given a fabricated one. It is
    inert by construction -- the token is a literal, and the only endpoint it
    is ever presented to is `ControlUpstream`, whether that is a thread on
    loopback or the one peer on an internal network -- which is the point: the
    child under test resolves *this*, not the operator's real credential, and a
    test that leaked the operator's would be a test that spent their tokens.
    """
    (home / ".claude").mkdir(parents=True, exist_ok=True)
    (home / ".claude" / ".credentials.json").write_text(
        json.dumps(
            {
                "claudeAiOauth": {
                    "accessToken": "sk-ant-oat01-synthetic-test-value",
                    "refreshToken": "sk-ant-ort01-synthetic-test-value",
                    "expiresAt": int(time.time() + 3600) * 1000,
                    "scopes": ["user:inference", "user:profile"],
                    "subscriptionType": "max",
                }
            }
        ),
        encoding="utf-8",
    )
    (home / ".claude.json").write_text(
        json.dumps({"hasCompletedOnboarding": True}), encoding="utf-8"
    )
    return home


#: The image every container proof starts from. It is a glibc one because an
#: Agent image has to be: the CLI the SDK bundles is a glibc-linked executable,
#: so a musl image is one no Agent child can start in, and a topology proved
#: about an image no Agent run could use is a proof about nothing.
AGENT_IMAGE = os.environ.get("RK_TEST_AGENT_IMAGE", "python:3.14-slim")


#: What the server calls the columns of the two answers the offline suites have
#: to spell out: `offer_slate()`'s rows and the rows the console's decision
#: queue comes back as. Both are read by name in production --
#: `execution._slate_entry` and `operator.queue` -- so a fake that named them
#: differently would keep passing while a renamed column broke the caller.
#: `RecordedColumnsTest` in the live suite asserts both against the server that
#: has them, which is what makes these names a record of it rather than a
#: second opinion about it.
SLATE_COLUMNS = (
    "ordinal", "task_label", "kind", "subject_label",
    "priority", "factors", "entitled", "expires_at",
)
DECISION_QUEUE_COLUMNS = (
    "program", "label", "question_code", "tool", "risk_class", "question",
    "requested_at", "deadline_at", "status", "answered_by", "answer",
)

#: What every container probe starts with. Here for the reason `docker` is here:
#: both container suites need it, and four copies of one preamble is how two of
#: them came to use different timeouts for the same question. The timeout only
#: bounds the answer a probe is usually asserting -- a route that is not there
#: answers by not answering -- so it is one number, and a generous one, because
#: a probe that timed out early under load would report an isolation that is
#: real as an isolation that is proven.
PROBE = """
import json, os, socket

def reaches(host, port):
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False

def resolves(host):
    try:
        socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        return True
    except OSError:
        return False

def writable(path):
    try:
        open(path, 'w').close()
        return True
    except OSError:
        return False
"""


def docker(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """One engine command, for the suites that arrange what `isolation` verifies.

    Here rather than in either container suite because both need it, and a test
    module that imported another test module would be a suite whose fixtures
    moved when a test file was renamed.
    """
    result = subprocess.run(
        ["docker", *arguments],
        env={"PATH": os.environ.get("PATH", "")},
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if check and result.returncode:
        raise AssertionError((result.stderr or result.stdout).strip())
    return result


def boundary(**overrides) -> isolation.AgentContainer:
    """One described Agent boundary, with no engine needed to describe it.

    The one builder: a described boundary and a live one differ by which names
    are real, so a second builder would be a second answer to what a boundary
    is made of.
    """
    fields = {
        "image": AGENT_IMAGE,
        "network": "rk2-agent-network",
        "proxy_container": "rk2-proxy",
        "proxy_url": "http://rk2-proxy:18080",
        "certificate": Path("/run/root.pem"),
    }
    fields.update(overrides)
    return isolation.AgentContainer(**fields)


#: A credential a launch under test really is given, so "never its value" is a
#: claim about output that had something in it to leak. One string for every
#: suite: two would let a leak through the module that did not name the one
#: being grepped for.
EXPORTED = "exported-into-the-launch"

#: The role a launch under test runs as when the test is not about roles. The
#: orchestrator, because it is the one role that holds the delegation tool, so
#: a suite that used any other would leave the widest surface untested.
ROLE = "orchestrator"


def startup_refusal(environment: dict | None = None, phase: str = "pre_spawn"):
    """One refusal, measured on inputs rather than on the machine underneath.

    The options value is nothing and the runtime facts are empty, so what comes
    back is the credential matrix's own verdict on the environment given plus
    the unmeasured runtime that says so -- the same records a child would carry
    home, without needing a child or an SDK to produce them.
    """
    violations = agent.assess(
        None,
        {"ANTHROPIC_API_KEY": EXPORTED} if environment is None else environment,
        {},
        launch_dir=scratch(),
        role=ROLE,
        managed_settings=(),
    )
    return agent.StartupRefusal(violations, phase, *_startup.KNOWN_RUNTIME)


@contextlib.contextmanager
def unlatched():
    """Provoke a startup refusal without becoming the process that refused.

    The latch is process state, and a suite is one process that refuses many
    times on purpose. Every test that lets a refusal reach `agent.agent_run`
    says so here, so the next one measures the machine rather than this
    process's memory of an earlier test. What proves the latch is
    `test_agent.LatchTest`, which uses processes of its own for this reason.
    """
    with mock.patch.object(agent, "_LATCH", None):
        yield


#: What a launcher fixture's `picks` means when nobody said: the first entry on
#: offer. A sentinel rather than `None`, because `None` is already an answer --
#: a session that called no tool and chose nothing -- and the two would
#: otherwise be the same fixture.
FIRST = object()


def latched(slate, picks: object = FIRST) -> _launch.Choice:
    """The latch a real child picks through, after it has picked.

    Shared by both launcher fixtures, which answer a session the same way and
    differ only in how they build the result around it. `_launch.Choice` is
    what the served tool writes into, so a fixture that set `choice` on the
    result directly would be reporting a pick no tool ever accepted.

    `picks` is what the child calls `pick_task` with: `FIRST` for the first
    entry it was offered, a label for one it names itself, `""` for a call that
    carried no label at all, and `None` for a session that calls nothing.
    """
    latch = _launch.Choice(slate)
    if picks is FIRST and not latch.offered:
        # Refused rather than quietly degraded: an empty slate asked for its
        # first entry is a fixture that would stand for `picks=None`, and a test
        # meaning "the child picked nothing" has to say so.
        raise AssertionError("an empty slate has no first entry: pass picks=None to pick nothing")
    wanted = latch.offered[0] if picks is FIRST else picks
    if wanted is not None:
        latch.pick({"task_label": wanted})
    return latch


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
