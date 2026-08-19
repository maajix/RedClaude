"""The out-of-band endpoint this harness owns end to end.

Every other channel in this tree is somebody else's: a hosted OOB service
answers a fixed body at a name it chose, and the fetch of that body is not
something we can see. Two things follow that a live engagement runs into
immediately. An XXE against a target that resolves external entities needs a DTD
the target can fetch, and a canary that answers a fixed string cannot carry one.
And the fetch itself is exactly the evidence the channel exists to produce -- an
inbound request caused by our payload -- so it belongs on the record rather than
in a terminal somebody had open.

So this module is a file host and the lifecycle of the name in front of it.

`serve` publishes one directory over loopback and treats every request as
evidence: the first path segment is the correlator, the rest is the payload's
business, and what arrives is stored and filed through the same writer
`rk callback accept` uses. Isolation is decided once, at startup, over the whole
directory -- a file that is not publishable is a refusal to start rather than a
request that gets a 404, because an operator who put something else in there is
an operator who does not know what is published.

`up`, `status` and `down` are the name. A quick tunnel's hostname is a fact
about today: it is read out of the tunnel's own output, stored as the binding's
evidence, and written to `callback_channel_bindings`, which is the only place
anything may learn it from. `down` releases it, and every correlator minted
against that binding dies with it -- not by a cleanup somebody has to remember,
but because a correlator names its binding and a released binding resolves to
nothing.

What is deliberately not here: the tunnel is not supervised, restarted or
health-checked after `up` returns. A tunnel that dies takes its name with it,
which is the safe direction, and the next `up` releases the binding whose
process is gone before it binds anything.
"""

from __future__ import annotations

import http.client
import http.server
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from redkraken import callback, migrate, pg, proxy, scope
from redkraken.outcome import INVALID_CONFIGURATION, Ledger, Report, report
from redkraken.store import Store


COMMAND = "oob"
SERVE = f"{COMMAND} serve"
UP = f"{COMMAND} up"
STATUS = f"{COMMAND} status"
DOWN = f"{COMMAND} down"

#: Where the published directories live, one per Program. An environment
#: variable rather than a fixed path because the operator picks the disk, and a
#: directory beneath it rather than the variable itself because two Programs
#: publishing into one directory would be two engagements sharing a file host.
ROOT_VARIABLE = "RK_OOB_ROOT"

#: What may be published. An allowlist, and a short one: these are the shapes an
#: engagement file takes when the point is to be fetched and parsed by something
#: on the target side. Anything else in the directory is a refusal to start.
PUBLISHABLE = (".dtd", ".html", ".js", ".json", ".svg", ".txt", ".xml", ".xsl")

#: Said rather than sniffed, for the same reason the store says what it holds.
#: `application/octet-stream` is not in this map because every suffix that may
#: be published is.
CONTENT_TYPES = {
    ".dtd": "application/xml-dtd",
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".txt": "text/plain; charset=utf-8",
    ".xml": "application/xml",
    ".xsl": "application/xslt+xml",
}

#: One engagement file. A DTD that does not fit in this is not an engagement
#: file, and the whole directory is held in memory while the publisher runs.
MAX_FILE_BYTES = 1 << 20

#: And the directory. Both ceilings are startup refusals, so a publisher that
#: started is one whose memory footprint is already known.
MAX_ROOT_BYTES = 8 << 20

#: The one path this publisher answers that is not a canary, and the only Host
#: that may ask for it. A quick tunnel routes by hostname, so nothing arriving
#: through the edge can carry this one: the check is what `rk oob up` uses to
#: refuse binding a name in front of nothing.
HEALTH_PATH = "/health"

#: The shape a correlator is minted in, which is the shape the SQL readers
#: `callback_correlator_label` and `callback_correlator_from_path` accept. A
#: first segment of any other shape names no canary that could exist, so it is
#: not a name this publisher takes to the database at all.
CORRELATOR = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")

#: The hostname a quick tunnel prints, once, in its own log.
QUICK_TUNNEL = re.compile(r"https://([a-z0-9][a-z0-9-]*\.trycloudflare\.com)")

#: What `rk oob up` runs. Not a path, so it is found the way the operator
#: installed it, and refused with its name when it is not there at all.
TUNNEL_BINARY = "cloudflared"

#: How long to wait for a tunnel to print its name before giving up on it.
TUNNEL_TIMEOUT = 60.0

#: How often to look for it in the meantime.
TUNNEL_POLL = 0.25

#: How long the publisher gets to answer the readiness question. It is a local
#: socket serving one word out of memory; a second is generous.
PROBE_TIMEOUT = 1.0

#: The loopback port the publisher listens on and `rk oob up` points a tunnel
#: at when nobody says otherwise. Shared, because the two commands have to agree
#: and a default only one of them had would be two ports.
DEFAULT_PORT = 8787

#: The provider this ticket implements. A named tunnel on a hosted zone is the
#: same binding table and the same publisher with a different word here.
QUICK_PROVIDER = "cloudflare-quick"

RESOLVE = "SELECT channel_name, channel_placement FROM resolve_callback_correlator($1)"
BIND = "SELECT bind_callback_channel($1, $2, $3, $4, $5::jsonb)"
RELEASE = "SELECT release_callback_binding($1::uuid)"
BINDING = callback.BINDING
LIVE_BINDINGS = (
    "SELECT id::text, channel_name, endpoint_host, tunnel_pid"
    "  FROM callback_channel_bindings"
    " WHERE program_id = rk2_program() AND released_at IS NULL"
)


@dataclass(frozen=True)
class Published:
    """The directory as it was at startup, and nothing that came later.

    Read once and held, which is what makes the isolation rules decidable: a
    request is answered out of this mapping, so there is no path to resolve, no
    parent to compare against the root and no window between checking a file and
    opening it. A file added while the publisher runs is not published, and that
    is the same rule as a file that was never there -- an operator changing what
    is published restarts the publisher, which re-reads and re-checks.
    """

    root: Path
    files: dict[str, bytes]

    def byte_size(self) -> int:
        return sum(len(body) for body in self.files.values())


def publishable(ledger: Ledger, base: Path | None, slug: str, configuration_path: Path) -> Published | None:
    """The directory this Program publishes, or the reason it may not be published.

    Every rule here is decided once, before a socket is bound, and every one of
    them is a refusal rather than a file quietly left out. That is the whole
    posture: what a target can fetch from this machine is a list an operator can
    read, and a publisher that started is one whose list was checked.

    The rules, and what each is guarding against:

    * The root is `$RK_OOB_ROOT/<slug>/` and nothing else, so publishing is a
      directory somebody made on purpose rather than a path somebody typed.
    * No symlink -- not the root, not anything in it. A symlink is a file whose
      contents are somewhere the checks below never looked.
    * Nothing but regular files with a publishable suffix, no subdirectories and
      no dotfiles. A directory would be a second namespace with its own rules;
      a dotfile is the shape of the things that end up in a directory by
      accident.
    * Not the configuration's own directory, not `$HOME`, and nothing holding a
      `.git`. Those are the three directories a slip would most plausibly point
      at, and each of them holds material the whole harness exists to keep out
      of a target's reach.
    * A ceiling per file and a ceiling over the lot, because the directory is
      held in memory for as long as the publisher runs.
    """
    if base is None:
        ledger.fail(
            "oob_root",
            f"no publish root: set ${ROOT_VARIABLE} to the directory holding the "
            f"per-Program publish roots",
            code=INVALID_CONFIGURATION,
            source=f"environment:{ROOT_VARIABLE}",
        )
        return None
    root = Path(base) / slug
    if not root.is_dir() or root.is_symlink():
        ledger.fail(
            "oob_root",
            f"{root} is not a directory this Program publishes from; "
            f"a publish root is ${ROOT_VARIABLE}/{slug} and is not a symlink",
            code=INVALID_CONFIGURATION,
            source=f"environment:{ROOT_VARIABLE}",
        )
        return None

    resolved = root.resolve()
    forbidden = _forbidden(resolved, Path(configuration_path).resolve())
    if forbidden is not None:
        ledger.fail(
            "oob_root",
            f"{root} is not publishable: {forbidden}",
            code=INVALID_CONFIGURATION,
            source=f"environment:{ROOT_VARIABLE}",
        )
        return None

    files: dict[str, bytes] = {}
    total = 0
    for entry in sorted(root.iterdir()):
        refusal = _unpublishable(entry)
        if refusal is not None:
            ledger.fail(
                "oob_file",
                f"{entry.name} is in the publish root and {refusal}; a publisher "
                "serves a directory an operator can read, so this is a refusal "
                "to start rather than a file left out",
                code=INVALID_CONFIGURATION,
                source=f"environment:{ROOT_VARIABLE}",
            )
            return None
        body = entry.read_bytes()
        total += len(body)
        if total > MAX_ROOT_BYTES:
            ledger.fail(
                "oob_root",
                f"{root} holds more than {MAX_ROOT_BYTES} byte(s) of engagement "
                "files; the directory is held in memory while the publisher runs",
                code=INVALID_CONFIGURATION,
                source=f"environment:{ROOT_VARIABLE}",
            )
            return None
        files[entry.name] = body

    if not files:
        ledger.fail(
            "oob_root",
            f"{root} holds no engagement files; a publisher with nothing to "
            "publish is a name in front of nothing",
            code=INVALID_CONFIGURATION,
            source=f"environment:{ROOT_VARIABLE}",
        )
        return None
    return Published(root=resolved, files=files)


def _forbidden(root: Path, configuration: Path) -> str | None:
    """Why this resolved directory must not be a publish root, or nothing."""
    if root == Path.home().resolve():
        return "it is the home directory"
    if (root / ".git").exists():
        return "it holds a .git, so it is a working tree rather than a publish root"
    if root in configuration.parents:
        return f"the configuration {configuration.name} is inside it"
    return None


def _unpublishable(entry: Path) -> str | None:
    """Why this directory entry may not be published, or nothing."""
    if entry.is_symlink():
        return "is a symlink, whose contents are somewhere these checks did not look"
    if not entry.is_file():
        return "is not a regular file"
    if entry.name.startswith("."):
        return "is a dotfile"
    if entry.suffix not in PUBLISHABLE:
        return "does not carry a publishable suffix (" + " ".join(PUBLISHABLE) + ")"
    if entry.stat().st_size > MAX_FILE_BYTES:
        return f"is larger than {MAX_FILE_BYTES} byte(s)"
    return None


#: The one address this publisher may listen on. Not an argument, because the
#: only thing that should reach it is the tunnel process on this machine, and a
#: knob that can be set to `0.0.0.0` is a knob somebody sets to `0.0.0.0`.
LISTEN_HOST = "127.0.0.1"


class Listener(http.server.HTTPServer):
    """The socket, plus the four things a request needs to be answered.

    Single-threaded on purpose: one database connection is held for the life of
    the publisher and a connection is not shared between threads. The volume
    this serves is one fetch per payload, so serialising them costs nothing and
    removes the class of bug where two arrivals interleave inside one session.
    """

    def __init__(
        self,
        address: tuple[str, int],
        published: Published,
        connection: pg.Connection,
        keep: Store,
        note: Callable[[str], None],
        channel: str,
    ) -> None:
        super().__init__(address, Request)
        self.published = published
        self.connection = connection
        self.keep = keep
        self.note = note
        #: The one channel this publisher serves. A correlator is minted against
        #: a channel and a channel is bound to one name, so a correlator of some
        #: other channel arriving here is a request this host has no file for --
        #: and handing one over would publish the engagement to whoever learned
        #: a correlator we never pointed at this name.
        self.channel = channel
        self.answered = 0
        self.recorded = 0
        #: Arrivals nobody could attribute: the first segment resolved no live
        #: correlator of this Program, so there was nothing to file them under.
        self.refused = 0
        #: And arrivals that were attributable and the writer refused, which is
        #: a different thing to have to explain and is counted apart from them.
        self.lost = 0
        #: Arrivals whose correlator is live on another channel of this Program.
        #: Attributable, and not to anything this host serves: counted apart
        #: from both, because a stranger's probe and a canary that came in the
        #: wrong door are different things for an operator to read.
        self.misdirected = 0


class Request(http.server.BaseHTTPRequestHandler):
    """One fetch: answered out of the published mapping, then put on the record.

    `GET` and `HEAD` and nothing else, because the only thing this host does is
    hand over a file somebody put there. There is no listing: a directory index
    would tell a target what else we are publishing, which is a question it has
    no business asking, and the answer would name the other canaries' files.
    """

    server_version = "rk-oob"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    #: Seconds one connection may be silent for. `HTTPServer` here is
    #: single-threaded on purpose -- the publisher answers one target at a time
    #: and its state is one mapping -- and `HTTP/1.1` keeps a connection open
    #: between requests, so without this one idle keep-alive through the tunnel
    #: blocks the next `readline` forever and the host stops answering anybody.
    #: `handle_one_request` turns the timeout into a closed connection.
    timeout = 30.0

    #: The most of a declared request body this host will read before answering.
    #: It reads one at all so that a `GET` carrying `Content-Length` does not
    #: leave its body in the buffer to be parsed as the next request line, and
    #: it stops here because the body is not what this host is for: a target
    #: that sent more than this gets its connection closed rather than its
    #: request answered off a desynchronised stream.
    MAX_BODY_BYTES = 64 * 1024

    def do_GET(self) -> None:
        self._answer(with_body=True)

    def do_HEAD(self) -> None:
        self._answer(with_body=False)

    def _body(self) -> bytes:
        """Whatever the request declared, read off the stream before answering.

        Returned rather than discarded because it is part of what arrived, and
        the transcript this host files is the request bytes a reader weighs.
        """
        try:
            declared = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self.close_connection = True
            return b""
        if declared <= 0:
            return b""
        if declared > self.MAX_BODY_BYTES:
            self.close_connection = True
            return b""
        return self.rfile.read(declared)

    def _arrived_by_another_method(self) -> None:
        """A method this host does not answer, from a target that still fired.

        The payload is what decides the method, not us: an entity resolver
        fetches, and a server-side request forged by something we planted may
        POST. Refusing it before the correlator is read would throw away the
        observation the canary exists to make, so the arrival is recorded and
        then refused -- which is the same order `_answer` uses, and the opposite
        of what `send_error` on an unhandled verb did.

        The connection closes rather than reading a body: a request body here is
        bytes a target chose the length of, and 405 is the whole answer.
        """
        self.close_connection = True
        listener: Listener = self.server
        listener.answered += 1
        correlator, _ = _requested(self.path)
        if correlator is not None and self._serves(correlator):
            self._record(listener, correlator, self.headers.get("Host", ""), self.path)
        self.send_response(405)
        self.send_header("Allow", "GET, HEAD")
        self.send_header("Content-Length", "0")
        self.send_header("Connection", "close")
        self.end_headers()

    do_POST = _arrived_by_another_method
    do_PUT = _arrived_by_another_method
    do_PATCH = _arrived_by_another_method
    do_DELETE = _arrived_by_another_method
    do_OPTIONS = _arrived_by_another_method

    def log_message(self, format: str, *args: object) -> None:
        """Every line through the publisher's own note, never through stderr.

        `BaseHTTPRequestHandler` writes to `sys.stderr` by default, which for a
        command whose report is machine-read is output nobody asked for in the
        middle of it.

        Control characters are translated the way CPython's own `log_message`
        translates them, which this override would otherwise drop: the request
        target is a target's bytes, and an operator reading the publisher's
        notes should not have their terminal written to by one.
        """
        self.server.note((format % args).translate(self._control_char_table))

    def _answer(self, with_body: bool) -> None:
        listener: Listener = self.server
        target = self.path
        host = self.headers.get("Host", "")
        # Before anything is written back, because the response goes out on the
        # same connection the body is still sitting in.
        arrived = self._body()

        if target == HEALTH_PATH and host == f"{LISTEN_HOST}:{listener.server_address[1]}":
            # Asked by `rk oob up` before it binds a name, and answerable by
            # nothing that came through the tunnel: a quick tunnel routes by
            # hostname and sends its own, so this Host cannot arrive from there.
            # Counted by nothing: `answered` is what targets fetched, and an
            # operator's own probe in that number is a number about us.
            self._send(200, "text/plain; charset=utf-8", b"ok", with_body=with_body)
            return

        listener.answered += 1

        correlator, name = _requested(target)
        if correlator is None:
            listener.refused += 1
            self.log_message("%s names no correlator", target)
            self._send(404, "text/plain; charset=utf-8", b"not found", with_body=with_body)
            return

        if not self._serves(correlator):
            self._send(404, "text/plain; charset=utf-8", b"not found", with_body=with_body)
            return

        body = listener.published.files.get(name) if name is not None else None
        self._send(
            200 if body is not None else 404,
            # Keyed rather than defaulted: a published name carries a
            # `PUBLISHABLE` suffix, startup refuses the root otherwise, and the
            # map is total over those eight. The name that is not published is
            # the refusal above and reads as one -- an `application/octet-stream`
            # fallback would have answered a spelling nobody published with a
            # type this host says at line 74 it does not serve.
            CONTENT_TYPES[Path(name).suffix]
            if body is not None
            else "text/plain; charset=utf-8",
            body if body is not None else b"not found",
            with_body=with_body,
        )
        # After the answer, because the fetch is what the target did and the
        # record is what we make of it. A file that is not there is still an
        # arrival: the payload fired and reached us, which is the observation.
        self._record(listener, correlator, host, target, arrived)

    def _serves(self, correlator: str) -> bool:
        """Whether this correlator is live on the channel this host publishes.

        Two questions, and the second is the one a global store of files makes
        necessary: a correlator may be live and belong to another channel of the
        same Program -- a DNS canary, or a second tunnel -- and this publisher
        holds the Program's files, not that channel's. Answering such a request
        out of the mapping would hand the engagement's payloads to whoever
        learned a name we never pointed here, and the record that followed would
        be refused by the writer anyway, because an arrival states a path and a
        channel that carries its correlator in a label states none.
        """
        listener: Listener = self.server
        channel = _resolves(listener.connection, correlator)
        if channel is None:
            # Nothing to attribute it to. A row naming no correlator would be a
            # claim about a target nobody can stand behind, so this arrival gets
            # an answer and a log line and no record.
            listener.refused += 1
            self.log_message("%s resolves no live correlator of this Program", self.path)
            return False
        if channel != listener.channel:
            listener.misdirected += 1
            self.log_message(
                "%s resolves a correlator of channel %s, which this host does not serve",
                self.path,
                channel,
            )
            return False
        return True

    def _record(
        self,
        listener: Listener,
        correlator: str,
        host: str,
        target: str,
        arrived: bytes = b"",
    ) -> None:
        arrival = {
            "host": host.rsplit(":", 1)[0] if host.count(":") == 1 else host,
            "arrival_kind": "http",
            # Everything that reaches this host is a client: a quick tunnel
            # forwards the fetch itself rather than a resolver's question about
            # where to send it.
            "peer_class": "client",
            # No peer address: the interaction has no column for one, and the
            # only address this process can see is the tunnel's own end of the
            # loopback socket. The fetcher's address is in `Cf-Connecting-Ip`,
            # which is a header the tunnel wrote and is stored verbatim in the
            # transcript below -- evidence a reader can weigh, rather than a
            # field the schema would present as a fact about the peer.
            "received_at": None,
            "path": target,
        }
        raw = proxy.transcript(self.requestline, list(self.headers.items()), arrived)
        try:
            answer, _, _ = callback.record(
                listener.connection, listener.keep, correlator, arrival, raw,
                actor=f"rk {SERVE}",
            )
        except pg.DatabaseError as error:
            # The answer is already sent, and a publisher that fell over on a
            # refused write would be one a target could stop by sending a
            # request the writer does not like.
            listener.lost += 1
            self.log_message("%s was not recorded: %s", target, error)
            return
        listener.recorded += 1
        self.log_message(
            "%s recorded as interaction %s, observation %s%s",
            target,
            answer.get("interaction"),
            answer.get("observation"),
            " (already on the record)" if answer.get("duplicate") else "",
        )

    def _send(self, status: int, content_type: str, body: bytes, *, with_body: bool) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if with_body:
            self.wfile.write(body)


def _requested(target: str) -> tuple[str | None, str | None]:
    """The correlator a request target claims, and the file it names beneath it.

    The correlator is the first segment and everything after it is the payload's
    business, which is the rule the database reads a path by. The file is the
    second segment when there is exactly one and it is not a dotfile: the
    address `rk callback provision` prints ends at the correlator's directory,
    so `/<correlator>/` names a canary and no file, and a target that walks
    deeper names one this host does not publish. Both are still arrivals -- the
    payload fired and reached us -- and neither is answered with anything.

    There is no path resolution here and nothing is opened by name: the file is
    looked up in the mapping the publisher read at startup, so traversal is not
    a check that has to be got right, it is a shape that has nowhere to go.
    """
    segments = target.split("?", 1)[0].split("/")
    if len(segments) < 2 or segments[0] != "" or not CORRELATOR.match(segments[1]):
        return None, None
    name = segments[2] if len(segments) == 3 else ""
    if not name or name.startswith("."):
        return segments[1], None
    return segments[1], name


def _resolves(connection: pg.Connection, correlator: str) -> str | None:
    """The channel a correlator is live on, or nothing when it is not live.

    `resolve_callback_correlator` is the one place that question is answered,
    and it is the place that knows a correlator whose binding was released is no
    longer reachable -- which is what makes yesterday's canary answer 404 this
    morning without anything having been cleaned up.
    """
    rows = connection.execute(RESOLVE, (correlator,)).rows
    return str(rows[0][0]) if rows else None


def serve(
    runtime: pg.Settings | None,
    configuration_path: Path,
    channel: str,
    *,
    store: Path,
    port: int,
    root: Path | None = None,
    announce: Callable[[str], None] | None = None,
    note: Callable[[str], None] | None = None,
) -> Report:
    """Publish one directory over loopback until the publisher is interrupted.

    The directory is checked and read before a socket is bound, so an operator
    who put something unpublishable in there learns that instead of finding out
    when a target fetches it. The channel is checked too: a publisher only makes
    sense for a channel that carries its correlator in the path, because one
    bound hostname has no labels to vary.

    `announce` is called with the address the moment the socket is bound and
    before anything is served on it, which is what `rk oob up` waits for. The
    report is written when the listener closes, which is far too late to be a
    readiness signal.

    `root` is the directory holding the per-Program publish roots, and there is
    no flag for it: the root is `$RK_OOB_ROOT/<slug>/` and refuses to be
    anything else, so the keyword exists for the tests, which need a temporary
    directory without an environment the whole process shares.
    """
    ledger = Ledger()
    facts: dict[str, object] = {"program_id": None, "oob": None}

    policy, slug = callback.policy_for(ledger, configuration_path)
    if policy is None or slug is None:
        return report(SERVE, ledger, **facts)
    endpoint = _channel(ledger, policy, slug, channel, SERVE)
    if endpoint is None:
        return report(SERVE, ledger, **facts)
    if endpoint.placement != "path":
        ledger.fail(
            "oob_channel",
            f"channel {channel} carries its correlator in the {endpoint.placement}; "
            "a publisher serves one hostname, which has no labels to vary",
            code=INVALID_CONFIGURATION,
            source="argument:--channel",
        )
        return report(SERVE, ledger, **facts)

    published = publishable(
        ledger, root or _root_from_environment(), slug, Path(configuration_path)
    )
    if published is None:
        return report(SERVE, ledger, **facts)

    connection = migrate.open_connection(ledger, runtime)
    if connection is None:
        return report(SERVE, ledger, **facts)
    with connection:
        program_id = callback.open_program(ledger, connection, slug)
        if program_id is None:
            return report(SERVE, ledger, **facts)
        facts["program_id"] = program_id

        speak = note if note is not None else _to_stderr
        try:
            listener = Listener(
                (LISTEN_HOST, port), published, connection, Store(Path(store)), speak, channel
            )
        except OSError as error:
            ledger.fail(
                "oob_listener",
                f"cannot listen on {LISTEN_HOST}:{port}: {error}",
                code=INVALID_CONFIGURATION,
                source="argument:--port",
            )
            return report(SERVE, ledger, **facts)

        bound = listener.server_address[1]
        with listener:
            if announce is not None:
                announce(f"{LISTEN_HOST}:{bound}")
            speak(
                f"publishing {len(published.files)} file(s) for channel {channel} "
                f"on {LISTEN_HOST}:{bound}"
            )
            try:
                listener.serve_forever()
            except KeyboardInterrupt:
                speak("interrupted")

    facts["oob"] = {
        "channel": channel,
        "address": f"{LISTEN_HOST}:{bound}",
        "root": str(published.root),
        "files": sorted(published.files),
        "byte_size": published.byte_size(),
        "answered": listener.answered,
        "recorded": listener.recorded,
        "unattributed": listener.refused,
        "misdirected": listener.misdirected,
        "unrecorded": listener.lost,
    }
    ledger.hold(
        "oob",
        f"published {len(published.files)} file(s) on {LISTEN_HOST}:{bound}: "
        f"{listener.answered} request(s) answered, {listener.recorded} recorded, "
        f"{listener.refused} attributable to nothing, {listener.lost} the writer "
        "refused",
    )
    return report(SERVE, ledger, **facts)


def up(
    runtime: pg.Settings | None,
    configuration_path: Path,
    channel: str,
    *,
    store: Path,
    port: int,
    binary: str = TUNNEL_BINARY,
    timeout: float = TUNNEL_TIMEOUT,
) -> Report:
    """Start a tunnel, read the name it was given, and bind it to the channel.

    In that order and with two refusals in front of it. A binding whose tunnel
    process is gone is released first, because an overnight pause and a restart
    in the morning is the ordinary path and the old name must not survive it.
    Then the publisher is asked whether it is listening, because a bound name in
    front of nothing is a name an agent will embed in a payload.

    The tunnel's own output is the evidence: the hostname is printed there once
    and nowhere else, so the bytes it was read from are stored and the binding
    cites them. A binding whose endpoint nobody can check against anything is a
    claim about what happened rather than a record of it.
    """
    ledger = Ledger()
    # `released` sits beside `oob` rather than inside it: reaping happens before
    # anything is bound, so a run that refuses afterwards still has to report
    # the names it took away from this machine.
    facts: dict[str, object] = {"program_id": None, "oob": None, "released": []}

    policy, slug = callback.policy_for(ledger, configuration_path)
    if policy is None or slug is None:
        return report(UP, ledger, **facts)
    endpoint = _channel(ledger, policy, slug, channel, UP)
    if endpoint is None:
        return report(UP, ledger, **facts)
    if endpoint.provider != QUICK_PROVIDER:
        ledger.fail(
            "oob_channel",
            f"channel {channel} declares provider {endpoint.provider}, which "
            f"binds no name; {UP} starts a {QUICK_PROVIDER} tunnel",
            code=INVALID_CONFIGURATION,
            source="argument:--channel",
        )
        return report(UP, ledger, **facts)

    connection = migrate.open_connection(ledger, runtime)
    if connection is None:
        return report(UP, ledger, **facts)
    with connection:
        program_id = callback.open_program(ledger, connection, slug)
        if program_id is None:
            return report(UP, ledger, **facts)
        facts["program_id"] = program_id

        reaped = _reap(connection)
        facts["released"] = reaped
        for released in reaped:
            ledger.hold(
                "oob_binding",
                f"released {released} whose tunnel process is gone; the name it "
                "bound is not this machine's any more",
            )

        if not _listening(port):
            ledger.fail(
                "oob_publisher",
                f"nothing answers {HEALTH_PATH} on {LISTEN_HOST}:{port}; start "
                f"`rk {SERVE}` first, because a bound name in front of nothing "
                "is a name an agent will embed in a payload",
                code=INVALID_CONFIGURATION,
                source="argument:--port",
            )
            return report(UP, ledger, **facts)

        started = _tunnel(ledger, binary, port, timeout)
        if started is None:
            return report(UP, ledger, **facts)

        # No `set_actor` here: `bind_callback_channel` sets its own, and a
        # label written in front of it would be one the writer overwrites.
        with connection.transaction():
            sha256, _ = Store(Path(store)).put(started.output)
            evidence = {
                "sha256": sha256,
                "byte_size": len(started.output),
                "content_type": "text/plain; charset=utf-8",
            }
            try:
                answer = _decode(
                    str(
                        connection.execute(
                            BIND,
                            (
                                channel,
                                QUICK_PROVIDER,
                                started.host,
                                started.pid,
                                _encode(evidence),
                            ),
                        ).scalar()
                    )
                )
            except pg.DatabaseError as error:
                ledger.fail(
                    "oob_binding",
                    f"the binding was refused: {error}",
                    code=INVALID_CONFIGURATION,
                    source="database",
                )
                return report(UP, ledger, **facts)

    facts["oob"] = {
        "channel": channel,
        "binding_id": answer.get("binding_id"),
        "endpoint": answer.get("endpoint"),
        "provider": QUICK_PROVIDER,
        "tunnel_pid": started.pid,
        "evidence_sha256": sha256,
    }
    ledger.hold(
        "oob",
        f"channel {channel} is bound to {answer.get('endpoint')} by tunnel "
        f"{started.pid}; the name is in binding {answer.get('binding_id')} and "
        f"nowhere else, and `rk {STATUS}` is how anything reads it",
    )
    return report(UP, ledger, **facts)


def status(
    runtime: pg.Settings | None,
    configuration_path: Path,
    channel: str,
) -> Report:
    """What name this channel is answering at, and what hangs off it.

    The only supported way to learn the name. Nothing in a configuration file
    holds it, no agent composes it, and this reads it from the binding rather
    than from anything remembered: a name that was released this morning is
    absent here, which is the answer that stops it being embedded in a payload.
    """
    ledger = Ledger()
    facts: dict[str, object] = {"program_id": None, "oob": None}

    policy, slug = callback.policy_for(ledger, configuration_path)
    if policy is None or slug is None:
        return report(STATUS, ledger, **facts)
    if _channel(ledger, policy, slug, channel, STATUS) is None:
        return report(STATUS, ledger, **facts)

    connection = migrate.open_connection(ledger, runtime)
    if connection is None:
        return report(STATUS, ledger, **facts)
    with connection:
        program_id = callback.open_program(ledger, connection, slug)
        if program_id is None:
            return report(STATUS, ledger, **facts)
        facts["program_id"] = program_id
        answer = _decode(str(connection.execute(BINDING, (channel,)).scalar()))

    facts["oob"] = dict(answer, channel=channel)
    if answer.get("bound"):
        ledger.hold(
            "oob",
            f"channel {channel} answers at {answer.get('endpoint')} with "
            f"{answer.get('correlators', 0)} live correlator(s)"
            + (
                f", bound at {answer.get('bound_at')} by tunnel {answer.get('tunnel_pid')}"
                if answer.get("binding_id")
                else " as declared"
            ),
        )
    else:
        ledger.hold(
            "oob",
            f"channel {channel} has no live binding, so it has no name and "
            f"nothing may be minted on it; `rk {UP}` binds one",
        )
    return report(STATUS, ledger, **facts)


def down(
    runtime: pg.Settings | None,
    configuration_path: Path,
    channel: str,
) -> Report:
    """Release the name this channel is answering at, and say what it killed.

    Every correlator minted against the binding dies with it -- not by a sweep
    here, but because it names a released binding and every read filters on
    that. So the count in this report is not housekeeping that was done, it is
    how many canaries an operator should stop expecting to hear from.
    """
    ledger = Ledger()
    facts: dict[str, object] = {"program_id": None, "oob": None}

    policy, slug = callback.policy_for(ledger, configuration_path)
    if policy is None or slug is None:
        return report(DOWN, ledger, **facts)
    if _channel(ledger, policy, slug, channel, DOWN) is None:
        return report(DOWN, ledger, **facts)

    connection = migrate.open_connection(ledger, runtime)
    if connection is None:
        return report(DOWN, ledger, **facts)
    with connection:
        program_id = callback.open_program(ledger, connection, slug)
        if program_id is None:
            return report(DOWN, ledger, **facts)
        facts["program_id"] = program_id

        binding = _decode(str(connection.execute(BINDING, (channel,)).scalar()))
        identifier = binding.get("binding_id")
        if identifier is None:
            # Either nothing is bound or the channel is static, which is a name
            # the operator declared and this verb has no business releasing.
            facts["oob"] = {"channel": channel, "released": False, "correlators": 0}
            ledger.hold(
                "oob",
                f"channel {channel} holds no binding to release; nothing was changed",
            )
            return report(DOWN, ledger, **facts)

        with connection.transaction():
            try:
                answer = _decode(str(connection.execute(RELEASE, (identifier,)).scalar()))
            except pg.DatabaseError as error:
                ledger.fail(
                    "oob_binding",
                    f"the binding was not released: {error}",
                    code=INVALID_CONFIGURATION,
                    source="database",
                )
                return report(DOWN, ledger, **facts)

    facts["oob"] = dict(answer, channel=channel, binding_id=identifier)
    ledger.hold(
        "oob",
        f"{answer.get('endpoint')} is no longer this Program's: "
        f"{answer.get('correlators', 0)} correlator(s) minted against it are "
        "unreachable, and the tunnel process is the operator's to stop",
    )
    return report(DOWN, ledger, **facts)


@dataclass(frozen=True)
class Started:
    """A tunnel process, the name it was given, and the bytes that said so."""

    host: str
    pid: int
    output: bytes
    log: Path


def _tunnel(ledger: Ledger, binary: str, port: int, timeout: float) -> Started | None:
    """Start the tunnel and wait for it to say what name it was given.

    The output goes to a file rather than a pipe nobody drains: this process
    returns while the tunnel keeps running, and a pipe with no reader is a
    tunnel that stops the first time it fills one. The file is what the binding
    cites, and it stays on disk for the tunnel to keep writing to.
    """
    handle, name = tempfile.mkstemp(prefix="rk-oob-", suffix=".log")
    log = Path(name)
    url = f"http://{LISTEN_HOST}:{port}"
    try:
        process = subprocess.Popen(
            [binary, "tunnel", "--url", url],
            stdin=subprocess.DEVNULL,
            stdout=handle,
            stderr=subprocess.STDOUT,
            # Its own session, so the tunnel outlives the shell that started it
            # and a Ctrl-C in the publisher's terminal is not a released name.
            start_new_session=True,
        )
    except OSError as error:
        ledger.fail(
            "oob_tunnel",
            f"{binary} did not start: {error}",
            code=INVALID_CONFIGURATION,
            source="argument:--tunnel",
        )
        return None
    finally:
        os.close(handle)

    deadline = time.monotonic() + timeout
    while True:
        output = log.read_bytes()
        found = QUICK_TUNNEL.search(output.decode("utf-8", "replace"))
        if found is not None:
            return Started(host=found.group(1), pid=process.pid, output=output, log=log)
        if process.poll() is not None:
            ledger.fail(
                "oob_tunnel",
                f"{binary} exited {process.returncode} without naming a tunnel; "
                f"its output is in {log}",
                code=INVALID_CONFIGURATION,
                source="argument:--tunnel",
            )
            return None
        if time.monotonic() >= deadline:
            # A tunnel nobody read a name out of is a process with no purpose
            # and no record, so it does not get to outlive the attempt.
            process.terminate()
            try:
                process.wait(timeout=TUNNEL_TIMEOUT)
            except subprocess.TimeoutExpired:
                process.kill()
            ledger.fail(
                "oob_tunnel",
                f"{binary} named no tunnel within {timeout:g} second(s); "
                f"its output is in {log}",
                code=INVALID_CONFIGURATION,
                source="argument:--tunnel",
            )
            return None
        time.sleep(TUNNEL_POLL)


def _reap(connection: pg.Connection) -> list[dict]:
    """Release every binding whose tunnel process is gone, before anything else.

    An overnight pause and a restart in the morning is the ordinary path, and
    the name Cloudflare handed out yesterday belongs to somebody else today. The
    process is the whole test: a quick tunnel lives exactly as long as the
    process that asked for it, so a pid that is not there is a name that is not
    ours.
    """
    released: list[dict] = []
    for row in connection.execute(LIVE_BINDINGS).rows:
        identifier, name, endpoint, pid = str(row[0]), str(row[1]), str(row[2]), row[3]
        if pid is not None and _running(int(pid)):
            continue
        with connection.transaction():
            answer = _decode(str(connection.execute(RELEASE, (identifier,)).scalar()))
        released.append(
            {
                "binding_id": identifier,
                "channel": name,
                "endpoint": endpoint,
                "tunnel_pid": pid,
                "correlators": answer.get("correlators", 0),
            }
        )
    return released


def _running(pid: int) -> bool:
    """Whether a process with this id exists, asked without touching it.

    Signal 0 is the question rather than an instruction. `EPERM` is a yes: a
    process this user may not signal is still a process, and reading it as gone
    would release a binding whose tunnel is up.
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _listening(port: int) -> bool:
    """Whether our own publisher answers on this port.

    The `Host` is the loopback address, which is the one thing a request through
    a quick tunnel cannot carry -- the edge routes by hostname and sends the
    tunnel's. So a 200 here is this machine answering, not something the tunnel
    is pointed at, and `rk oob up` binds a name to a publisher rather than to
    whatever else happened to be on the port.
    """
    address = f"{LISTEN_HOST}:{port}"
    try:
        session = http.client.HTTPConnection(LISTEN_HOST, port, timeout=PROBE_TIMEOUT)
        try:
            session.request("GET", HEALTH_PATH, headers={"Host": address})
            answer = session.getresponse()
            return answer.status == 200 and answer.read() == b"ok"
        finally:
            session.close()
    except (OSError, http.client.HTTPException):
        return False


def _channel(
    ledger: Ledger, policy: scope.Policy, slug: str, channel: str, command: str
) -> scope.Channel | None:
    """The declared channel this command names, or the refusal saying it is not."""
    endpoint = policy.channel(channel)
    if endpoint is None:
        declared = sorted(entry.name for entry in policy.channels)
        ledger.fail(
            "oob_channel",
            f"{slug} declares no callback channel named {channel}; it declares "
            + (", ".join(declared) if declared else "none"),
            code=INVALID_CONFIGURATION,
            source="argument:--channel",
        )
        return None
    return endpoint


def _root_from_environment() -> Path | None:
    """The publish root the environment names, or nothing."""
    raw = os.environ.get(ROOT_VARIABLE, "").strip()
    return Path(raw) if raw else None


def _to_stderr(line: str) -> None:
    """Where a publisher's running commentary goes when nobody redirected it.

    Not stdout: the report is machine-read from there, and a request log in the
    middle of it is output nobody asked for.
    """
    print(line, file=sys.stderr, flush=True)


def _encode(value: dict) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _decode(value: str) -> dict:
    decoded = json.loads(value)
    return decoded if isinstance(decoded, dict) else {}
