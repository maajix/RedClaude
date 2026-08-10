"""`rk proxy`: the one peer a Tool run may reach, and the only writer of an allowed Receipt.

Section 7 of the spec puts the whole egress guarantee on one sentence: an agent
container has exactly one reachable peer, and it is this process. Everything
here follows from taking that literally.

The capability is *taken*, never read. `Proxy-Authorization` and
`X-RedKraken-Program` are removed from the header container before any other
line of this module looks at the request, so the code that builds what goes to
the target cannot include them by omission -- there is nothing left to omit. The
same removal is why the capability appears in no Receipt, no Artifact and no
log: after four lines it exists only as a local variable and a parameter to one
database call.

The decision is the database's. This module canonicalises the request that
arrived -- host, port, both path spellings -- and hands those to
`authorize_egress_request`, which resolves the capability to a Program, an Agent
run and a Tool run, checks the Program is still open, and re-decides scope
against the current compiled policy. The proxy does not get to have an opinion:
it either received an authorization or it did not, and without one no socket is
opened towards the target. That ordering is the ticket's fifth criterion and it
is observable -- a refused request leaves the target's request count unchanged.

Subresources and redirects share one capability on purpose (§7 again), and each
is still decided on its own: the capability says which Tool run this is, and the
scope check is redone per request against the URL that actually arrived.

What comes back is written once, by `record_proxy_exchange`, which is the only
path to an allowed Receipt that exists -- `rk2_proxy` holds no INSERT on
`receipts` and a database trigger refuses an allowed agent Receipt with no live
capability behind it even when the owner attempts it. A refused write is a 502
to the caller, never a 200: an exchange the record does not carry is an exchange
that did not happen as far as the harness is concerned, and reporting it as
successful would be the one lie the whole design exists to prevent.

Three things are deliberately not here. HTTPS through CONNECT is ticket 10, and
is refused rather than tunnelled, because a tunnel this process cannot see
inside is egress with no Receipt. Address policy and pinning are ticket 11: the
`connector` seam below is where they attach, and today it resolves a name the
ordinary way. Credential injection is ticket 12, which is also when the wire
view of an exchange first differs from the agent's -- until then there is one
view, it is the agent's, and claiming two would be recording a difference that
does not exist.
"""

from __future__ import annotations

import http.client
import ipaddress
import json
import re
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import Message
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import SplitResult, urlsplit

from redkraken import config, migrate, pg, program, scope
from redkraken.outcome import (
    INTEGRITY_FAILED,
    INVALID_CONFIGURATION,
    Ledger,
    Report,
    report,
)
from redkraken.store import Store, digest


__all__ = [
    "AUTHORIZATION",
    "COMMAND",
    "DECISION",
    "PROGRAM",
    "PROXY_URL",
    "RECEIPT",
    "REQUEST",
    "SERVE",
    "Authorization",
    "Fence",
    "Refused",
    "Server",
    "capability_of",
    "describes_this_hop",
    "endpoint",
    "forwardable",
    "listen",
    "origin_form",
    "query_sha256",
    "send",
    "serve",
    "take_control",
]


COMMAND = "proxy"
SERVE = f"{COMMAND} serve"
REQUEST = f"{COMMAND} request"

#: Where the door listens, for the runtime that has to reach it. Deliberately not
#: a connection string: the fence's own login is `RK_PROXY_DATABASE_URL` and it is
#: `rk2_proxy`, so no single exported variable runs both sides of the fence.
PROXY_URL = "RK_PROXY_URL"

#: What the runtime sends and the proxy takes. `Proxy-Authorization` is the
#: header HTTP already reserves for the hop rather than the origin: every client
#: library strips it on forward, and this one removes it before it can forget to.
AUTHORIZATION = "Proxy-Authorization"
PROGRAM = "X-RedKraken-Program"

#: What the proxy answers with. The Receipt label is the agent-citable name for
#: what just happened; the decision header is how a refusal says it was this
#: fence and not the target that said no.
RECEIPT = "X-RedKraken-Receipt"
DECISION = "X-RedKraken-Decision"

#: Everything the decision header is allowed to say. Tokens rather than the
#: refusal's own prose: a caller branches on this value, and a reason reworded in
#: a later ticket would silently change what it branched to. The prose goes to
#: `X-RedKraken-Detail`, which nothing is meant to parse.
REFUSED = "capability-refused"
AMBIGUOUS = "control-headers-refused"
NO_PROGRAM = "no-program"
RECEIPT_REFUSED = "receipt-refused"
TUNNEL = "tunnel-refused"

#: What an ambiguous take says, in one place because two paths report it and a
#: caller comparing the two would otherwise be reading a difference that means
#: nothing.
TWO_HEADERS = "the request carries two of one control header"

#: The minted shape, pinned: `authorize_tool_run` emits 32 random bytes as
#: lowercase hex and nothing else is a capability. Anchored on both ends, so a
#: value with anything after it is not "a capability with trailing junk" -- it is
#: not a capability.
CAPABILITY = re.compile(r"^RedKraken ([0-9a-f]{64})$")

#: Headers that describe this hop and must not describe the next one. `Host` is
#: in the list because the proxy sends the host it decided against rather than
#: the one the caller wrote: those are the same name or the decision was about a
#: different server than the request reached. The two length headers are here
#: because the body is re-sent with a length this process measured.
HOP_BY_HOP = frozenset(
    {
        "connection",
        "content-length",
        "host",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "proxy-connection",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)

#: Every internal control header, by prefix rather than by name, so a header
#: added later is excluded by having been named at all.
INTERNAL = "x-redkraken-"

#: What an artifact of one whole exchange is. Not the body's type: the bytes
#: stored are a complete HTTP message, headers included, and calling them
#: `application/json` because the body was would misdescribe every one of them.
TRANSCRIPT = "message/http"

#: How long the proxy waits on a target before giving up. A refusal with a
#: Receipt is a better outcome than a socket held open by a target that never
#: answers, because the second one holds a capability alive while it waits.
TIMEOUT = 30.0

#: The largest response this fence will read into memory to hash and store. A
#: Receipt names the bytes of the exchange, so the bytes have to be held; a
#: target that answers with more than this is refused rather than streamed past
#: unrecorded.
CEILING = 32 * 1024 * 1024

#: The tool a request through this proxy is a run of. Pinned here because the
#: gate's risk rules are written against this exact name.
TOOL = "mcp__rk2__net_request"


class Refused(Exception):
    """One request that will not be forwarded, and the reason a Receipt cites.

    The status is the proxy's own, never the target's: 407 says this fence
    refused a capability, and a caller that reads one knows the request did not
    leave the machine. 400 is reserved for a message that was not a proxy
    request at all, which is a different fact and is worth being able to tell
    apart from a refused one.
    """

    def __init__(
        self,
        reason: str,
        detail: str = "",
        *,
        status: int = 407,
        target_status: int | None = None,
    ) -> None:
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail or reason
        self.status = status
        #: What the target answered, on the refusals that happen after it did.
        #: `status` is this fence's answer and is never the target's; the two
        #: live on one object because a Receipt records both facts about the
        #: same refusal, and a refusal before contact has only the first.
        self.target_status = target_status


@dataclass(frozen=True)
class Control:
    """What the runtime told the proxy, once it is no longer in the request."""

    capability: str | None
    program: str | None
    #: Whether one of the two names carried two values. Reported rather than
    #: raised: see `take_control`.
    ambiguous: bool = False


@dataclass(frozen=True)
class Authorization:
    """One decision to contact one target, as the database resolved it.

    Not a **Standing grant**: that word is the glossary's for an operator's
    standing predicate over requests, and this is the answer to one request,
    resolved from one capability and discarded with it.
    """

    program_id: str
    tool_run_id: str
    scope_version: int
    scope_class: str


# ---------------------------------------------------------------------------
# The bytes: what is taken, what is forwarded, what is recorded
# ---------------------------------------------------------------------------


def capability_of(value: str | None) -> str | None:
    """The capability in one header value, or nothing at all.

    Nothing at all covers absent, mis-scheme'd, wrong length and wrong alphabet
    alike, because the proxy's next move is the same for all of them: refuse
    before egress and record the attempt. Distinguishing them in the answer would
    tell a caller which half of a guess was right.
    """
    if not value:
        return None
    found = CAPABILITY.match(value)
    return found.group(1) if found else None


def take_control(headers: Message) -> Control:
    """Remove the control headers and return what they said.

    Removal happens first and unconditionally, including on the paths that go on
    to refuse: a request rejected for carrying two capabilities must not be
    forwarded with either of them still attached, and the cheapest way to mean
    that is for the container the forwarder reads to no longer hold them.

    Two values under one name is refused rather than resolved. Taking the first
    would let a caller hide a second capability behind one the proxy accepts, and
    taking the last would do the same in the other direction. The duplicated name
    resolves to nothing at all here, so no later line can pick a side.

    Reported rather than raised, because the caller who duplicates a header is
    exactly the caller who most needs a row. A request carrying two
    `Proxy-Authorization` lines can still have named its Program unambiguously,
    and that is enough to file the attempt against; raising from here was how
    sending one header twice bought a refusal that nothing recorded.
    """
    offered = headers.get_all(AUTHORIZATION) or []
    claimed = headers.get_all(PROGRAM) or []
    del headers[AUTHORIZATION]
    del headers[PROGRAM]
    return Control(
        capability=capability_of(offered[0]) if len(offered) == 1 else None,
        program=(claimed[0].strip() or None) if len(claimed) == 1 else None,
        ambiguous=len(offered) > 1 or len(claimed) > 1,
    )


def describes_this_hop(name: str, named: frozenset[str] | set[str] = frozenset()) -> bool:
    """Whether one header is about this connection rather than the message on it.

    One predicate, because the request going out and the answer coming back are
    filtered by the same rule and a copy of it would be a rule that could drift
    on one side only -- which for the internal prefix would mean a control header
    reaching a target, and for hop-by-hop would mean a length this process did
    not measure.
    """
    lowered = name.lower()
    return lowered in HOP_BY_HOP or lowered in named or lowered.startswith(INTERNAL)


def forwardable(headers: Message) -> list[tuple[str, str]]:
    """The caller's headers, minus everything that describes this hop.

    `Connection` names its own additions to the hop-by-hop set, so they are read
    out of it rather than assumed to be the fixed list. Anything under the
    internal prefix goes whether or not `take_control` knew about it: a control
    header this version does not recognise is still not the target's business.
    """
    named = {
        item.strip().lower()
        for value in (headers.get_all("connection") or [])
        for item in value.split(",")
        if item.strip()
    }
    return [
        (name, value) for name, value in headers.items() if not describes_this_hop(name, named)
    ]


def origin_form(url: str) -> str:
    """The request line a target expects, from the absolute form a proxy gets.

    The fragment is dropped because it never belonged on the wire: it is the
    caller's own reference into the answer, and a proxy that forwarded one would
    be sending a byte no origin server was ever asked for.
    """
    parts = urlsplit(url)
    path = parts.path or "/"
    return f"{path}?{parts.query}" if parts.query else path


def query_sha256(url: str) -> str | None:
    """The digest of the query string, or nothing when there was no query.

    A digest rather than the string, because a query carries identifiers,
    tokens and occasionally a credential somebody pasted, and §6 lets digests
    into a record that it does not let values into. Absence stays absence: a
    hash of the empty string would make "no query" and "an empty query" the same
    fact and neither of them distinguishable from a query nobody recorded.
    """
    query = urlsplit(url).query
    return digest(query.encode("utf-8")) if query else None


def transcript(start: str, headers: list[tuple[str, str]], body: bytes) -> bytes:
    """One HTTP message as bytes, in the order it went or came.

    Reconstructed from what this process sent or read rather than captured off
    the socket, which is what makes it an honest subject for a hash: the bytes
    named by the Receipt are the bytes this fence handled, headers included, and
    a control header cannot appear in them because it is not in the list.
    """
    head = start + "\r\n" + "".join(f"{name}: {value}\r\n" for name, value in headers) + "\r\n"
    return head.encode("latin-1", "replace") + body


def endpoint(url: str) -> tuple[str, int]:
    """The local proxy an operator named, refused if it is not local.

    The capability is plaintext for exactly one hop, and this is the assertion
    that the hop is on this machine. A proxy on another host would be a
    capability crossing a network in the clear, which is the one thing its
    five-minute lifetime is not a defence against.

    The refusal it raises never reaches a caller as a status: it is the only
    `Refused` on this side of the fence, and `send` turns it into one violation
    in a report. Only the detail survives that, which is why the detail says the
    whole thing.
    """
    parts = urlsplit(url)
    if parts.scheme != "http":
        raise Refused(
            "endpoint refused",
            f"{url} is not an http:// endpoint; the local proxy speaks plain HTTP",
        )
    host = parts.hostname or ""
    try:
        port = parts.port or 80
    except ValueError as error:
        raise Refused("endpoint refused", f"the proxy port cannot be read: {error}") from error
    if not _loopback(host):
        raise Refused(
            "endpoint refused",
            f"{host} is not a loopback address; the capability is sent to this machine only",
        )
    return host, port


def _loopback(host: str) -> bool:
    """Whether a name or address is this machine and nothing else."""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# The database half
# ---------------------------------------------------------------------------


#: Every canonical value the decision is made from, and none it could re-derive.
#: 039 read the host and port back out of the URL with a regular expression while
#: this process parsed the same URL with `urlsplit`; two parsers over one string
#: is a differential waiting to be found, and the one that matters is the one
#: whose answer the socket is opened against. So the proxy sends what it
#: canonicalised and the function refuses anything that is not canonical.
AUTHORIZE = (
    "SELECT program_id::text, tool_run_id::text, scope_version, scope_class"
    "  FROM authorize_egress_request($1, $2, $3, $4, $5::integer, $6, $7, $8)"
)

#: One call, one transaction: the artifacts of the exchange and the Receipt that
#: names them are written together or not at all. A Receipt naming bytes no row
#: registered is a dangling reference, and rows for bytes no Receipt names are
#: an artifact nobody can reach.
RECORD = "SELECT record_proxy_exchange($1, $2::jsonb, $3::jsonb)"

BLOCKED = "SELECT write_blocked_receipt($1::uuid, $2::jsonb, $3)::text"

BIND = "SELECT set_config('rk2.program_id', $1, false)"


def _object(answer: object) -> dict:
    """One `jsonb` answer as a mapping, whichever shape the driver returned it in.

    Both sides of this module read a function that answers with an object, and a
    second spelling of the same two-branch decode is a second place for the two
    to disagree about what an answer with no rows looks like.
    """
    return json.loads(answer) if isinstance(answer, str) else dict(answer)


class Fence:
    """The decision and the record, on the connection that owns neither.

    One connection, used from the handler threads under a lock. The alternative
    -- a connection per request -- would put the number of live database sessions
    under the control of whatever is making requests, which for a process whose
    job is to survive a hostile client is the wrong direction to fail in.
    """

    def __init__(self, connection: pg.Connection):
        self.connection = connection
        self._lock = threading.Lock()

    def close(self) -> None:
        self.connection.close()

    def _bind(self, program_id: str) -> None:
        """Tell the session which Program this request claims to be.

        Claimed, not proven: the header is the caller's. It decides nothing on
        its own -- `resolve_egress_capability` requires the capability's own Tool
        run to belong to the bound Program, so a capability offered under
        somebody else's Program resolves to no row at all.
        """
        self.connection.execute(BIND, (program_id,))

    def authorize(
        self, program_id: str, capability: str, method: str, request: scope.Request
    ) -> Authorization:
        with self._lock:
            self._bind(program_id)
            try:
                rows = self.connection.execute(
                    AUTHORIZE,
                    (
                        capability,
                        method,
                        request.protocol,
                        request.host,
                        request.port,
                        request.path_raw,
                        request.path_norm,
                        "",
                    ),
                ).rows
            except pg.DatabaseError as error:
                raise Refused("capability refused", str(error)) from error
        if not rows:
            raise Refused("capability refused", "no capability resolved")
        found, tool_run, version, klass = rows[0]
        return Authorization(
            program_id=str(found),
            tool_run_id=str(tool_run),
            scope_version=int(version),
            scope_class=str(klass),
        )

    def allowed_receipt(
        self, program_id: str, capability: str, receipt: dict, artifacts: list[dict]
    ) -> dict:
        """Record one exchange, under the Program this request was decided for.

        The bind is repeated here rather than inherited from `authorize`. One
        connection serves every handler thread, `set_config` is session-wide, and
        the target exchange happens outside the lock -- so between the decision
        and this write another thread's request has had every opportunity to
        rebind the session to its own Program. Binding again is what stops a
        served exchange from failing to record because somebody else was faster.
        """
        with self._lock:
            self._bind(program_id)
            try:
                answer = self.connection.execute(
                    RECORD,
                    (capability, json.dumps(receipt), json.dumps(artifacts)),
                ).scalar()
            except pg.DatabaseError as error:
                raise Refused("receipt write refused", str(error)) from error
        return _object(answer)

    def blocked_receipt(self, program_id: str, capability: str | None, receipt: dict) -> str:
        with self._lock:
            self._bind(program_id)
            answer = self.connection.execute(
                BLOCKED, (program_id, json.dumps(receipt), capability)
            ).scalar()
        return str(answer)


# ---------------------------------------------------------------------------
# The server
# ---------------------------------------------------------------------------


Connector = Callable[[str, int, float], http.client.HTTPConnection]


def connect(host: str, port: int, timeout: float) -> http.client.HTTPConnection:
    """Open the connection to the target this request was authorized for.

    The seam ticket 11 attaches to. Today the name is resolved the ordinary way
    and whatever it resolves to is dialled; pinning the address that was decided
    against, and refusing one that moved between the decision and the socket, is
    that ticket's whole subject and is not simulated here.
    """
    return http.client.HTTPConnection(host, port, timeout=timeout)


class Server(ThreadingHTTPServer):
    """The listening socket, and the three things a request is answered from."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        address: tuple[str, int],
        handler: type[BaseHTTPRequestHandler],
        *,
        fence: Fence | None,
        store: Store,
        connector: Connector,
        timeout: float = TIMEOUT,
    ):
        super().__init__(address, handler)
        self.fence = fence
        self.store = store
        self.connector = connector
        self.target_timeout = timeout


class Handler(BaseHTTPRequestHandler):
    """One request: take the control headers, ask, forward, record, answer."""

    protocol_version = "HTTP/1.1"
    server_version = "redkraken"
    sys_version = ""

    def _serve(self) -> None:
        arrival = datetime.now(timezone.utc)
        control = take_control(self.headers)
        program_id = _identifier(control.program)
        if program_id is None:
            # Either nothing named a Program or two headers did, and the one
            # that would have said which is part of what was ambiguous. There is
            # nowhere to file the record either way; guessing a Program would put
            # a stranger's row in somebody's audit.
            return self._answer(407, AMBIGUOUS if control.ambiguous else NO_PROGRAM, body=b"")

        if control.ambiguous:
            # The Program is unambiguous, so the attempt does have somewhere to
            # go -- and it goes there. A refusal that filed nothing would make
            # duplicating one's own capability header the cheapest way through
            # this fence there is: refused, but unrecorded.
            return self._refuse(
                program_id,
                None,
                Refused("ambiguous control headers", TWO_HEADERS),
                arrival,
                url=self.path,
                decision=AMBIGUOUS,
            )

        try:
            request = self._request()
            if control.capability is None:
                raise Refused("capability refused", "no capability was offered")
            authorization = self.server.fence.authorize(
                program_id, control.capability, self.command, request
            )
            body = self._body()
        except Refused as refusal:
            return self._refuse(program_id, control.capability, refusal, arrival, url=self.path)

        self._forward(authorization, control.capability, request, body, arrival)

    do_GET = _serve
    do_HEAD = _serve
    do_POST = _serve
    do_PUT = _serve
    do_PATCH = _serve
    do_DELETE = _serve
    do_OPTIONS = _serve

    def do_CONNECT(self) -> None:
        """Refuse the tunnel. Ticket 10 is where HTTPS gets one.

        The take still happens, and an ambiguous one is still the refusal
        reported: a caller has to be able to tell which of the two things was
        wrong with their request.

        Nothing is filed on this path, ambiguous or not, and that is not the hole
        `_serve` closes. There a record was suppressible by duplicating a header;
        here no tunnel produces a record at all, because no tunnel is opened --
        the row this ticket could write about a CONNECT would be a Receipt about
        an exchange that never happened.
        """
        control = take_control(self.headers)
        if control.ambiguous:
            return self._answer(407, AMBIGUOUS, detail=TWO_HEADERS, body=b"")
        self._answer(405, TUNNEL, body=b"")

    def _request(self) -> scope.Request:
        """The request line, canonicalised, or a refusal that never leaves."""
        if not self.path.lower().startswith("http://"):
            # Origin form means "you are the origin server". This fence has no
            # resource to serve, and answering one would be an unauthenticated
            # surface on the process holding every capability in flight.
            # `https://` in absolute form is ticket 10's, through CONNECT.
            raise Refused(
                "not a proxy request",
                f"{self.requestline} is not an absolute form URL",
                status=400,
            )
        try:
            return scope.canonical_request(self.path)
        except scope.PolicyError as error:
            raise Refused("malformed request", error.detail) from error

    def _body(self) -> bytes:
        """What the caller sent, bounded, or a refusal.

        A chunked request body is refused rather than re-framed: the Receipt
        names a hash of exactly what was forwarded, and a proxy that re-chunks
        is recording bytes that differ from the ones it read.
        """
        if (self.headers.get("Transfer-Encoding") or "").strip():
            raise Refused("unsupported framing", "a chunked request body is not forwarded")
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError as error:
            raise Refused("unsupported framing", "the request length cannot be read") from error
        if length < 0 or length > CEILING:
            raise Refused("unsupported framing", f"a request body over {CEILING} bytes")
        return self.rfile.read(length) if length else b""

    def _exchange(
        self,
        request: scope.Request,
        target: str,
        headers: list[tuple[str, str]],
        body: bytes,
    ) -> tuple[int, str, list[tuple[str, str]], bytes]:
        """Contact the authorized target and read what it answered, or refuse.

        Every refusal from here is one that happened after the socket was opened,
        which is why they are raised together: the caller of this method knows the
        request left the machine and records that on all of them.
        """
        try:
            connection = self.server.connector(
                request.host, request.port, self.server.target_timeout
            )
            try:
                # Header by header, in the order the transcript records, rather
                # than through `request(headers=...)`: that takes a mapping, so a
                # caller who sent two `Cookie` lines would have one of them
                # dropped on the wire while the Receipt named both. `skip_host`
                # and `skip_accept_encoding` are set because this list already
                # carries them, and the automatic `Content-Length: 0` that
                # `request()` adds to a body-less POST is a byte the Receipt
                # would not have known about either.
                connection.putrequest(
                    self.command, target, skip_host=True, skip_accept_encoding=True
                )
                for name, value in headers:
                    connection.putheader(name, value)
                connection.endheaders(body or None)
                answer = connection.getresponse()
                returned = answer.read(CEILING + 1)
                status = answer.status
                back = list(answer.getheaders())
                reason = answer.reason
            finally:
                connection.close()
        except (OSError, http.client.HTTPException) as error:
            raise Refused("target unreachable", str(error)) from error
        if len(returned) > CEILING:
            raise Refused(
                "response too large",
                f"the target answered with over {CEILING} bytes",
                target_status=status,
            )
        return status, reason, back, returned

    def _forward(
        self,
        authorization: Authorization,
        capability: str,
        request: scope.Request,
        body: bytes,
        arrival: datetime,
    ) -> None:
        """Send the authorized request, record the exchange, answer the caller."""
        authority = _authority(request.host, request.port, request.protocol)
        headers = [("Host", authority), *forwardable(self.headers)]
        if body:
            headers.append(("Content-Length", str(len(body))))
        if not any(name.lower() == "accept-encoding" for name, _ in headers):
            # `http.client` adds this one when the caller does not, and a
            # transcript that omitted it would be a hash of bytes that differ
            # from the ones the socket carried.
            headers.append(("Accept-Encoding", "identity"))
        target = origin_form(self.path)
        line = f"{self.command} {target} HTTP/1.1"

        egress = datetime.now(timezone.utc)
        try:
            status, reason, back, returned = self._exchange(request, target, headers, body)
        except Refused as refusal:
            return self._refuse(
                authorization.program_id,
                capability,
                refusal,
                arrival,
                url=self.path,
                authorization=authorization,
                egress=egress,
            )

        sent = transcript(line, headers, body)
        received = transcript(f"HTTP/1.1 {status} {reason}", back, returned)
        store = self.server.store
        request_sha, request_new = store.put(sent)
        response_sha, response_new = store.put(received)

        receipt = {
            # The version this request was decided against, named in the words of
            # the Receipt. The row's own `scope_version` is derived by the writer
            # from the Program's current one, so a policy recompiled between the
            # decision and the write leaves the two visibly disagreeing rather
            # than silently relabelling what was decided.
            "reason": f"allowed as {authorization.scope_class}"
            f" under scope version {authorization.scope_version}",
            "method": self.command,
            "scheme": request.protocol,
            "host": request.host,
            "port": request.port,
            "path": request.path_raw,
            "query_sha256": query_sha256(self.path),
            "status_code": status,
            "ts_arrival": arrival.isoformat(),
            "ts_egress": egress.isoformat(),
            "waited_ms": int((datetime.now(timezone.utc) - egress).total_seconds() * 1000),
            "request_agent_sha": request_sha,
            "request_wire_sha": None,
            "response_agent_sha": response_sha,
            "response_wire_sha": None,
            "scope_class": authorization.scope_class,
            "intercepted": True,
            "notes": None,
        }
        artifacts = [
            {"sha256": request_sha, "byte_size": len(sent), "content_type": TRANSCRIPT},
            {"sha256": response_sha, "byte_size": len(received), "content_type": TRANSCRIPT},
        ]
        try:
            written = self.server.fence.allowed_receipt(
                authorization.program_id, capability, receipt, artifacts
            )
        except Refused as refusal:
            # The bytes are spent: the target has answered and cannot be asked to
            # forget. Two things follow from that, and only one of them was here
            # before. The caller must not read a 200 for an exchange with no
            # Receipt behind it -- and the exchange must not vanish either, so the
            # record that can still be written is written: a blocked Receipt
            # naming the target, the status it answered with and the moment of
            # egress. It cannot name the transcripts, because registering them is
            # precisely what failed, and bytes no row can reach are discarded
            # rather than left in the store for nobody.
            if request_new:
                store.discard(request_sha)
            if response_new:
                store.discard(response_sha)
            return self._refuse(
                authorization.program_id,
                capability,
                Refused(
                    refusal.reason,
                    refusal.detail,
                    status=502,
                    target_status=status,
                ),
                arrival,
                url=self.path,
                authorization=authorization,
                egress=egress,
                decision=RECEIPT_REFUSED,
            )

        label = str(written.get("label") or written.get("receipt_id") or "")
        self._answer(status, None, body=returned, headers=back, receipt=label, reason=reason)

    def _refuse(
        self,
        program_id: str,
        capability: str | None,
        refusal: Refused,
        arrival: datetime,
        *,
        url: str,
        authorization: Authorization | None = None,
        egress: datetime | None = None,
        decision: str = REFUSED,
    ) -> None:
        """Record the attempt under the Program it named, and answer the refusal.

        The record is written before the answer, so a caller cannot learn the
        verdict earlier than the audit trail does. A record that itself fails to
        write does not become a served request: the answer is still a refusal.

        `egress` is what separates a refusal from a refusal-after-contact. Without
        it, "the target never answered" and "the target answered and the record
        would not write" are the same row shape, and an auditor reading the second
        one has no way to know that bytes left this machine.

        The one way that write legitimately fails is a Program header naming a
        Program that does not exist -- there is no row to file the attempt
        against, and inventing one would be worse than not filing it. That is why
        the failure is logged rather than raised, and why it is narrowed to the
        database's own errors: anything else is this module being wrong, and a
        bug that silently swallows itself is a fence nobody can see holes in.
        """
        try:
            parts = urlsplit(url)
        except ValueError:
            parts = urlsplit("")
        receipt = {
            "decision": "blocked",
            "reason": refusal.reason,
            "method": self.command,
            "scheme": (parts.scheme or None),
            "host": _hostname(parts),
            "port": _port(parts),
            "path": (parts.path or None),
            "query_sha256": query_sha256(url) if parts.query else None,
            "ts_arrival": arrival.isoformat(),
            "scope_class": authorization.scope_class if authorization else "denied",
            "intercepted": True,
        }
        if egress is not None:
            receipt["ts_egress"] = egress.isoformat()
            receipt["waited_ms"] = int(
                (datetime.now(timezone.utc) - egress).total_seconds() * 1000
            )
        if refusal.target_status is not None:
            receipt["status_code"] = refusal.target_status
        try:
            self.server.fence.blocked_receipt(program_id, capability, receipt)
        except (pg.DatabaseError, OSError, Refused) as error:
            self.log_error("no blocked receipt for %s: %s", program_id, error)
        self._answer(refusal.status, decision, detail=refusal.reason, body=b"")

    def _answer(
        self,
        status: int,
        decision: str | None,
        *,
        body: bytes,
        headers: list[tuple[str, str]] | None = None,
        receipt: str | None = None,
        detail: str | None = None,
        reason: str | None = None,
    ) -> None:
        """One answer to the caller, with the Receipt's name on it when there is one."""
        self.close_connection = True
        self.send_response(status, reason)
        for name, value in headers or []:
            if not describes_this_hop(name):
                self.send_header(name, value)
        if decision:
            self.send_header(DECISION, decision)
        if detail:
            self.send_header("X-RedKraken-Detail", detail)
        if receipt:
            self.send_header(RECEIPT, receipt)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        if self.command != "HEAD" and body:
            self.wfile.write(body)

    def log_message(self, format: str, *arguments: object) -> None:
        """Silence by default. The Receipt is the record; stderr is not one."""
        return

    def log_error(self, format: str, *arguments: object) -> None:
        """Not silenced, because it is the case the Receipt does not cover.

        Every served and every refused request has a row behind it. The one thing
        that leaves no row is a record that could not be written, so that is the
        one thing this process says out loud.
        """
        BaseHTTPRequestHandler.log_message(self, format, *arguments)


def _identifier(value: str | None) -> str | None:
    """The Program a request claims, or nothing when it claims nothing usable."""
    if not value:
        return None
    try:
        return str(uuid.UUID(value))
    except ValueError:
        return None


def _authority(host: str, port: int, protocol: str | None) -> str:
    """The `Host` header for a canonicalised target, default port omitted."""
    literal = f"[{host}]" if ":" in host else host
    if (protocol == "http" and port == 80) or (protocol == "https" and port == 443):
        return literal
    return f"{literal}:{port}"


def _hostname(parts: SplitResult) -> str | None:
    """The host of a URL that may not have one. `urlsplit` defers the parse."""
    try:
        return parts.hostname
    except ValueError:
        return None


def _port(parts: SplitResult) -> int | None:
    """The port of a URL that may not have a readable one."""
    try:
        return parts.port
    except ValueError:
        return None


def listen(
    address: tuple[str, int],
    *,
    fence: Fence | None,
    store: Store,
    connector: Connector = connect,
    timeout: float = TIMEOUT,
) -> Server:
    """Bind the listening socket without serving on it."""
    return Server(
        address, Handler, fence=fence, store=store, connector=connector, timeout=timeout
    )


def serve(settings: pg.Settings, *, root: Path, host: str = "127.0.0.1", port: int = 0) -> Report:
    """Run the fence until it is interrupted.

    Binds before it connects, so an operator who named a port something else
    holds learns that from the report rather than after a database session has
    been opened for a process that cannot listen.

    And it binds nowhere but this machine. `endpoint` refuses to send a
    capability to a proxy that is not local; a listener on a routable interface
    is the same hole from the other side, because what arrives at it is bearer
    material that anybody who can reach the port may spend.
    """
    ledger = Ledger()
    if not _loopback(host):
        ledger.fail(
            "listener",
            f"{host} is not a loopback interface, and a capability is bearer material",
            code=INVALID_CONFIGURATION,
            source="argument:--host",
        )
        return report(SERVE, ledger, endpoint=None)
    try:
        server = listen((host, port), fence=None, store=Store(Path(root)))
    except OSError as error:
        ledger.fail(
            "listener",
            f"cannot listen on {host}:{port}: {error}",
            code=INVALID_CONFIGURATION,
            source="argument:--port",
        )
        return report(SERVE, ledger, endpoint=None)
    ledger.hold("listener", f"listening on {host}:{server.server_address[1]}")

    connection = migrate.open_connection(ledger, settings)
    if connection is None:
        server.server_close()
        return report(SERVE, ledger, endpoint=None)
    server.fence = Fence(connection)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        ledger.hold("shutdown", "interrupted by the operator")
    finally:
        server.server_close()
        connection.close()
    return report(SERVE, ledger, endpoint=f"http://{host}:{server.server_address[1]}")


# ---------------------------------------------------------------------------
# The runtime half: one Tool run, one capability, one request
# ---------------------------------------------------------------------------


OPEN_RUN = (
    "INSERT INTO agent_runs (program_id, role, runs_as, model, effort, mission_packet)"
    " VALUES ($1::uuid, 'orchestrator', 'session', $2, 'low', $3::jsonb) RETURNING id::text"
)
OPEN_TOOL_RUN = (
    "INSERT INTO tool_runs (program_id, agent_run_id, tool, args, status, transport)"
    " VALUES ($1::uuid, $2::uuid, $3, $4::jsonb, 'running', 'runtime')"
    " RETURNING id::text, label"
)
AUTHORIZE_TOOL_RUN = "SELECT authorize_tool_run($1::uuid)"
#: Closing is what revokes: `guard_tool_run_authorization` clears the digest and
#: its expiry on any update that leaves `running`, so a Tool run cannot end and
#: keep a live capability. Stated here rather than written here, because a
#: runtime that cleared it itself would be a second place the rule lives.
#: `closed_by` is deliberately not set: 022 restricts it to the four hook events
#: and exempts a runtime-opened row from carrying one, because the runtime
#: closing its own row has no hook event to cite and inventing one would make the
#: column unusable as evidence.
CLOSE_TOOL_RUN = "UPDATE tool_runs SET status = $2, finished_at = now() WHERE id = $1::uuid"
CLOSE_RUN = "UPDATE agent_runs SET finished_at = now(), stop_reason = $2 WHERE id = $1::uuid"


def send(
    runtime: pg.Settings | None,
    configuration_path: Path,
    url: str,
    *,
    proxy_url: str,
    method: str = "GET",
    timeout: float = TIMEOUT,
) -> Report:
    """Open one Tool run, mint its capability and spend it on one request.

    The whole of ticket 09 from the caller's side. The capability is minted by
    the database, held in this process for the length of one request, sent to a
    proxy on this machine and to nothing else, and revoked by the Tool run
    closing -- which happens on the failure paths too, in the `finally` below,
    because a capability whose Tool run never closed stays live for its full five
    minutes.
    """
    ledger = Ledger()
    facts: dict = {
        "program_id": None,
        "program_slug": None,
        "tool_run": None,
        "receipt": None,
        "response": None,
    }

    try:
        host, port = endpoint(proxy_url)
    except Refused as refusal:
        ledger.fail(
            "proxy_endpoint",
            refusal.detail,
            code=INVALID_CONFIGURATION,
            source=f"environment:{PROXY_URL}",
        )
        return report(REQUEST, ledger, **facts)
    ledger.hold("proxy_endpoint", f"the capability is sent to {host}:{port} and nowhere else")

    try:
        request = scope.canonical_request(url)
    except scope.PolicyError as error:
        ledger.fail(
            "request", error.detail, code=INVALID_CONFIGURATION, source="argument:--url"
        )
        return report(REQUEST, ledger, **facts)
    if request.protocol != "http":
        ledger.fail(
            "request",
            f"{request.protocol} through this proxy is ticket 10; this one speaks plain HTTP",
            code=INVALID_CONFIGURATION,
            source="argument:--url",
        )
        return report(REQUEST, ledger, **facts)
    ledger.hold("request", f"{method} {request.host}:{request.port}{request.path_norm}")

    configuration, refusals = config.load(Path(configuration_path))
    if configuration is None:
        ledger.refuse("configuration", f"refused by {len(refusals)} violation(s)", refusals)
        return report(REQUEST, ledger, **facts)
    facts["program_slug"] = configuration.document["program"]["name"]
    ledger.hold("configuration", f"{facts['program_slug']}, schema {configuration.schema_version}")

    connection = migrate.open_connection(ledger, runtime)
    if connection is None:
        return report(REQUEST, ledger, **facts)
    with connection:
        program.assert_runtime_connection(ledger, connection)
        if ledger.violations:
            return report(REQUEST, ledger, **facts)
        program_id = program.resolve(ledger, connection, facts["program_slug"])
        if program_id is None:
            return report(REQUEST, ledger, **facts)
        facts["program_id"] = program_id
        _spend(ledger, facts, connection, program_id, url, method, (host, port), timeout)
    return report(REQUEST, ledger, **facts)


def _spend(
    ledger: Ledger,
    facts: dict,
    connection: pg.Connection,
    program_id: str,
    url: str,
    method: str,
    listener: tuple[str, int],
    timeout: float,
) -> None:
    """One Agent run, one Tool run, one capability, and its revocation.

    Three transactions rather than one, and the boundaries are the point. The
    Agent run and the Tool run commit before the capability is minted because the
    proxy resolves it on a session of its own and cannot see an uncommitted row;
    the close commits separately because it has to happen whatever the request
    did. `set_actor` is transaction-local by construction, so each of them
    declares its actor again -- a session-wide actor is exactly what 013 refuses.
    """
    connection.execute(BIND, (program_id,))
    with connection.transaction():
        connection.execute("SELECT set_actor('runtime', $1)", (f"rk {REQUEST}",))
        run = connection.execute(
            OPEN_RUN, (program_id, "operator", json.dumps({"command": REQUEST}))
        ).scalar()
        opened = connection.execute(
            OPEN_TOOL_RUN,
            (
                program_id,
                str(run),
                TOOL,
                json.dumps({"url": url, "method": method.upper(), "identity_slot": ""}),
            ),
        ).rows[0]
    tool_run_id, label = str(opened[0]), str(opened[1])
    facts["tool_run"] = {"id": tool_run_id, "label": label}

    outcome = "error"
    try:
        gate = _object(connection.execute(AUTHORIZE_TOOL_RUN, (tool_run_id,)).scalar())
        capability = gate.get("capability")
        if not capability:
            ledger.fail(
                "authorization",
                f"the gate answered {gate.get('decision')} for {label}: no capability was minted",
                code=INVALID_CONFIGURATION,
                source="database",
            )
            outcome = "denied"
            return
        ledger.hold(
            "authorization",
            f"{label} is {gate.get('risk_class')}/{gate.get('decision')} by {gate.get('rule')}",
        )
        status, body, receipt = _through(listener, url, method, capability, program_id, timeout)
        facts["response"] = {"status": status, "byte_size": len(body)}
        facts["receipt"] = receipt
        if receipt is None:
            ledger.fail(
                "receipt",
                f"the proxy answered {status} without naming a Receipt",
                code=INTEGRITY_FAILED,
                source="proxy",
            )
            return
        ledger.hold("receipt", f"the proxy wrote {receipt} for a {status} answer")
        outcome = "success"
    except (OSError, http.client.HTTPException) as error:
        ledger.fail(
            "proxy_endpoint",
            f"the proxy did not answer: {error}",
            code=INVALID_CONFIGURATION,
            source=f"environment:{PROXY_URL}",
        )
    finally:
        with connection.transaction():
            connection.execute("SELECT set_actor('runtime', $1)", (f"rk {REQUEST}",))
            connection.execute(CLOSE_TOOL_RUN, (tool_run_id, outcome))
            connection.execute(
                CLOSE_RUN, (str(run), "completed" if outcome == "success" else "error")
            )
        ledger.hold(
            "revocation", f"{label} closed as {outcome}; its capability no longer resolves"
        )


def _through(
    listener: tuple[str, int],
    url: str,
    method: str,
    capability: str,
    program_id: str,
    timeout: float,
) -> tuple[int, bytes, str | None]:
    """The request itself, in absolute form, with the capability on this hop."""
    host, port = listener
    client = http.client.HTTPConnection(host, port, timeout=timeout)
    try:
        client.request(
            method.upper(),
            url,
            headers={AUTHORIZATION: f"RedKraken {capability}", PROGRAM: program_id},
        )
        answer = client.getresponse()
        body = answer.read(CEILING + 1)
        return answer.status, body, answer.headers.get(RECEIPT)
    finally:
        client.close()
