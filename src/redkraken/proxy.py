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

HTTPS arrives through CONNECT and is *terminated here*, not relayed. A tunnel
this process cannot see inside is egress with no Receipt, so the door answers
the CONNECT itself, presents a certificate from the run's own authority
(`tls`), and reads the request inside as a request -- decided, forwarded and
recorded by the same three lines as a plain one. What that costs is written
down: the agent's view of the target's certificate is this door's, so a TLS
claim about the target is only true if this side made it, and `intercepted` is
on every Receipt to say so.

The address is decided before the socket, and then pinned. The name is resolved
once, *after* the capability has been spent and the scope check has passed --
never before, because a DNS query is itself egress, and one made on behalf of a
request that was going to be refused is a packet leaving this machine that no
Receipt names. Every address the name answers with has to be one the public
internet routes to, and the one that will be dialled is re-decided against the
Program's own policy as a literal address, so a name pointing at loopback, at a
private network, at link-local metadata or at a host the policy withdrew is
refused with no socket opened. What is then dialled is that address and not the
name: the name survives as the `Host` header and as the certificate the door
verifies, so a name that moves between the decision and the connection moves
nothing.

Target-issued authentication headers are wire-only.  They are removed before
the response is answered or made agent-visible; when that changes the message,
the exact target response is encrypted under the installation root key and the
Receipt names both hashes.  A door without that key refuses such a response
instead of leaking it.  Ticket 12 extends this same boundary with injected
Identity material and persisted session state.

Containment is not here either, and cannot be. Telling a child to use this door
(`tls.agent_environment`) is a request; a client that ignores it reaches the
network the same way it always would. What makes the door the only peer is a
network namespace with no other route, and that is a topology rather than a
module: it is ticket 11's first criterion, the child that has to live in it is
ticket 16's, and until both exist the honest statement is that this module
refuses everything it is asked and nothing it is not.
"""

from __future__ import annotations

import base64
import http.client
import hmac
import ipaddress
import json
import math
import re
import socket
import ssl
import threading
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from email.message import Message
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import BinaryIO, Protocol
from urllib.parse import SplitResult, quote, urljoin, urlsplit

from redkraken import build, config, identity, migrate, pg, program, scope, seal, tls, vault
from redkraken.outcome import (
    AWAITING_DECISION,
    INTEGRITY_FAILED,
    INVALID_CONFIGURATION,
    MISSING_DEPENDENCY,
    TARGET_UNREACHABLE,
    Ledger,
    Report,
    report,
)
from redkraken.store import Corrupt, Store, digest


__all__ = [
    "AUTHORITY_VARIABLE",
    "AUTHORIZATION",
    "CA_VARIABLE",
    "COMMAND",
    "DECISION",
    "DETAIL",
    "PROGRAM",
    "PROXY_URL",
    "RECEIPT",
    "REQUEST",
    "SERVE",
    "Answer",
    "Authorization",
    "Control",
    "FixtureAddress",
    "Fence",
    "IdentityBinding",
    "Refused",
    "Server",
    "capability_of",
    "connect",
    "describes_this_hop",
    "destination",
    "endpoint",
    "forwardable",
    "listen",
    "merge_control",
    "origin_form",
    "peer",
    "pinned_ips",
    "query_sha256",
    "redirected",
    "response_for_agent",
    "resolve",
    "send",
    "serve",
    "spend",
    "take_control",
    "unroutable",
    "with_required",
]


COMMAND = "proxy"
SERVE = f"{COMMAND} serve"
REQUEST = f"{COMMAND} request"

#: Where the door listens, for the runtime that has to reach it. Deliberately not
#: a connection string: the fence's own login is `RK_PROXY_DATABASE_URL` and it is
#: `rk2_proxy`, so no single exported variable runs both sides of the fence.
PROXY_URL = "RK_PROXY_URL"

#: The door's own connection, held as `rk2_proxy`: EXECUTE on two writers and no
#: receipt DML at all. Spelled out rather than folded into `RK_DATABASE_URL`
#: because a fence running as the runtime would be a fence with the privileges of
#: the thing it fences. Named here rather than beside the CLI's other roles
#: because both things that open it are here: the command, and the door `start`
#: puts in a container.
DATABASE_VARIABLE = "RK_PROXY_DATABASE_URL"

#: Where the door keeps the authority it signs intercepted connections with. A
#: directory rather than a file, because it holds a private key as well as the
#: certificate, and the two must not be handed out together.
AUTHORITY_VARIABLE = "RK_PROXY_AUTHORITY"

#: And the one file out of that directory a client is given: the certificate to
#: trust for the length of the run. Named separately because the side that
#: trusts it is not the side that holds the key, and an installation that
#: exported one variable for both would be exporting the key.
CA_VARIABLE = "RK_PROXY_CA_FILE"

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

#: And where the sentence goes. Named beside the other two because the runtime
#: puts it in its own report, so the string a refusal is explained by has to be
#: the string the door sent and not a second wording of it.
DETAIL = "X-RedKraken-Detail"

#: Ticket 136: which class the policy graded this request at, on every answer
#: this door gives. The door has always decided it -- it is on the Receipt, in
#: the reason line and in the transport branch -- and the decision died here: a
#: model reading its own answer could not tell a request served against the
#: target from one served against a fixture, and those are two different things
#: to conclude from the same bytes. Under the internal prefix like the other
#: three, so `describes_this_hop` keeps it off a target and out of the header
#: list the child reads as the target's own.
SCOPE = "X-RedKraken-Scope"

#: Everything the decision header is allowed to say. Tokens rather than the
#: refusal's own prose: a caller branches on this value, and a reason reworded in
#: a later ticket would silently change what it branched to. The prose goes to
#: `X-RedKraken-Detail`, which nothing is meant to parse.
REFUSED = "capability-refused"
AMBIGUOUS = "control-headers-refused"
NO_PROGRAM = "no-program"
RECEIPT_REFUSED = "receipt-refused"
TUNNEL = "tunnel-refused"

#: The refusals that are about how much rather than about whether. Its own token
#: because the caller's response to one is the opposite of its response to a
#: capability refusal: a throttled request is the same request, sent again later,
#: and a caller that read them as one token would either retry a refusal that
#: will never succeed or abandon one that would have.
BUDGETED = "budget-refused"

#: The refusals that are the target's state rather than this fence's verdict: a
#: name that answered with nothing, a socket that would not open, a TLS layer
#: that would not come up. Its own token because the capability was valid, was
#: spent and would be accepted again: a caller reading `capability-refused` for
#: one of these mints a fresh capability and is told the same thing, while the
#: fact worth acting on -- this target did not answer -- is the one it did not
#: learn. Ticket 11 already separates them in the Receipt's `reason`; this is
#: that same distinction on the wire.
UNREACHABLE = "target-unreachable"

#: The reasons that token stands for. Read from the reason the Receipt was filed
#: under rather than passed at each refusal site, because the code that dials a
#: target is not the code that knows about decision tokens, and a later path that
#: forgot to pass it would file the target's state as a refused capability again.
TARGET_FAULT = frozenset({"target unresolved", "target unreachable"})

#: The door lost the session it decides with. Its own token because it is the
#: one answer here that no Receipt stands behind: `pg.ConnectionError_` is a
#: sibling of `pg.DatabaseError` rather than a subclass, so a session that went
#: away is not a statement the server refused, and there is nothing to file the
#: attempt against and nothing a caller can mint its way past. Answered rather
#: than dropped, because a client left holding a socket that closes mid-request
#: cannot tell this door from the target it was asking for.
UNAVAILABLE = "door-unavailable"

#: The Program requires a header on every request and the door cannot produce its
#: value. Its own token because it is the one refusal here that the caller cannot
#: act on at all: the capability is live, the scope allows the target, the budget
#: has room, and what is missing is a value only an operator can provide. A caller
#: that read it as a capability refusal would give up on a Program that is one
#: `rk header provision` away from working.
HEADERLESS = "required-header-refused"

#: The one required-header refusal whose prose the caller is allowed to read.
#: Every other one down that path is the database's error text about this door's
#: SQL, and the thing being fenced is the caller; this one is the door's own
#: sentence about an operator's configuration, and withholding it would leave a
#: Program refusing every request for a reason nobody can see from either side.
HEADER_MISSING = "required header missing"

#: What an ambiguous take says, in one place because two paths report it and a
#: caller comparing the two would otherwise be reading a difference that means
#: nothing.
TWO_HEADERS = "the request carries two of one control header"

#: And what it says when the two are on different hops: the tunnel offered one
#: capability and the request inside it another. Distinct prose because the
#: caller who does it has made a different mistake from the one who sent the
#: same header twice, and the fix is not the same either.
TWO_HOPS = "the tunnel and the request inside it disagree about the control headers"

#: The answer that opens a tunnel. Reason phrase and not a status alone, because
#: it is the string every proxy has sent since RFC 2817 and clients match on it.
ESTABLISHED = "Connection Established"

#: Why a door with no authority still refuses one. An operator who did not name
#: a certificate directory gets a refusal that says so, rather than a tunnel
#: this process would have to relay blind.
NO_AUTHORITY = f"this door was started without a certificate authority (${AUTHORITY_VARIABLE})"

#: The one destination this door carries without a capability: the model its
#: children think with. `tls.agent_environment` exempts nothing, so a child's
#: own session reaches Anthropic through this proxy like everything else -- and
#: the CLI has no capability to send, the orchestrator being started with none
#: at all. Every request it made was answered `407 no-program`, and every run
#: died before it thought once.
#:
#: This is not target egress. No Program's budget pays for it, no scope admits
#: it, and nothing a Receipt could describe crosses it: what goes out is the
#: session the runtime itself opened. Pinned to the exact name and port, so the
#: exemption cannot be widened by a child naming a host that merely ends the
#: same way. Telemetry is deliberately not here -- the CLI also dials a logging
#: endpoint, and a hunt's telemetry is not this door's to forward.
CONTROL_PLANE = frozenset({("api.anthropic.com", 443)})

#: What the log line calls a tunnel this door carried rather than terminated.
CARRIED = "control-plane"

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

#: The line that makes a wire view the document of one exchange rather than of
#: the bytes it happened to carry. Under the internal prefix, so it is the
#: door's own statement and never something a target sent: `describes_this_hop`
#: keeps the prefix off the wire in both directions.
EXCHANGE = INTERNAL + "exchange"

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

#: The statuses that point a client somewhere else. Named because the door does
#: not follow one -- the client does, back through this same fence, where the
#: new URL is canonicalised and decided on its own -- and what the door owes the
#: record is the target it handed over, canonicalised the same way.
REDIRECTS = frozenset({301, 302, 303, 307, 308})

# Response fields whose value is authentication material issued by the target,
# rather than content the Agent may consume.  Header names are the enforceable
# boundary available before ticket 12 adds per-Identity body projections.
#: What stands in an Agent-visible body where a credential value stood. A
#: marker rather than an empty string, so that a body the Agent reads says a
#: value was taken out rather than reading as a body the target sent short.
REDACTION = b"[redacted]"

WIRE_RESPONSE_HEADERS = frozenset(
    {
        "authentication-info",
        "proxy-authenticate",
        "proxy-authentication-info",
        "set-cookie",
        "set-cookie2",
        "www-authenticate",
    }
)


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
        pinned: tuple[str, ...] = (),
        retry_at: datetime | None = None,
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
        #: What the name resolved to, on the refusals that happen after it did.
        #: Carried on the exception rather than passed to the recorder, because
        #: the line that refuses an address is the only line that knows which
        #: addresses were on the table, and a blocked Receipt that named none of
        #: them would say a name was refused without saying what it pointed at.
        #:
        #: Always the addresses rather than one of them joined into a string, so
        #: that a refusal knowing one and a refusal knowing four are the same
        #: kind of thing here and `pinned_ips` is written in one place.
        self.pinned = pinned
        #: When the same request would be worth making again, on the refusals
        #: that are about a limit rather than about authority. Nothing on the
        #: rest, and that absence is the fact: a capability that lapsed does not
        #: come back, so a retry time on one would be this door telling a caller
        #: to keep asking. The database computes it, because it holds the bucket
        #: this request would have drawn from.
        self.retry_at = retry_at


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
    identity_entity_id: str | None = None
    identity_label: str | None = None


@dataclass(frozen=True)
class FixtureAddress:
    """Where an evaluation put the fixture it is grading, as the database said.

    Two fields rather than one, because the class is the database's answer and
    not this process's opinion of it. A door that filled in `fixture` for itself
    would be describing its own behaviour on a row an auditor reads as a
    description of the policy.

    The third is the anchor, and it comes from the same row for the same reason.
    A fixture's certificate is signed by an authority `rk playbook evaluate`
    minted for this Program alone, so the only party that can say which authority
    that is, is the one holding the row -- and a door that picked a trust anchor
    for itself would be deciding what counts as a verified target.
    """

    address: str
    scope_class: str
    #: The PEM certificate a transport measurement of this fixture is verified
    #: against, and `None` for a cleartext one. Used at no other address and for
    #: no other Program: it reaches `connect` only on the probe dialled at this
    #: row's own host and port.
    trust_anchor: str | None = None


@dataclass(frozen=True)
class Reservation:
    """One request's share of a Program's budget, taken or refused.

    A refusal comes back as a value rather than as an exception, unlike every
    other decision this door asks the database for. That is deliberate: the other
    refusals mean the request had no business being made, and this one means it
    had business being made later. The two are told apart by `granted`, and the
    caller of a refused one still owes it nothing -- there is no slot to give
    back, which is why `id` is empty on exactly those.
    """

    id: str | None
    granted: bool
    reason: str
    retry_at: datetime | None
    target: str


@dataclass
class IdentityBinding:
    """One leased Identity slot opened into short-lived proxy memory."""

    entity_id: str
    label: str
    revision: int
    binding_revision: int
    session: identity.Session = field(repr=False)
    generation: int = 0
    salt: bytes = field(default=b"", repr=False)
    root: seal.Root | None = field(default=None, repr=False)
    changed: bool = False

    @classmethod
    def provisioned(
        cls,
        *,
        entity_id: str,
        label: str,
        revision: int,
        material: dict,
        binding_revision: int = 1,
    ) -> IdentityBinding:
        """Build a binding from control-side material before it is encrypted."""
        return cls(
            entity_id,
            label,
            revision,
            binding_revision,
            identity.Session.from_material(material),
        )


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


def merge_control(tunnel: Control, inner: Control) -> Control:
    """One request's control, from the two hops a tunnelled one arrives on.

    Not a preference for one hop: a merge, because no client puts everything on
    the same hop. `urllib` moves `Proxy-Authorization` onto the CONNECT and
    leaves every other header on the request inside, `curl --proxy-header` puts
    both on the CONNECT, and a client that has never heard of this harness puts
    the capability where HTTP says it goes and nothing else anywhere. Requiring
    one shape would refuse the two of those three that are ordinary HTTP.

    What is refused is disagreement. Two capabilities across two hops is the
    same request meaning two things as two capabilities in one header, and the
    reasoning `take_control` gives applies unchanged: resolving it in either
    direction lets a caller hide one behind the other. Agreement is not
    disagreement -- a client that repeats itself on both hops has said one thing
    twice.
    """
    if tunnel.ambiguous or inner.ambiguous:
        return Control(None, tunnel.program or inner.program, ambiguous=True)
    capability, split = _agreed(tunnel.capability, inner.capability)
    program, disputed = _agreed(tunnel.program, inner.program)
    return Control(capability, program, ambiguous=split or disputed)


def _agreed(tunnel: str | None, inner: str | None) -> tuple[str | None, bool]:
    """One value from two hops, or nothing and the fact that they differed."""
    if tunnel is not None and inner is not None and tunnel != inner:
        return None, True
    return (tunnel if tunnel is not None else inner), False


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


def with_required(
    headers: list[tuple[str, str]], required: list[tuple[str, str]]
) -> list[tuple[str, str]]:
    """The wire headers after the Program's required identifiers own their names.

    Replacement rather than addition, matching `Session.inject`: a name the
    Program requires is a name nothing else may also send, or the target reads
    two values for one header and picks whichever its parser prefers. The list
    comes back unchanged when nothing is required, so the ordinary request is not
    copied for the sake of a rule that does not apply to it.
    """
    if not required:
        return headers
    owned = {name.lower() for name, _ in required}
    return [
        (name, value) for name, value in headers if name.lower() not in owned
    ] + list(required)


def response_for_agent(headers: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Remove target-issued authentication material from an Agent response.

    The unmodified list remains the wire view.  Returning a new list makes the
    transformation explicit at the call site: the caller is answered from this
    value and the encrypted artifact is made from the original.
    """
    return [
        (name, value)
        for name, value in headers
        if name.lower() not in WIRE_RESPONSE_HEADERS
    ]


def project_identity_response(
    headers: list[tuple[str, str]], body: bytes, secrets: Sequence[str] = ()
) -> tuple[list[tuple[str, str]], bytes]:
    """The Agent's view of a response some Identity's credential was spent on.

    Redaction and not suppression, because the two halves of the message are
    read by different things. A body is read by the Agent, and story 120 asks
    for exactly that: agent-visible Artifacts redacted, so that exact bytes can
    be cited without exposing injected secrets. Withholding it whole would cite
    nothing and would make an authenticated exchange -- the one an access
    control finding is made of -- an exchange whose answer nobody may read.

    A header is not read, it is parsed, so one carrying credential material is
    dropped rather than marked: `/continue/[redacted]` is a `Location` that
    canonicalises into a URL no target ever pointed at, and something
    downstream would treat it as one. Dropped, it is absent, and the sealed
    wire view is where the exact bytes stay.

    Reflection is still not perfectly recognisable -- a target may transform a
    value beyond any spelling `_renderings` knows -- so what this narrows is
    the ordinary case rather than closing the class. What makes that honest is
    the record: the Agent view and the wire view are hashed separately and the
    difference is sealed, so an exchange whose redaction was incomplete is one
    an auditor can still see whole.
    """
    renderings = [rendering for secret in secrets for rendering in _renderings(secret)]
    kept = [
        (name, value)
        for name, value in response_for_agent(headers)
        # Name and value both: a target that echoes a token into a header's
        # name has reflected it as surely as one that echoes it into the value,
        # and the field it chose is not the Agent's business either way.
        if not any(
            rendering in f"{name}: {value}".encode("utf-8", "surrogateescape")
            for rendering in renderings
        )
    ]
    for rendering in renderings:
        body = body.replace(rendering, REDACTION)
    return kept, body


def project_identity_request(
    headers: list[tuple[str, str]], body: bytes, secrets: Sequence[str] = ()
) -> tuple[list[tuple[str, str]], bytes]:
    """The Agent's view of a request made while some Identity's credential was live.

    Redaction on this side was not needed while the only thing an Agent could
    put on a wire was headers it wrote itself and the only injected material
    was headers the door added, because the two views were then built from one
    body and that body was always empty. Ticket 96 makes a body something a
    model composes, and an Agent that got a credential value from anywhere --
    a target that echoed one past `_renderings`, a configuration somebody
    pasted, a guess that happened to be right -- can now write it into the
    request rather than only read it out of a response. The agent-visible
    request Artifact is where that would be stored in the clear, so it is
    scrubbed against the same values the response is scrubbed against.

    Replacement and not suppression, and unlike the response side that goes for
    the headers too. A response header carrying a credential is dropped because
    a header is parsed rather than read, and `/continue/[redacted]` is a
    `Location` something downstream would follow. A request header is the
    Agent's own account of what it sent, so dropping one would make the record
    say the Agent sent something it did not, and nothing downstream parses this
    document -- what is parsed is the wire view, which is sealed and exact.

    `Content-Length` is restated rather than scrubbed, and that is the one
    place this differs from what it mirrors. On the response side the length is
    the target's claim and the door does not rewrite a target's words. Here it
    is the door's own measurement of the door's own document, so an Agent view
    whose body has been shortened states the length of the body it actually
    contains, and an auditor reading it does not see a message that was framed
    for more bytes than it holds. The wire view keeps the number that went out.
    """
    renderings = [rendering for secret in secrets for rendering in _renderings(secret)]
    if not renderings:
        return headers, body
    scrubbed = body
    for rendering in renderings:
        scrubbed = scrubbed.replace(rendering, REDACTION)
    kept = [
        (name, str(len(scrubbed)))
        if name.lower() == "content-length"
        else (_scrubbed(name, renderings), _scrubbed(value, renderings))
        for name, value in headers
    ]
    return kept, scrubbed


def _scrubbed(text: str, renderings: Sequence[bytes]) -> str:
    """One header's name or value with every rendering of a secret taken out.

    Through bytes rather than over the string, because `_renderings` answers in
    bytes and it answers in bytes for a reason: a value's base64 and hex
    spellings are byte transformations and a comparison done in text would have
    to guess an encoding for each of them.
    """
    raw = text.encode("utf-8", "surrogateescape")
    for rendering in renderings:
        raw = raw.replace(rendering, REDACTION)
    return raw.decode("utf-8", "surrogateescape")


def _renderings(secret: str) -> tuple[bytes, ...]:
    """The spellings of one credential value a target is likely to echo back.

    A value that made it onto a wire comes back through whatever the target did
    with it on the way: quoted into a URL, encoded into a token, printed into a
    debug page. These are the transformations that survive a round trip through
    an ordinary web application without changing what the value is, so they are
    the ones searched for. Anything richer -- a hash, a truncation, half a value
    on each side of a template -- is not recoverable by search and is not
    pretended to be.
    """
    raw = secret.encode("utf-8", "surrogateescape")
    if not raw:
        return ()
    return tuple(
        dict.fromkeys(
            (
                raw,
                quote(secret, safe="").encode("ascii"),
                base64.b64encode(raw),
                base64.b64encode(raw).rstrip(b"="),
                base64.urlsafe_b64encode(raw),
                base64.urlsafe_b64encode(raw).rstrip(b"="),
                raw.hex().encode("ascii"),
                raw.hex().upper().encode("ascii"),
            )
        )
    )


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


def redirected(url: str, location: str | None) -> str | None:
    """Where a redirect points, canonicalised, or nothing when it points nowhere.

    The door does not follow one and must not: following would spend a
    capability on a URL the caller never asked for, and the caller is going to
    come back through this same fence anyway, where the new URL is canonicalised
    by `_request` and decided on its own like any other. What this is for is the
    record. A `Location` is the target's text, it is relative as often as it is
    absolute, and an auditor reading a Receipt for a 302 has no way to chain it
    to the next Receipt unless the door writes down the same spelling the next
    decision will be made against.

    The query goes no further than `query_sha256` lets one go: a redirect
    carries session identifiers and occasionally a credential, and a note is
    read by a person rather than hashed. Nothing readable comes back as nothing
    at all -- a `Location` this canonicaliser refuses is one the next request
    would be refused for, and repeating the target's own bytes into a record to
    say so would be putting unparsed input where an operator reads prose.
    """
    # Stripped before it is tested, not after: `urljoin` reads an empty reference
    # as "the same URL", so whitespace alone would be recorded as a redirect
    # pointing at the request that produced it.
    pointing = (location or "").strip()
    if not pointing:
        return None
    try:
        target = scope.canonical_request(urljoin(url, pointing))
    except (scope.PolicyError, ValueError):
        return None
    authority = _authority(target.host, target.port, target.protocol)
    return f"{target.protocol}://{authority}{target.path_norm}"


def transcript(start: str, headers: list[tuple[str, str]], body: bytes) -> bytes:
    """One HTTP message as bytes, in the order it went or came.

    Reconstructed from what this process sent or read rather than captured off
    the socket, which is what makes it an honest subject for a hash: the bytes
    named by the Receipt are the bytes this fence handled, headers included, and
    a control header cannot appear in them because it is not in the list.
    """
    head = start + "\r\n" + "".join(f"{name}: {value}\r\n" for name, value in headers) + "\r\n"
    return head.encode("latin-1", "replace") + body


def wire_view(
    start: str, headers: list[tuple[str, str]], body: bytes, *, exchange: str
) -> bytes:
    """The same message, as the document of the one exchange that carried it.

    Sealed material and Agent-visible material share one content-addressed
    store, where the hash is the whole identity of an artifact and an artifact
    is either readable or sealed and never both. The bytes of a message are not
    unique to an exchange: the same page fetched anonymously and then with an
    Identity produces one Agent artifact and one wire view that are the same
    bytes, the two classifications land on one row, and whichever exchange
    arrives second cannot be recorded at all -- the target has answered and
    there is nowhere to put the answer.

    The exchange line is what separates them. It names the moment and the
    request, both of which the Receipt already carries in the clear, so it
    withholds nothing and reveals nothing; what it does is make a wire view a
    document no anonymous fetch can reproduce, which is the property the store
    needs and the bytes alone do not have.
    """
    return transcript(start, [(EXCHANGE, exchange)] + headers, body)


def peer(url: str) -> tuple[str, int]:
    """The door's address, as whoever is about to send it a capability sees it.

    Plain HTTP and nothing else, because the capability rides on that hop and a
    client that spoke TLS to the door would be verifying the door's own
    certificate against the door's own authority -- which proves nothing about
    who is on the other end and hides the exchange from the fence that has to
    read it.

    Where the door *is* differs by side and is not decided here. The operator's
    runtime reaches it on loopback and asserts as much in `endpoint`; a child
    reaches it by container name over the one internal network its boundary
    joins, and there is no loopback there to assert.
    """
    parts = urlsplit(url)
    if parts.scheme != "http":
        raise Refused(
            "endpoint refused",
            f"{url} is not an http:// endpoint; the door speaks plain HTTP",
        )
    host = parts.hostname or ""
    try:
        port = parts.port or 80
    except ValueError as error:
        raise Refused("endpoint refused", f"the proxy port cannot be read: {error}") from error
    if not host:
        raise Refused("endpoint refused", f"{url} names no host to send the capability to")
    return host, port


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
    host, port = peer(url)
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


#: The files a container runtime leaves behind to say a process is inside one.
#: Docker writes the first, Podman the second. Read rather than trusted from an
#: argument, because the argument is the thing being checked: a caller asking to
#: bind wide is asking for the rule to be relaxed, and the answer to "may it be"
#: cannot come from the asker.
CONTAINER_MARKERS = (Path("/.dockerenv"), Path("/run/.containerenv"))


def _in_a_container() -> bool:
    """Whether this process is inside a container.

    Distinct from `serve`'s `contained` argument, which is a caller saying it
    means to bind wide.  One is a claim and the other is the fact it is held to.
    """
    return any(marker.exists() for marker in CONTAINER_MARKERS)


def _unbindable(host: str, contained: bool) -> str | None:
    """Why this address may not be listened on, or None if it may.

    Loopback is always allowed and needs no argument: nothing off this machine
    can reach it.

    Anything wider is bearer material on a routable interface, which is the hole
    `endpoint` refuses from the other side, so it needs two things at once. The
    caller has to say it means it -- `rk proxy serve` never does, which is what
    keeps this from becoming a second way to expose a door on a host -- and the
    process has to actually be in a container, so that "routable" means routable
    from the container network and nothing else. The second is checked here
    rather than left to the operator because a door started with the flag on a
    host would be exactly the listener the first rule exists to prevent, and it
    would look like it was working.

    Which container network, and whether the door is its only peer, is not
    knowable from in here: it takes an engine, and a door holding an engine
    socket would be a worse hole than the one this closes. `door.start` asks
    that question from outside, before and after this process binds.
    """
    if _loopback(host):
        return None
    if not contained:
        return f"{host} is not a loopback interface, and a capability is bearer material"
    if not _in_a_container():
        return (
            f"{host} is not a loopback interface and this is not a container; "
            "a door binds wide only where a container network is the whole of "
            "what can reach it"
        )
    return None


# ---------------------------------------------------------------------------
# The database half
# ---------------------------------------------------------------------------


#: Every canonical value the decision is made from, and none it could re-derive.
#: 039 read the host and port back out of the URL with a regular expression while
#: this process parsed the same URL with `urlsplit`; two parsers over one string
#: is a differential waiting to be found, and the one that matters is the one
#: whose answer the socket is opened against. So the proxy sends what it
#: canonicalised and the function refuses anything that is not canonical.
#:
#: The eighth value is not canonical and is not a spelling: it is whether this
#: request has bytes after its headers. It goes to the same decision rather than
#: to a second one because a body is part of the request, and a separate call
#: would be one a door with a bug could simply not make -- which is the whole
#: difference between a check and a suggestion. What the function does with it
#: is ticket 96's rule: a body is refused unless the Tool run was opened as
#: body-bearing.
AUTHORIZE = (
    "SELECT program_id::text, tool_run_id::text, scope_version, scope_class,"
    "       identity_entity_id::text, identity_label"
    "  FROM authorize_identity_egress_request("
    "       $1, $2, $3, $4, $5::integer, $6, $7, $8::boolean)"
)

#: The second decision, about the address rather than the name. It is a separate
#: function because it is a separate question asked at a separate moment: the
#: address does not exist until the name has been resolved, and the name is not
#: resolved until the first decision has said yes. It is in the database rather
#: than here for the same reason the first one is -- and for one more. This role
#: holds no `SELECT` on `program_scope_rules` and `scope_class_of` is not a
#: definer function, so the proxy cannot read the policy even to agree with it.
#: The capability is passed rather than the Program: the function resolves it and
#: takes the Program from that, so a door made to lie about which Program it is
#: serving cannot have an address checked against somebody else's policy.
AUTHORIZE_ADDRESS = (
    "SELECT scope_class, reason"
    "  FROM authorize_identity_egress_address($1, $2, $3, $4::integer, $5)"
)

#: The question that comes before both of those, and almost always answers
#: nothing. An evaluation serves its fixture on one of this machine's own private
#: addresses and records where it put it; every other request there is has no such
#: row, and the two decisions above are the whole of what decides it. It is asked
#: before the name is resolved because that is the point -- an evaluation's target
#: is scoped as `<fixture>.localhost`, and a lookup would answer 127.0.0.1 and be
#: refused one line later, correctly and uselessly. The cost is one round trip on
#: every request, which is the price of the answer coming from the database: a
#: door that decided for itself which targets are synthetic could call anything
#: one.
FIXTURE_ADDRESS = (
    "SELECT address, scope_class, trust_anchor"
    "  FROM authorize_fixture_address($1, $2, $3, $4::integer)"
)

#: What that function says when the capability, rather than the address, is what
#: it refused. Matched as a string because it arrives as one: both refusals carry
#: `23514`, so the code separates them from a constraint violation and this
#: separates them from each other.
LAPSED = "egress capability refused"

#: And what both scope decisions say when the request is in scope no longer.
#: Named beside `LAPSED` for the same reason: three refusals share `23514`, and
#: the reservation has to tell the one that means "later" from the two that mean
#: "no". A scope version replaced between the two decisions is the second kind.
UNSCOPED = "egress request is outside current scope"

#: One call, one transaction: the artifacts of the exchange and the Receipt that
#: names them are written together or not at all. A Receipt naming bytes no row
#: registered is a dangling reference, and rows for bytes no Receipt names are
#: an artifact nobody can reach.
RECORD_SEALED = (
    "SELECT record_identity_proxy_exchange("
    "$1, $2::jsonb, $3::jsonb, $4::jsonb, $5, $6::bigint, $7::jsonb)"
)

OPEN_IDENTITY = (
    "SELECT identity_entity_id::text, identity_label, revision, binding_revision, alg, nonce_hex,"
    "       kek_gen, envelope_hex, ciphertext_sha256, salt_hex, root_check_hex, audit_id"
    "  FROM open_identity_slot($1, $2)"
)

CONFIRM_IDENTITY = "SELECT confirm_identity_slot_open($1, $2, $3::uuid, $4)"

#: One row per header the capability's live scope version requires, provisioned
#: or not. The nulls are answers rather than absences: a declared header with no
#: value is a request that must not leave, and a function that returned nothing
#: for it would be saying the Program requires no headers.
OPEN_HEADERS = (
    "SELECT ord, name, revision, alg, nonce_hex, kek_gen, envelope_hex,"
    "       ciphertext_sha256, salt_hex, root_check_hex, audit_id"
    "  FROM open_required_headers($1)"
)
CONFIRM_HEADERS = "SELECT confirm_required_headers_open($1, $2::uuid, $3)"

WIRE_KEYING = (
    "SELECT generation, salt_hex, root_check_hex"
    "  FROM ensure_proxy_wire_keying($1, $2::bytea, $3::bytea)"
)

#: Answers with the Receipt's label rather than its row id, because a label is
#: the only name the agent reading this refusal can look up.
BLOCKED = "SELECT write_blocked_receipt($1::uuid, $2::jsonb, $3)"

#: Ticket 93. The one write the door makes about a handshake nobody but the door
#: took, and it opens the runtime Tool run the row is attributed to as well --
#: `rk2_proxy` holds EXECUTE on writers and no DML, so the provenance of a probe
#: is minted by the same function that files it or the probe has none.
MEASUREMENT = "SELECT record_transport_measurement($1, $2::jsonb)"

#: The third decision, and the only one that is not about this request alone. It
#: takes the capability rather than the Program for the same reason the address
#: check does -- it resolves it and takes the Program from that -- and it takes
#: the canonical request because it has to find the scope rule that matched, and
#: the per-target limits hang off that rule rather than off the hostname the
#: caller wrote. Everything it decides is decided under a row lock, which is what
#: makes the limits a Program's limits rather than a process's.
RESERVE = (
    "SELECT reservation::text, granted, reason, retry_at, scope_target"
    "  FROM reserve_egress_slot($1, $2, $3, $4::integer, $5, $6)"
)

#: And giving it back. `contacted` is the fact the door alone holds: the database
#: knows a slot was taken, and only this process knows whether a socket towards
#: the target was ever opened. A slot released as uncontacted refunds itself, so
#: the counters count exchanges rather than attempts.
RELEASE = "SELECT release_egress_slot($1::uuid, $2)"

#: Whether this Program already holds an agent-visible reference to these bytes.
#: Asked of the database rather than of the store, because the store is a
#: content-addressed heap five modules write and a hit in it says the bytes are
#: on disk, not that this Agent may read them.
READS = "SELECT program_reads_artifact($1, $2)"

BIND = "SELECT set_config('rk2.program_id', $1, false)"


def as_object(answer: object) -> dict:
    """One `jsonb` answer as a mapping, whichever shape the driver returned it in.

    Both sides of this module read a function that answers with an object, and a
    second spelling of the same two-branch decode is a second place for the two
    to disagree about what an answer with no rows looks like. Public because the
    execution slice reads the same three functions -- `authorize_tool_run`,
    `promote_proposal`, `finish_task_attempt` -- and a copy over there would be
    that second place, one import away from the original.
    """
    return json.loads(answer) if isinstance(answer, str) else dict(answer)


def _moment(answer: object) -> datetime | None:
    """One `timestamptz` as a moment, or nothing when the column was null.

    The driver hands timestamps over as the text the server sent, offset and
    all, so this is a parse rather than a conversion and the result is aware
    whatever the session's time zone happens to be. Absent stays absent: the
    column is null on the refusals that have no time to name, and inventing one
    would tell a caller to retry something that will never lift.
    """
    if answer is None:
        return None
    return datetime.fromisoformat(str(answer))


def _refusal(error: pg.DatabaseError, address: str) -> Refused:
    """Which of the two things the address decision refuses, this one was.

    The address check resolves the capability again before it looks at anything
    else, so a Tool run that closed, a Program that was retired or a task lease
    that lapsed between the two decisions arrives here rather than at the first
    one. Filing that as `address refused` would be a Receipt sending an auditor
    to look at an address that was never the problem, so it is filed under the
    same reason the first decision would have used, and the address it had
    already pinned rides along either way.
    """
    reason = "capability refused" if LAPSED in str(error) else "address refused"
    return Refused(reason, str(error), pinned=(address,))


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

        Guarded here rather than at each of the twelve places that bind, because
        every one of them wraps the query that follows and none of them wrapped
        this. A bind that raises `pg.DatabaseError` -- a session lost, or one
        left in an aborted transaction by the request before -- escapes handlers
        that catch `Refused`, and the exchange this one belongs to then gets no
        Receipt, no answer and no line in the log, which is the one failure this
        module says out loud. Typed, it is a refusal like any other: the caller
        answers 502, and the record that can still be written is written.

        A lost session is deliberately not caught here. `pg.ConnectionError_` is
        a sibling class, and a fence with no session behind it cannot file the
        refusal it would be raising -- so it belongs to `_serve`, which answers
        `door-unavailable` and says so out loud, rather than to a `Refused` that
        promises a Receipt nothing can write.
        """
        try:
            self.connection.execute(BIND, (program_id,))
        except pg.DatabaseError as error:
            raise Refused("program bind refused", str(error)) from error

    def authorize(
        self,
        program_id: str,
        capability: str,
        method: str,
        request: scope.Request,
        has_body: bool = False,
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
                        has_body,
                    ),
                ).rows
            except pg.DatabaseError as error:
                raise Refused("capability refused", str(error)) from error
        if not rows:
            raise Refused("capability refused", "no capability resolved")
        found, tool_run, version, klass, identity_id, identity_label = rows[0]
        return Authorization(
            program_id=str(found),
            tool_run_id=str(tool_run),
            scope_version=int(version),
            scope_class=str(klass),
            identity_entity_id=str(identity_id) if identity_id is not None else None,
            identity_label=str(identity_label) if identity_label is not None else None,
        )

    def fixture_address(
        self, program_id: str, capability: str, request: scope.Request
    ) -> FixtureAddress | None:
        """Where this Program's fixture is, if this Program is an evaluation.

        Nothing is the ordinary answer and means "resolve the name like any
        other": the row exists only for a Program that `rk playbook evaluate`
        opened and only for the one host and port it served a fixture at. What
        comes back instead of nothing is an address on this machine's own
        private network, which is where the evaluator bound the fixture so that
        the door can reach it and the children on the internal network cannot.

        Refusals arrive here the way they arrive at `authorize_address`, because
        the function asks the same questions for the same reason: this is asked
        after the name was decided and before anything is dialled, so the
        capability, the Identity lease and the Program's coverage of the host are
        all re-read here, and a lease that lapsed in between opens no socket down
        either route.
        """
        with self._lock:
            self._bind(program_id)
            try:
                rows = self.connection.execute(
                    FIXTURE_ADDRESS,
                    (capability, request.protocol, request.host, request.port),
                ).rows
            except pg.DatabaseError as error:
                raise _refusal(error, request.host) from error
        if not rows:
            return None
        anchor = rows[0][2]
        return FixtureAddress(
            address=str(rows[0][0]),
            scope_class=str(rows[0][1]),
            trust_anchor=None if anchor is None else str(anchor),
        )

    def authorize_address(
        self, program_id: str, capability: str, request: scope.Request, address: str
    ) -> None:
        """Decide the address the name answered with, before a socket is opened.

        The name was decided already. This asks the narrower question the name
        cannot answer: whether the machine it points at is one the Program
        withdrew. A policy stated in names says nothing about most addresses, and
        that silence is not a refusal -- it is the ordinary case, and refusing on
        it would refuse every request there is. What refuses is a withdrawal that
        reaches the address: an excluded network, an excluded address, whichever
        name was used to arrive at it.

        Nothing comes back, and that is the shape of the question rather than an
        omission. `authorize` returns a class because the Receipt records what a
        request was allowed AS; the answer here is `unlisted` for almost every
        address a name-based policy ever sees, so recording it would fill a
        column with a word that means "the policy is written in names".
        """
        with self._lock:
            self._bind(program_id)
            try:
                rows = self.connection.execute(
                    AUTHORIZE_ADDRESS,
                    (capability, request.protocol, request.host, request.port, address),
                ).rows
            except pg.DatabaseError as error:
                # The capability is resolved again inside that function, so this
                # is also where a capability that stopped being live between the
                # two decisions arrives. It is reported as what it is: a Receipt
                # reading "address refused" for a lapsed lease would send an
                # auditor looking at the address, which was never the problem.
                raise _refusal(error, address) from error
        if not rows:
            raise Refused("address refused", "no address verdict", pinned=(address,))

    def reserve(
        self, program_id: str, capability: str, request: scope.Request
    ) -> Reservation:
        """Take one request's worth of the Program's budget, or learn it is spent.

        Third of the three decisions, and the one that cannot be made here. Rate,
        burst and concurrency are properties of a Program, not of a process: two
        doors, two Tool runs and two threads of one Tool run all draw on the same
        allowance, and a counter in this process would be a counter of what this
        process happened to see. So the arithmetic happens under a row lock in
        the database, and what comes back is the verdict, not the numbers.

        It runs after `authorize` and before the name is resolved, which puts it
        on the right side of the only line that matters: a request refused here
        has not resolved a name, opened a socket or sent a byte. Spending budget
        on a request that scope would have refused would also let a caller
        measure the policy by watching its own allowance drain.
        """
        with self._lock:
            self._bind(program_id)
            try:
                rows = self.connection.execute(
                    RESERVE,
                    (
                        capability,
                        request.protocol,
                        request.host,
                        request.port,
                        request.path_raw,
                        request.path_norm,
                    ),
                ).rows
            except pg.DatabaseError as error:
                # Three refusals arrive down this one path, because the function
                # re-resolves the capability and re-finds the rule before it
                # looks at any limit: a Tool run that closed between the two
                # decisions, and a scope version replaced between them. Only the
                # third is a budget, and only a budget is worth retrying, so the
                # other two are filed under the name the first decision already
                # gives them -- a scope refusal caught here and a scope refusal
                # caught by `authorize` are one condition and read as one.
                said = str(error)
                unretryable = LAPSED in said or UNSCOPED in said
                raise Refused(
                    "capability refused" if unretryable else "budget refused", said
                ) from error
        if not rows:
            raise Refused("budget refused", "no reservation verdict")
        reservation, granted, reason, retry_at, target = rows[0]
        return Reservation(
            id=str(reservation) if reservation is not None else None,
            granted=bool(granted),
            reason=str(reason),
            retry_at=_moment(retry_at),
            target=str(target),
        )

    def release(self, program_id: str, reservation: str, contacted: bool) -> None:
        """Give the slot back, and say whether a target heard about it.

        Idempotent, because the caller releases from a `finally` and a request
        that was refused after contact runs through more than one of them. A
        second release of the same slot changes nothing, which is what makes the
        `finally` safe to write without asking whether an earlier one already ran.

        A slot that is never given back is not a hole. It expires on its own, and
        until it does it occupies concurrency -- so the failure mode of this call
        is a Program that is briefly more restricted than its policy says, which
        is the direction a fence should fail in.
        """
        with self._lock:
            self._bind(program_id)
            self.connection.execute(RELEASE, (reservation, contacted))

    def allowed_receipt(
        self,
        program_id: str,
        capability: str,
        receipt: dict,
        artifacts: list[dict],
        seals: list[dict] | None = None,
        binding: IdentityBinding | None = None,
    ) -> dict:
        """Record one exchange, under the Program this request was decided for.

        The bind is repeated here rather than inherited from `authorize`. One
        connection serves every handler thread, `set_config` is session-wide, and
        the target exchange happens outside the lock -- so between the decision
        and this write another thread's request has had every opportunity to
        rebind the session to its own Program. Binding again is what stops a
        served exchange from failing to record because somebody else was faster.
        """
        state: dict | None = None
        expected_revision: int | None = None
        identity_label: str | None = None
        if binding is not None:
            identity_label = binding.label
            expected_revision = binding.revision
            if binding.changed:
                if binding.root is None or not binding.salt or binding.generation < 1:
                    raise Refused(
                        "identity slot refused",
                        "the opened Identity has no authenticated keying context",
                        status=502,
                    )
                try:
                    state = identity.seal_session(
                        binding.session,
                        root=binding.root,
                        program_id=program_id,
                        identity_id=binding.entity_id,
                        generation=binding.generation,
                        salt=binding.salt,
                        binding_revision=binding.binding_revision,
                        revision=binding.revision + 1,
                    )
                except identity.Invalid as error:
                    raise Refused(
                        "identity session refused", str(error), status=502
                    ) from error

        with self._lock:
            self._bind(program_id)
            try:
                answer = self.connection.execute(
                    RECORD_SEALED,
                    (
                        capability,
                        json.dumps(receipt),
                        json.dumps(artifacts),
                        json.dumps(seals or []),
                        identity_label,
                        expected_revision,
                        json.dumps(state) if state is not None else None,
                    ),
                ).scalar()
            except pg.DatabaseError as error:
                raise Refused("receipt write refused", str(error)) from error
        return as_object(answer)

    def measurement(self, program_id: str, capability: str, receipt: dict) -> str:
        """File one handshake this door took on its own behalf, and name it.

        The narrowest of the writes here: no artifacts, no seals and no Identity,
        because a probe sends no request and reads no body. What it carries is
        the wire side of a handshake and where it was taken, and everything
        citability turns on -- the purpose, the Lane, the decision, the
        interception -- is assigned by the function rather than sent to it.

        A refusal is raised like any other so that the caller can decide what it
        costs, and the caller decides it costs nothing: an exchange that was
        served is served whether or not the door managed to also measure the
        target.
        """
        with self._lock:
            self._bind(program_id)
            try:
                return str(
                    self.connection.execute(
                        MEASUREMENT, (capability, json.dumps(receipt))
                    ).scalar()
                )
            except pg.DatabaseError as error:
                raise Refused("measurement write refused", str(error)) from error

    def reads(self, program_id: str, capability: str, sha256: str) -> bool:
        """Whether the Agent of this capability's Program can already read these bytes.

        A refusal is an answer of "no" rather than an exception: this decides
        whether the door withholds something it is allowed to withhold, and a
        Program whose capability just lapsed is one the withholding is right for.
        """
        with self._lock:
            self._bind(program_id)
            try:
                return bool(self.connection.execute(READS, (capability, sha256)).scalar())
            except pg.DatabaseError:
                return False

    def open_identity(
        self,
        program_id: str,
        capability: str,
        entity_id: str,
        label: str,
        root: seal.Root,
    ) -> IdentityBinding:
        """Open exactly the Identity the live capability currently leases."""
        with self._lock:
            self._bind(program_id)
            try:
                rows = self.connection.execute(OPEN_IDENTITY, (capability, label)).rows
            except pg.DatabaseError as error:
                raise Refused("identity slot refused", str(error)) from error
        if not rows:
            raise Refused("identity slot refused", "no live Identity slot resolved")
        (
            found_id,
            found_label,
            revision,
            binding_revision,
            alg,
            nonce_hex,
            generation,
            envelope_hex,
            ciphertext_sha256,
            salt_hex,
            root_check_hex,
            audit_id,
        ) = rows[0]
        try:
            if str(found_id) != entity_id or str(found_label) != label:
                raise Refused("identity slot refused", "the selected Identity changed")
            envelope = bytes.fromhex(str(envelope_hex))
            if not hmac.compare_digest(digest(envelope), str(ciphertext_sha256)):
                raise seal.Tampered("Identity slot envelope digest disagrees")
            salt = bytes.fromhex(str(salt_hex))
            number = int(generation)
            session = identity.open_session(
                root=root,
                program_id=program_id,
                identity_id=entity_id,
                revision=int(revision),
                binding_revision=int(binding_revision),
                generation=number,
                salt=salt,
                root_check=bytes.fromhex(str(root_check_hex)),
                alg=str(alg),
                nonce=bytes.fromhex(str(nonce_hex)),
                envelope=envelope,
            )
        except (ValueError, identity.Invalid, seal.Tampered, seal.Unusable, Refused):
            self._confirm_identity_open(program_id, capability, label, str(audit_id), "denied")
            raise
        self._confirm_identity_open(program_id, capability, label, str(audit_id), "ok")
        return IdentityBinding(
            entity_id=entity_id,
            label=label,
            revision=int(revision),
            binding_revision=int(binding_revision),
            session=session,
            generation=number,
            salt=salt,
            root=root,
        )

    def _confirm_identity_open(
        self,
        program_id: str,
        capability: str,
        label: str,
        audit_id: str,
        outcome: str,
    ) -> None:
        """Append the authenticated result of a previously audited slot-open attempt."""
        with self._lock:
            self._bind(program_id)
            try:
                self.connection.execute(
                    CONFIRM_IDENTITY, (capability, label, audit_id, outcome)
                )
            except pg.DatabaseError as error:
                raise Refused("identity slot refused", str(error)) from error

    def required_headers(
        self, program_id: str, capability: str, root: seal.Root | None
    ) -> list[tuple[str, str]]:
        """The headers this Program requires on every request, with their values.

        Empty when the policy requires none, which is the ordinary case and costs
        one query and no audit row. When it requires any, every one of them has to
        open: a Program that states it identifies itself with `X-Bounty-Id` and
        then reaches a target without it has sent traffic nobody can attribute,
        which is the failure the declaration exists to prevent. So a header with
        no provisioned value refuses the request rather than sending the rest.
        """
        with self._lock:
            self._bind(program_id)
            try:
                rows = self.connection.execute(OPEN_HEADERS, (capability,)).rows
            except pg.DatabaseError as error:
                raise Refused("required header refused", str(error), status=502) from error
        if not rows:
            return []

        audit_id = str(rows[0][10])
        try:
            if root is None:
                raise Refused(
                    HEADER_MISSING,
                    "this Program requires a header the door has no artifact key to open",
                    status=502,
                )
            answer: list[tuple[str, str]] = []
            for (
                _ord,
                name,
                revision,
                alg,
                nonce_hex,
                generation,
                envelope_hex,
                ciphertext_sha256,
                salt_hex,
                root_check_hex,
                _audit,
            ) in rows:
                if envelope_hex is None:
                    raise Refused(
                        HEADER_MISSING,
                        f"{name} is required on every request and no value is provisioned",
                        status=502,
                    )
                envelope = bytes.fromhex(str(envelope_hex))
                if not hmac.compare_digest(digest(envelope), str(ciphertext_sha256)):
                    raise seal.Tampered("header slot envelope digest disagrees")
                number = int(generation)
                salt = bytes.fromhex(str(salt_hex))
                if not hmac.compare_digest(
                    root.check(salt, generation=number),
                    bytes.fromhex(str(root_check_hex)),
                ):
                    raise Refused(
                        "required header refused",
                        "the proxy artifact key does not match this installation",
                        status=502,
                    )
                value = seal.unseal(
                    root.header_key(
                        salt,
                        generation=number,
                        program_id=program_id,
                        name=str(name),
                    ),
                    seal.Sealed.decode(envelope),
                    aad=seal.header_associated_data(
                        program_id=program_id,
                        name=str(name),
                        generation=number,
                        revision=int(revision),
                    ),
                )
                answer.append((str(name), value.decode("latin-1")))
        except (ValueError, seal.Tampered, seal.Unusable, Refused):
            self._confirm_headers_open(program_id, capability, audit_id, "denied")
            raise
        self._confirm_headers_open(program_id, capability, audit_id, "ok")
        return answer

    def _confirm_headers_open(
        self, program_id: str, capability: str, audit_id: str, outcome: str
    ) -> None:
        """Append the authenticated result of a previously audited header open."""
        with self._lock:
            self._bind(program_id)
            try:
                self.connection.execute(CONFIRM_HEADERS, (capability, audit_id, outcome))
            except pg.DatabaseError as error:
                raise Refused("required header refused", str(error), status=502) from error

    def wire_key(
        self, program_id: str, capability: str, root: seal.Root
    ) -> tuple[int, bytes]:
        """Derive the Program key after the database confirms its generation.

        The database supplies only a random salt and a root-check value.  The
        secret and the derived key never cross the connection, and a proxy with
        the wrong root refuses before producing ciphertext nobody can open.
        """
        proposed = seal.new_salt()
        with self._lock:
            self._bind(program_id)
            try:
                rows = self.connection.execute(
                    WIRE_KEYING,
                    (capability, proposed, root.check(proposed, generation=1)),
                ).rows
            except pg.DatabaseError as error:
                raise Refused("wire seal refused", str(error), status=502) from error
        if not rows:
            raise Refused("wire seal refused", "no active key generation", status=502)
        generation, salt_hex, root_check_hex = rows[0]
        number = int(generation)
        salt = bytes.fromhex(str(salt_hex))
        expected = root.check(salt, generation=number)
        if not hmac.compare_digest(expected, bytes.fromhex(str(root_check_hex))):
            raise Refused(
                "wire seal refused",
                "the proxy artifact key does not match this installation",
                status=502,
            )
        return number, root.program_key(salt, generation=number, program_id=program_id)

    def blocked_receipt(self, program_id: str, capability: str | None, receipt: dict) -> str:
        """File one refusal and return the label it was filed under."""
        with self._lock:
            self._bind(program_id)
            answer = self.connection.execute(
                BLOCKED, (program_id, json.dumps(receipt), capability)
            ).scalar()
        return str(answer)


# ---------------------------------------------------------------------------
# The server
# ---------------------------------------------------------------------------


Resolver = Callable[[str, int], tuple[str, ...]]


class Connector(Protocol):
    """How this door opens a socket towards a target.

    A protocol rather than a `Callable` alias because of the last argument: the
    trust anchor is keyword-only, so that the ordinary dial reads exactly as it
    did and the one call that measures a fixture says at the call site which
    authority it is measuring against.
    """

    def __call__(
        self,
        host: str,
        port: int,
        timeout: float,
        protocol: str,
        address: str,
        client_certificate: identity.ClientCertificate | None,
        *,
        anchor: str | None = None,
    ) -> tuple[http.client.HTTPConnection, Handshake | None]: ...


def resolve(host: str, port: int) -> tuple[str, ...]:
    """Every address one name answers with, in the order the resolver gave them.

    All of them, not the first: a name that answers with a public address and a
    private one is the shape of a rebinding attack, and a caller that saw only
    the address it was about to dial could not tell that apart from a name with
    one record. `destination` is what makes the distinction; this is only the
    lookup, and it is a seam so that a test can decide what a name answers
    without a resolver on the machine agreeing.
    """
    found = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return tuple(info[4][0] for info in found)


def unroutable(address: str) -> str | None:
    """Why one address may not be dialled from here, or nothing when it may.

    Named for the answer it gives rather than for the question: it speaks when
    an address is refused and stays silent when it is not, so `routable` would
    have read as true at every call site where it means the opposite.

    Deny by default, like the policy above it: an address is dialled because it
    is one the public internet routes to, not because it failed to match a list
    of bad ones. That is what makes the answer the same for the ranges nobody
    remembers -- carrier-grade NAT, the documentation blocks, the IPv4-mapped
    spelling of loopback -- as for `127.0.0.1`.

    The classes are named separately rather than collapsed into "not public"
    because each one is a different way in, and the blocked Receipt is read by
    somebody deciding whether a target was hostile or a Program was misconfigured:
    link-local is the cloud metadata endpoint, private is the operator's own
    network and this machine's provisioning and control ports, loopback is the
    door itself and the database behind it. Multicast is said out loud because
    it is the one class `is_global` answers yes for.
    """
    return scope.address_refusal(address)


def destination(host: str, port: int, resolver: Resolver) -> tuple[str, ...]:
    """The addresses the request may be sent to, or a refusal that opens nothing.

    Called after the capability has been spent and the scope check has passed,
    which is the whole of why it is a separate step. A DNS query is egress: it
    leaves this machine, it carries the name that was asked for, and a door that
    resolved before it decided would be answering "is this name in scope" with a
    lookup a watcher of the network can read. So the order is decide, then
    resolve, then dial.

    One bad address refuses the name rather than being skipped over. A name that
    answers with a routable address and an unroutable one has said two things,
    and picking the half that passes would let whoever controls the zone decide
    which half this door dials on the next lookup.
    """
    try:
        # Deduplicated here rather than in the resolver, so that it holds however
        # the name was looked up. A name with an A record and the mapped spelling
        # of the same address has said one thing twice, and a record listing it
        # twice reads as two answers that happen to agree.
        addresses = tuple(dict.fromkeys(resolver(host, port)))
    except OSError as error:
        raise Refused("target unresolved", f"{host} does not resolve: {error}") from error
    if not addresses:
        raise Refused("target unresolved", f"{host} resolves to no address at all")
    for address in addresses:
        refused = unroutable(address)
        if refused is not None:
            raise Refused(
                "address refused",
                f"{host} does not resolve to a public address: {refused}",
                pinned=addresses,
            )
    return addresses


def pinned_ips(addresses: tuple[str, ...]) -> str:
    """Every address a name answered with, in the column a Receipt reads it from.

    One spelling for the allowed row and the blocked one, because an auditor
    filtering `pinned_ips` across both is filtering one format. The order is the
    resolver's, so the address that was dialled -- or would have been -- is the
    first, and a row with several is a name that answered with several rather
    than a request that went to more than one place.
    """
    return ",".join(addresses)


def _retry_after(moment: datetime | None) -> list[tuple[str, str]] | None:
    """`Retry-After` as a whole number of seconds, or no header at all.

    Seconds rather than the date RFC 9110 also allows, because the caller's clock
    is not this machine's and the interval is what the answer means. Rounded up
    and floored at one: a client that retried after the truncated value would
    arrive fractionally too early and be refused again, and zero would read as
    "now", which is the one thing this header exists to say it is not.
    """
    if moment is None:
        return None
    waiting = (moment - datetime.now(timezone.utc)).total_seconds()
    return [("Retry-After", str(max(1, math.ceil(waiting))))]


@dataclass(frozen=True)
class Handshake:
    """What one TLS connection negotiated, and whether it was verified.

    Read off a live socket rather than declared by the code that opened it, so
    the record describes the connection that happened. `chain_verified` and
    `hostname_verified` come from the context the socket is wrapped in for the
    same reason: they are what OpenSSL was told to enforce on this handshake,
    not what the door intended to enforce.

    `defect` is the words the strict attempt failed with, on the connections
    that only completed because it was tried again without verification. It is
    the finding: a target whose certificate has expired, is self-signed or names
    another host is a target with a defect, and the whole point of reaching it
    anyway is to have that written down.
    """

    tls_version: str | None
    cipher: str | None
    alpn: str | None
    #: The name this side asked for, which is the name the certificate below was
    #: checked against. Null on the door's own listening socket: a server is told
    #: the name, it does not send one.
    sni: str | None
    cert_sha256: str | None
    cert_issuer: str | None
    cert_subject: str | None
    cert_not_after: str | None
    chain_verified: bool
    hostname_verified: bool
    defect: str | None = None


def _name(field: tuple | None) -> str | None:
    """One certificate name, flattened to the pairs OpenSSL reported.

    The attribute names are OpenSSL's own spelling and are not shortened: a
    column an auditor compares between the two sides of an intercepted exchange
    has to hold one vocabulary, and the abbreviation table that would produce
    `CN=` is a second one.
    """
    if not field:
        return None
    return ", ".join(f"{name}={value}" for rdn in field for name, value in rdn)


def handshake(sock: socket.socket, defect: str | None = None) -> Handshake | None:
    """The facts of a completed TLS handshake, or nothing for a plain socket.

    Nothing rather than an empty record, because "this hop was not TLS" and
    "this hop was TLS and told us nothing" are different facts and the Receipt
    distinguishes them by whether the columns are null.

    The certificate is read in binary form because that is the only form
    available on an unverified connection: `getpeercert()` answers with an empty
    mapping when the context was told not to verify, while the DER is there
    either way. So a downgraded exchange still names the certificate it saw by
    hash -- which is the identifying fact -- and leaves the parsed fields null
    rather than inventing them.
    """
    if not isinstance(sock, ssl.SSLSocket):
        return None
    context = sock.context
    parsed = sock.getpeercert() or {}
    der = sock.getpeercert(binary_form=True)
    expires = parsed.get("notAfter")
    return Handshake(
        tls_version=sock.version(),
        cipher=(sock.cipher() or (None,))[0],
        alpn=sock.selected_alpn_protocol(),
        sni=sock.server_hostname,
        cert_sha256=digest(der) if der else None,
        cert_issuer=_name(parsed.get("issuer")),
        cert_subject=_name(parsed.get("subject")),
        cert_not_after=(
            datetime.fromtimestamp(ssl.cert_time_to_seconds(expires), timezone.utc).isoformat()
            if expires
            else None
        ),
        chain_verified=context.verify_mode != ssl.CERT_NONE,
        hostname_verified=context.check_hostname,
        defect=defect,
    )


def _notes(redirect: str | None, wire: Handshake | None) -> str | None:
    """The Receipt's free text: where the target pointed, and what was wrong.

    One column holds both because both are the same kind of statement -- a thing
    about this exchange an auditor reads rather than filters on -- and because a
    certificate defect must not be the reason a redirect stops being recorded.
    The verification failure is kept in the target's own words; which columns
    were left unverified is the queryable form of it, and this is the sentence
    that says why.
    """
    said = [note for note in (redirect, None if wire is None else wire.defect) if note]
    return "; ".join(said) or None


def transport(agent: Handshake | None, wire: Handshake | None) -> dict:
    """Both sides of an intercepted exchange, in the columns a Receipt holds.

    The gap is the product. What the agent's TLS stack negotiated is a fact
    about this door, what the door negotiated upstream is a fact about the
    target, and `receipts.transport_divergence` is generated from the two -- so
    an agent that concluded "the target speaks TLS 1.3 with a valid Let's
    Encrypt certificate" from what it saw is contradicted by the row rather than
    believed.

    Nothing at all when the upstream hop was not TLS: there is no target-side
    handshake to describe, and `receipts_agent_transport_records_both_sides`
    refuses a row that describes only the agent's -- which is exactly the shape
    a door that did not know it was lying would write.

    `agent_cert_*` stays null even though the door knows the leaf it presented.
    Recording it means naming the forging key under
    `receipts_intercepted_leaf_names_ca`, and nothing yet writes the
    `interception_cas` row that name would point at. A null column is "not
    recorded"; a leaf with no CA behind it would be an unattributable forging
    key, which `check_transport_claims` reports as a defect in its own right.
    """
    if wire is None:
        return {}
    facts = {
        "wire_tls_version": wire.tls_version,
        "wire_cipher": wire.cipher,
        "wire_alpn": wire.alpn,
        "wire_cert_sha256": wire.cert_sha256,
        "wire_cert_issuer": wire.cert_issuer,
        "wire_cert_subject": wire.cert_subject,
        "wire_cert_not_after": wire.cert_not_after,
        "wire_sni": wire.sni,
        "wire_chain_verified": wire.chain_verified,
        "wire_hostname_verified": wire.hostname_verified,
    }
    if agent is not None:
        facts |= {
            "agent_tls_version": agent.tls_version,
            "agent_cipher": agent.cipher,
            "agent_alpn": agent.alpn,
        }
    return facts


def connect(
    host: str,
    port: int,
    timeout: float,
    protocol: str,
    address: str,
    client_certificate: identity.ClientCertificate | None,
    *,
    anchor: str | None = None,
) -> tuple[http.client.HTTPConnection, Handshake | None]:
    """Open the connection to the address this request was pinned to.

    The socket is opened against `address` and never against `host`, and that is
    the pin: the name was resolved once, every address it answered with was
    checked, and this dials the one that was decided about. A second lookup here
    -- which is what handing the name to `http.client` would be -- is exactly the
    window a zone with a one-second TTL exists to use.

    The name is not thrown away, because two things still have to be true of it:
    the target has to be told which host it is being asked for, and an https
    certificate has to be checked against the name the policy authorised rather
    than against the address underneath it. So the connection keeps the name and
    the socket keeps the address, and `server_hostname` is the name.

    An https target is tried against the system trust store first, and this is
    the only place in the harness where a real certificate is seen at all. The
    agent is looking at this door's certificate by construction, so a claim
    about the target's -- issuer, expiry, name, chain -- can only be made on
    this side of the door. `intercepted` on the Receipt is what stops the
    agent's view from being read as the target's.

    A certificate that does not verify does not end the request. The targets
    this door exists to reach are targets under test, and an expired, a
    self-signed or a misnamed certificate is a finding about one of them rather
    than a reason to have no record of it: refusing here produced "target
    unreachable" and nothing else -- no status, no bytes, and no statement about
    the certificate that caused it. So the strict attempt is made, its words are
    kept, and the connection is dialled a second time with verification off.
    What makes that safe to have written is that it is written: the returned
    `Handshake` says the chain and the name were not checked, and
    `receipts.transport_citable` is generated from exactly those two columns, so
    a downgraded exchange can never be cited as a verified measurement of the
    target's transport.

    Only a verification failure is retried. Any other handshake error -- a
    protocol the target will not speak, a reset, a timeout -- is the target
    being unreachable, and dialling it again without verification would answer
    a question nobody asked.

    `anchor` replaces the system store, and only one caller passes one: the probe
    that measures an evaluation's fixture, with the authority the database holds
    for that one Program. It is a replacement rather than an addition, because a
    context carrying both would let a fixture's authority vouch for a public name
    and the system's roots vouch for a fixture -- and because the door has no
    business trusting the evaluator's authority for anything except the address
    the evaluator recorded. Everything else arrives here with no anchor and is
    verified exactly as it was.
    """
    if protocol != "https":
        raw = socket.create_connection((address, port), timeout=timeout)
        connection = http.client.HTTPConnection(host, port, timeout=timeout)
        connection.sock = raw
        return connection, None

    context = ssl.create_default_context(cadata=anchor)
    # Told to the target because it is true: everything above this speaks
    # HTTP/1.1 and nothing here can read a frame of anything else. Unset, the
    # two sides of an intercepted exchange disagreed about ALPN on every row --
    # the door offers `http/1.1` to the agent -- and a divergence that is on
    # every Receipt is one an auditor stops reading.
    context.set_alpn_protocols(["http/1.1"])
    if client_certificate is not None:
        client_certificate.install(context)
    try:
        return _dial(host, port, timeout, address, context, None)
    except ssl.SSLCertVerificationError as error:
        defect = str(error)
    # A second context rather than the first with its verification turned off:
    # `check_hostname` must be cleared before `verify_mode`, the order is easy
    # to get wrong, and a context that has been mutated mid-request is one the
    # next reader of `Handshake.chain_verified` cannot trust to describe the
    # socket it was read from.
    downgraded = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    downgraded.check_hostname = False
    downgraded.verify_mode = ssl.CERT_NONE
    downgraded.set_alpn_protocols(["http/1.1"])
    if client_certificate is not None:
        client_certificate.install(downgraded)
    return _dial(host, port, timeout, address, downgraded, defect)


def _dial(
    host: str,
    port: int,
    timeout: float,
    address: str,
    context: ssl.SSLContext,
    defect: str | None,
) -> tuple[http.client.HTTPConnection, Handshake | None]:
    """One TLS attempt against the pinned address, and what it negotiated."""
    raw = socket.create_connection((address, port), timeout=timeout)
    try:
        connection: http.client.HTTPConnection = http.client.HTTPSConnection(
            host, port, timeout=timeout, context=context
        )
        secured = context.wrap_socket(raw, server_hostname=host)
        connection.sock = secured
    except OSError:
        # The handshake is where this happens, and a target whose certificate
        # does not verify has already been given a socket. Closing it here is
        # what stops a refused exchange from holding a descriptor open until the
        # collector notices: nothing else refers to it, because the connection
        # object that would have owned it was never returned.
        raw.close()
        raise
    return connection, handshake(secured, defect)


def _pour(source: BinaryIO, sink: BinaryIO, wake: socket.socket) -> None:
    """Move one direction of a carried tunnel, and end the other when it stops.

    File objects on both sides rather than the sockets themselves, because the
    client's end has already been read from: `BaseHTTPRequestHandler` took the
    CONNECT line and its headers through `rfile`, and bytes a client sent behind
    them are sitting in that buffer. A relay reading the socket directly would
    leave them there and start the tunnel one record short.

    `wake` is the other direction's socket. A tunnel ends when either side hangs
    up, and the thread blocked on the side that did not is only released by
    shutting its socket down under it.
    """
    try:
        while True:
            block = source.read1(65536)
            if not block:
                break
            sink.write(block)
            sink.flush()
    except OSError:
        # Either end going away mid-copy is how a tunnel ends, not a fault to
        # report: the CONNECT was answered long ago and there is nobody left to
        # answer to.
        pass
    finally:
        try:
            wake.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass


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
        resolver: Resolver = resolve,
        timeout: float = TIMEOUT,
        authority: tls.Authority | None = None,
        root_secret: seal.Root | None = None,
    ):
        super().__init__(address, handler)
        self.fence = fence
        self.store = store
        self.connector = connector
        #: How a name becomes addresses. Separate from the connector because they
        #: happen at different moments and for different reasons: this one runs
        #: before anything is dialled, so that what is dialled has been decided.
        self.resolver = resolver
        self.target_timeout = timeout
        #: What a tunnel is answered with, or nothing -- in which case CONNECT is
        #: refused. Optional rather than required so that a door with no
        #: certificate material is a door that says no to tunnels, not a door
        #: that relays one it cannot read.
        self.authority = authority
        #: The installation root used only when a target response contains
        #: wire-only credential headers.  Without it those responses fail
        #: closed; ordinary one-view exchanges do not need key material.
        self.root_secret = root_secret
        #: Which targets this door has already taken a transport measurement of,
        #: as `(program, host, port)`. Here rather than in the database, and it
        #: is what bounds the cost: a measurement is a second handshake with the
        #: target, so one per target for as long as this door is up is the
        #: difference between measuring a target and hammering it. A door that
        #: restarts measures again, which is the honest reading of a set held in
        #: a process -- what it records is what this door saw.
        self.measured: set[tuple[str, str, int]] = set()
        #: And the lock over it. Every request is its own thread, so two requests
        #: to one target that arrive together would otherwise both measure it.
        self.measured_lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    """One request: take the control headers, ask, forward, record, answer."""

    protocol_version = "HTTP/1.1"
    server_version = "redkraken"
    sys_version = ""

    #: The target this connection was opened towards, once a CONNECT has been
    #: answered and the socket is this door's TLS rather than the client's. Set
    #: on the instance that serves the requests inside the tunnel, so everything
    #: below can ask "which hop am I on" without a second code path.
    tunnel: tuple[str, int] | None = None
    tunnel_control: Control = Control(None, None)

    #: Whether a socket towards the target has been opened for the request being
    #: served now. Reset per request rather than per connection, because one
    #: handler serves every request inside a tunnel and a flag carried over from
    #: the last one would charge a Program for an exchange it never had. Set at
    #: the one line that dials, so it means what it says.
    contacted: bool = False

    #: What the socket towards the target negotiated, for the request being
    #: served now. Null on a plain http target and until the dial, and reset with
    #: `contacted` for the same reason: one handler serves every request inside a
    #: tunnel, and a handshake carried over would put one target's certificate on
    #: another target's Receipt.
    wire: Handshake | None = None

    #: The authority a measurement of this request's target is verified against,
    #: when the target is an evaluation's fixture and the database handed one
    #: over. Reset per request with the two above and for their reason: an anchor
    #: carried over would be this door offering one fixture's authority for
    #: another target's handshake.
    anchor: str | None = None

    #: The budget slot this request holds, and the Program it was taken under.
    #: On the instance rather than passed down, because what gives it back is not
    #: the code that took it: the exchange releases it the moment the socket is
    #: closed, and `_serve` releases whatever is left on every other way out.
    slot: str | None = None
    slot_program: str | None = None

    def _serve(self) -> None:
        """Decide one request, and answer even when the session is gone.

        `pg.ConnectionError_` is a sibling of `pg.DatabaseError` and not a
        subclass of it, so every typed guard under this one -- the binds, the
        reads, the receipt writes -- lets a lost session past. Uncaught it
        reaches `socketserver`, which prints a traceback and drops the socket:
        no answer, no row, and a caller that cannot tell a door that stopped
        deciding from a target that stopped answering. Caught here it is one
        502 carrying the token that says which, and the log line `log_error`
        exists for -- the record could not be written, so this is said out loud.
        """
        try:
            self._decide()
        except pg.ConnectionError_ as error:
            self.log_error("no session for %s: %s", self.path, error)
            self._answer(502, UNAVAILABLE, body=b"")

    def _decide(self) -> None:
        arrival = datetime.now(timezone.utc)
        control = take_control(self.headers)
        if self.tunnel is not None:
            # The take still ran, so whatever this request carried is out of the
            # message either way. What it said is merged with what the CONNECT
            # said, because ordinary clients split the two across the hops.
            control = merge_control(self.tunnel_control, control)
        url = self._url()
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
            said = TWO_HOPS if self.tunnel is not None else TWO_HEADERS
            return self._refuse(
                program_id,
                None,
                Refused("ambiguous control headers", said),
                arrival,
                url=url,
                decision=AMBIGUOUS,
                # Said out loud to the caller, unlike every other detail this
                # method sends: it is this module's own prose about the caller's
                # own headers, and the two ways to be ambiguous need different
                # fixes from whoever sent them.
                detail=said,
            )

        self.contacted = False
        self.wire = None
        self.anchor = None
        self.slot = None
        self.slot_program = program_id
        try:
            request = self._request(url)
            if control.capability is None:
                raise Refused("capability refused", "no capability was offered")
            # Read before the decision rather than after it, because the
            # decision now depends on it: ticket 96 binds a body to the Tool run
            # the way the method has always been bound, and "does this request
            # have bytes after its headers" is not a question that can be
            # answered from the headers alone once a chunked one is refused
            # here. What moves with it is only the order of two refusals a
            # caller can earn at once -- a chunked body offered with a dead
            # capability is now recorded as the framing it is.
            body = self._body()
            authorization = self.server.fence.authorize(
                program_id, control.capability, self.command, request, bool(body)
            )
            slot = self.server.fence.reserve(program_id, control.capability, request)
        except Refused as refusal:
            return self._refuse(program_id, control.capability, refusal, arrival, url=url)

        if not slot.granted:
            # A limit, not a verdict about this request. It is filed with the
            # authorization it earned, so that the row says what the request was
            # allowed as and then says it was not sent anyway -- an auditor
            # reading a Program that stopped working needs to tell "out of scope"
            # from "out of budget", and those are the same shape without it.
            return self._refuse(
                program_id,
                control.capability,
                Refused(slot.reason, slot.reason, retry_at=slot.retry_at),
                arrival,
                url=url,
                authorization=authorization,
                decision=BUDGETED,
                detail=slot.reason,
            )

        self.slot = slot.id
        try:
            try:
                authorization, addresses = self._pin(
                    authorization, control.capability, request
                )
            except Refused as refusal:
                # Its own block, because by here there is an `authorization` and
                # the record has to say so. A request refused for its address was
                # in scope by name and spent a live capability to get that far,
                # and a Receipt that filed it as `denied` alongside the ones that
                # never resolved anything would hide exactly the case worth
                # seeing: a name the policy allows, pointing somewhere the policy
                # does not.
                return self._refuse(
                    program_id,
                    control.capability,
                    refusal,
                    arrival,
                    url=url,
                    authorization=authorization,
                )

            self._forward(
                authorization, control.capability, request, body, arrival, url, addresses
            )
        finally:
            # Whatever the exchange did not already give back. Every way out of
            # the block above ends here, including the refusal that returns from
            # inside it, and a slot released as uncontacted is refunded -- so a
            # request that took budget and then failed to resolve a name does not
            # count against a Program that never reached anything.
            self._release()

    do_GET = _serve
    do_HEAD = _serve
    do_POST = _serve
    do_PUT = _serve
    do_PATCH = _serve
    do_DELETE = _serve
    do_OPTIONS = _serve

    def do_CONNECT(self) -> None:
        """Answer the tunnel, and then be the other end of it.

        The alternative -- relaying the bytes to the target unread -- is the one
        thing section 7 does not allow: it is egress, it is unrecorded, and the
        Receipt that would name it could say nothing about what crossed. So the
        door terminates the TLS itself. Nothing is forwarded here at all; a
        socket towards the target is opened later, by the request inside, and
        only after the database has authorized that request.

        `CONTROL_PLANE` is the one exception, and it is not a target: it is the
        session this runtime opened for the child to think in, carried by
        `_relay` and never read. Taken before the authority is asked for,
        because a door with no certificate material can still carry one.

        No Receipt is written for the CONNECT, and that is not the hole `_serve`
        closes. A CONNECT is not an exchange -- no bytes reach a target because
        of one -- and the row it could write would name a request nobody has
        made yet. The requests inside are each recorded, refused ones included.

        What is refused here is only what makes a tunnel impossible: control
        headers that mean two things, no authority to sign with, and an
        authority-form that is not one. Scope is not consulted, because the
        question a CONNECT asks -- "may I speak to this host at all" -- is
        answered by refusing every request inside it, and answering it earlier
        would tell a caller which hosts are in scope without spending anything.
        """
        control = take_control(self.headers)
        if control.ambiguous:
            return self._answer(407, AMBIGUOUS, detail=TWO_HEADERS, body=b"")
        try:
            host, port = _hostport(self.path)
        except Refused as refusal:
            return self._answer(refusal.status, TUNNEL, detail=refusal.detail, body=b"")
        if (host, port) in CONTROL_PLANE:
            return self._relay(host, port)
        authority = self.server.authority
        if authority is None:
            return self._answer(405, TUNNEL, detail=NO_AUTHORITY, body=b"")
        try:
            context = authority.context(host)
        except Refused as refusal:
            return self._answer(refusal.status, TUNNEL, detail=refusal.detail, body=b"")
        except tls.Unusable as error:
            return self._answer(400, TUNNEL, detail=str(error), body=b"")

        self.send_response_only(200, ESTABLISHED)
        self.end_headers()
        self.wfile.flush()

        self.connection.settimeout(self.server.target_timeout)
        try:
            secured = context.wrap_socket(self.connection, server_side=True)
        except (OSError, ValueError) as error:
            # A client that will not complete the handshake has been answered
            # already and there is nothing further to say to it: the only place
            # a message could go is a TLS session that does not exist.
            self.log_error("no tunnel to %s: %s", self.path, error)
            self.close_connection = True
            return
        # `wrap_socket` detaches the socket underneath, so from here the plain
        # one is a dead file descriptor and every read and write in this handler
        # has to be the TLS one -- including the ones `finish` makes.
        self.connection = secured
        self.rfile = secured.makefile("rb", self.rbufsize)
        self.wfile = secured.makefile("wb")
        self.tunnel = (host, port)
        self.tunnel_control = control
        self.close_connection = False
        try:
            while not self.close_connection:
                self.handle_one_request()
        except OSError as error:
            # `log_message` and not `log_error`: a client that hangs up mid-tunnel
            # is the ordinary end of a connection and leaves no gap in the record,
            # which is the one thing stderr here is for.
            self.log_message("tunnel to %s ended: %s", self.path, error)
            self.close_connection = True
        finally:
            # `shutdown_request` will close the socket this handler was given,
            # and that is no longer the one holding the descriptor: `wrap_socket`
            # detached it. Nothing else refers to the TLS socket, so a door that
            # left it to the collector would leak a descriptor per tunnel.
            try:
                self.wfile.flush()
            except OSError:
                pass
            secured.close()

    def _relay(self, host: str, port: int) -> None:
        """Carry one control-plane tunnel to its end without reading it.

        The narrower of the two ways to let a child reach its own model.
        Terminating this tunnel the way every other one is terminated would put
        the operator's subscription credential through this process in the clear
        on every turn a child takes -- the door would hold the one credential it
        exists to stop a child spending elsewhere. So the bytes are relayed, and
        this door knows what the CONNECT already told it and nothing more: which
        name, and that a session was open.

        `destination` still decides what may be dialled, so a control-plane name
        answering with a private address is refused here exactly as a target's
        would be. What is not asked is the database: there is no Program, no
        capability and no Receipt, which is the whole difference between this
        and an exchange.

        No timeout on either socket. A model session is idle between turns for
        as long as the child is thinking, and a fence that timed that out would
        end the run it exists to carry.
        """
        try:
            addresses = destination(host, port, self.server.resolver)
        except Refused as refusal:
            return self._answer(refusal.status, TUNNEL, detail=refusal.detail, body=b"")
        try:
            upstream = socket.create_connection(
                (addresses[0], port), timeout=self.server.target_timeout
            )
        except OSError as error:
            self.log_error("no %s tunnel to %s: %s", CARRIED, self.path, error)
            return self._answer(502, UNAVAILABLE, body=b"")

        self.close_connection = True
        self.send_response_only(200, ESTABLISHED)
        self.end_headers()
        self.wfile.flush()
        self.log_message("carried %s to %s unread", CARRIED, self.path)
        upstream.settimeout(None)
        self.connection.settimeout(None)
        outward = threading.Thread(
            target=_pour,
            args=(self.rfile, upstream.makefile("wb"), upstream),
            daemon=True,
        )
        outward.start()
        try:
            _pour(upstream.makefile("rb"), self.wfile, self.connection)
        finally:
            outward.join(timeout=self.server.target_timeout)
            upstream.close()

    def _url(self) -> str:
        """The absolute URL this request is about, whichever hop it arrived on.

        Inside a tunnel the client sends an origin-form path and the host is the
        one the CONNECT named -- not the `Host` header, which is the client's to
        write and is not what this door issued a certificate for. Everything
        downstream reads this one string, so the scope decision, the Receipt and
        the certificate all describe the same target or none of them do.
        """
        if self.tunnel is None:
            return self.path
        host, port = self.tunnel
        return f"https://{_authority(host, port, 'https')}{self.path}"

    def _request(self, url: str) -> scope.Request:
        """The request line, canonicalised, or a refusal that never leaves."""
        if self.tunnel is not None and not self.path.startswith("/"):
            # Absolute form inside a tunnel would name a second target while the
            # certificate on this socket names the first. There is no answer to
            # give that is true of both.
            raise Refused(
                "not a proxy request",
                f"{self.requestline} is not an origin form request",
                status=400,
            )
        if not url.lower().startswith(("http://", "https://")):
            # Origin form means "you are the origin server". This fence has no
            # resource to serve, and answering one would be an unauthenticated
            # surface on the process holding every capability in flight.
            raise Refused(
                "not a proxy request",
                f"{self.requestline} is not an absolute form URL",
                status=400,
            )
        try:
            return scope.canonical_request(url)
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

    def _pin(
        self, authorization: Authorization, capability: str, request: scope.Request
    ) -> tuple[Authorization, tuple[str, ...]]:
        """Turn the authorized name into the address that will be dialled.

        A synthetic target first, because it is the one destination whose address
        is not a property of the name. `rk playbook evaluate` serves a fixture on
        one of this machine's own private addresses and records where it put it;
        the name it is scoped under -- `<fixture>.localhost` -- resolves to
        loopback, which the two steps below would refuse, correctly. So the
        database is asked for the endpoint before anything is looked up, and
        when there is one the request is dialled at it and nothing is resolved.
        The class comes back with the address, and the authorization carries it
        onward, so the Receipt says the request was allowed as a fixture and pins
        the address a socket was actually opened to. Everything else in the door
        is unchanged: a Program with no endpoint takes the three steps below, and
        no configuration file can produce one.

        Three steps in one order, and the order is the point. The name is
        resolved -- which happens here and not earlier, because a lookup is a
        packet leaving this machine carrying the name that was asked for, and one
        made for a request that was about to be refused would be egress no
        Receipt could name. Every address it answered with is checked for being
        one the public internet routes to, which is where loopback, the
        operator's own networks, the metadata endpoint and this machine's own
        control ports stop being reachable through a name. And the address that
        will be dialled is put back to the database as a destination in its own
        right, so a Program that withdrew a network has withdrawn it however the
        request spelled its way there.

        What comes back from those three steps is every address, not the one
        that was chosen. The Receipt names them all: an auditor asking why a name
        was refused needs to see what it answered with, and an auditor reading an
        allowed exchange needs to see that the other answers were checked too.
        Only the first is put to the policy, because only the first is dialled --
        the rest are held to being routable and to being recorded, and a Program
        that withdrew one of them has withdrawn a machine this request never
        contacted. The fixture branch above comes back with one address because
        one is all there was: nothing was resolved, so there are no other answers
        to hold to anything.
        """
        fixture = self.server.fence.fixture_address(
            authorization.program_id, capability, request
        )
        if fixture is not None:
            # Kept for the probe and for nothing else. The exchange below is the
            # agent's, and the agent's view of this fixture stays what it is: a
            # leaf this door forged, on a chain the agent cannot check.
            self.anchor = fixture.trust_anchor
            return (
                replace(authorization, scope_class=fixture.scope_class),
                (fixture.address,),
            )

        addresses = destination(request.host, request.port, self.server.resolver)
        self.server.fence.authorize_address(
            authorization.program_id, capability, request, addresses[0]
        )
        return authorization, addresses

    def _exchange(
        self,
        request: scope.Request,
        addresses: tuple[str, ...],
        target: str,
        headers: list[tuple[str, str]],
        body: bytes,
        client_certificate: identity.ClientCertificate | None,
    ) -> tuple[int, str, list[tuple[str, str]], bytes]:
        """Contact the authorized target and read what it answered, or refuse.

        Every refusal from here is one that happened after the socket was opened,
        which is why they are raised together: the caller of this method knows the
        request left the machine and records that on all of them.

        The whole answer set comes in and the first of it is dialled, so that a
        target that never came back is recorded with the same addresses an
        exchange that did would have named. A row saying one address for a failed
        connection and four for a successful one would read as two different
        facts about the same lookup.
        """
        address = addresses[0]
        # Immediately before the dial and not after it: a connection that was
        # opened and then failed is still a request this Program made of that
        # target, and a Program whose budget only counted the exchanges that
        # succeeded could hammer a target that never answers for free.
        self.contacted = True
        try:
            connection, self.wire = self.server.connector(
                request.host,
                request.port,
                self.server.target_timeout,
                request.protocol,
                address,
                client_certificate,
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
        except identity.Invalid as error:
            raise Refused("identity slot refused", str(error), pinned=addresses) from error
        except (OSError, http.client.HTTPException) as error:
            raise Refused("target unreachable", str(error), pinned=addresses) from error
        finally:
            # Here rather than after the record is written, because the slot
            # limits how many requests are at a target at once and this one is no
            # longer at it. Holding it through the Receipt, the artifact store and
            # the answer would make a Program's concurrency a limit on how fast
            # this process writes rows, which is not a fact about the target.
            self._release()
        if len(returned) > CEILING:
            raise Refused(
                "response too large",
                f"the target answered with over {CEILING} bytes",
                target_status=status,
            )
        return status, reason, back, returned

    def _release(self) -> None:
        """Give this request's budget slot back, at most once, and never fail on it.

        Taken out of the field first, so the second caller has nothing to give
        back: two paths release -- the exchange when the socket closes, `_serve`
        for every way out that never got there -- and neither knows whether the
        other ran.

        A release that cannot be written is logged rather than raised. The
        request it belongs to has already been decided, and turning a bookkeeping
        failure into the caller's answer would replace a served exchange with an
        error about a row. What it costs instead is one slot held until the
        reservation lapses, which refuses requests rather than admitting them.
        """
        slot, self.slot = self.slot, None
        if slot is None or self.slot_program is None:
            return
        try:
            self.server.fence.release(self.slot_program, slot, self.contacted)
        except (pg.DatabaseError, pg.ConnectionError_, OSError) as error:
            self.log_error("no release for %s: %s", slot, error)

    def _measure(
        self,
        authorization: Authorization,
        capability: str,
        request: scope.Request,
        addresses: tuple[str, ...],
    ) -> None:
        """Take this door's own handshake with the target, once, and file it.

        Ticket 93. Everything above this method describes an exchange the agent
        asked for, and every TLS fact on that row is doubled for the reason 025
        records: the agent's side is the door's certificate, and the door's side
        is on a socket carrying somebody else's request. This is the other kind
        of connection -- opened by this process, for this process, with nothing
        downstream -- and it is the only kind `receipts.transport_citable` will
        ever be true of.

        The order is the order of the request that triggered it, and that is what
        makes it the same lane rather than a second one. The scope decision has
        already been made and is not made again: this dials the address that
        decision pinned, for the Program it was made for, and refuses to run at
        all for a class a measurement may not be filed under. What it does ask
        for again is budget, because a handshake is egress: it takes its own slot
        from the same per-target concurrency and the same token bucket the
        exchange took one from, and a Program with none left is not measured now.

        Nothing here may change what the caller was told. It runs after the
        answer has been written, every failure is logged and swallowed, and a
        target that could not be measured gives its claim back so that a later
        request tries again -- an exchange that was served stays served whether
        or not the door also managed to measure the target it served from.
        """
        if request.protocol != "https" or self.server.fence is None:
            return
        # The two classes 025's shape constraint admits. An `egress_support` host
        # is somewhere the harness talks to on its own business rather than a
        # target under test, and a measurement of one would be a claim nobody
        # asked for filed against a Program's budget.
        if authorization.scope_class not in ("target", "fixture"):
            return

        target = (authorization.program_id, request.host, request.port)
        with self.server.measured_lock:
            if target in self.server.measured:
                return
            self.server.measured.add(target)

        address = addresses[0]
        slot: Reservation | None = None
        filed = False
        try:
            slot = self.server.fence.reserve(authorization.program_id, capability, request)
            if not slot.granted:
                return
            arrival = datetime.now(timezone.utc)
            connection, wire = self.server.connector(
                request.host,
                request.port,
                self.server.target_timeout,
                request.protocol,
                address,
                # No Identity. A measurement is about what the target's transport
                # is, which it is before anybody authenticates, and offering a
                # leased credential to open a socket nobody sends a request on
                # would spend an Identity on a question it cannot answer.
                None,
                anchor=self.anchor,
            )
            connection.close()
            if wire is None:
                return
            self.server.fence.measurement(
                authorization.program_id,
                capability,
                {
                    "reason": f"transport measured as {authorization.scope_class}"
                    f" under scope version {authorization.scope_version}",
                    "scheme": request.protocol,
                    "host": request.host,
                    "port": request.port,
                    "pinned_ips": pinned_ips((address,)),
                    "ts_arrival": arrival.isoformat(),
                    "ts_egress": datetime.now(timezone.utc).isoformat(),
                    "scope_class": authorization.scope_class,
                    "notes": _notes(None, wire),
                    # The wire side alone, which is the whole of what this row
                    # is: `transport` writes no agent columns when there is no
                    # agent handshake, and there was none.
                    **transport(None, wire),
                },
            )
            filed = True
        except (
            Refused,
            OSError,
            http.client.HTTPException,
            pg.DatabaseError,
            pg.ConnectionError_,
        ) as error:
            self.log_error("no measurement for %s:%s: %s", request.host, request.port, error)
        finally:
            if not filed:
                with self.server.measured_lock:
                    self.server.measured.discard(target)
            if slot is not None and slot.granted and slot.id is not None:
                try:
                    self.server.fence.release(authorization.program_id, slot.id, True)
                except (pg.DatabaseError, pg.ConnectionError_, OSError) as error:
                    self.log_error("no release for measurement %s: %s", slot.id, error)

    def _forward(
        self,
        authorization: Authorization,
        capability: str,
        request: scope.Request,
        body: bytes,
        arrival: datetime,
        url: str,
        addresses: tuple[str, ...],
    ) -> None:
        """Send the authorized request, record the exchange, answer the caller."""
        authority = _authority(request.host, request.port, request.protocol)
        agent_headers = [("Host", authority), *forwardable(self.headers)]
        if body:
            agent_headers.append(("Content-Length", str(len(body))))
        if not any(name.lower() == "accept-encoding" for name, _ in agent_headers):
            # `http.client` adds this one when the caller does not, and a
            # transcript that omitted it would be a hash of bytes that differ
            # from the ones the socket carried.
            agent_headers.append(("Accept-Encoding", "identity"))
        target = origin_form(url)
        line = f"{self.command} {target} HTTP/1.1"

        root = self.server.root_secret
        binding: IdentityBinding | None = None
        client_certificate: identity.ClientCertificate | None = None
        client_certificate_sha: str | None = None
        wire_headers = list(agent_headers)
        if authorization.identity_entity_id is not None:
            if root is None:
                return self._refuse(
                    authorization.program_id,
                    capability,
                    Refused(
                        "identity slot refused",
                        "an authenticated exchange needs the proxy artifact key",
                        status=502,
                    ),
                    arrival,
                    url=url,
                    authorization=authorization,
                )
            try:
                binding = self.server.fence.open_identity(
                    authorization.program_id,
                    capability,
                    authorization.identity_entity_id,
                    authorization.identity_label or "",
                    root,
                )
            except (identity.Invalid, seal.Tampered, seal.Unusable) as error:
                return self._refuse(
                    authorization.program_id,
                    capability,
                    Refused("identity slot refused", str(error), status=502),
                    arrival,
                    url=url,
                    authorization=authorization,
                )
            except Refused as refusal:
                return self._refuse(
                    authorization.program_id,
                    capability,
                    refusal,
                    arrival,
                    url=url,
                    authorization=authorization,
                )
            wire_headers = binding.session.inject(url, agent_headers)
            client_certificate = binding.session.client_certificate(url)
            try:
                client_certificate_sha = (
                    client_certificate.public_sha256()
                    if client_certificate is not None
                    else None
                )
            except identity.Invalid as error:
                return self._refuse(
                    authorization.program_id,
                    capability,
                    Refused("identity slot refused", str(error), status=502),
                    arrival,
                    url=url,
                    authorization=authorization,
                )

        # What the Program requires on every request. Fetched after the Identity
        # rather than before it because the Identity is the narrower claim: it
        # belongs to this capability and this Tool run, so when both are broken
        # the refusal an operator gets back is the one that names the smaller
        # thing. The ordinary case -- a policy that requires no header -- costs
        # one query and leaves no audit row.
        try:
            required = self.server.fence.required_headers(
                authorization.program_id, capability, root
            )
        except (seal.Tampered, seal.Unusable) as error:
            return self._refuse(
                authorization.program_id,
                capability,
                Refused("required header refused", str(error), status=502),
                arrival,
                url=url,
                authorization=authorization,
                decision=HEADERLESS,
            )
        except Refused as refusal:
            return self._refuse(
                authorization.program_id,
                capability,
                refusal,
                arrival,
                url=url,
                authorization=authorization,
                decision=HEADERLESS,
                detail=refusal.detail if refusal.reason == HEADER_MISSING else None,
            )

        # Applied last, and over the Identity, because the Program's requirement
        # is the stronger claim: an Identity that carried a header of the same
        # name would be one credential document deciding how its Program
        # identifies itself to a target. It goes onto the wire view alone, so the
        # Agent's own record of its request does not contain a value the Agent
        # may not have -- and the two views then differ, which puts the sealed
        # wire artifact and its `target_request` transformation on the record as
        # the proof of exactly what the door added.
        wire_headers = with_required(wire_headers, required)

        egress = datetime.now(timezone.utc)
        try:
            status, reason, back, returned = self._exchange(
                request,
                addresses,
                target,
                wire_headers,
                body,
                client_certificate,
            )
        except Refused as refusal:
            return self._refuse(
                authorization.program_id,
                capability,
                refusal,
                arrival,
                url=url,
                authorization=authorization,
                egress=egress,
            )

        # Ticket 96's third rule. The two views of the request were built from
        # one header list and one body while the only injected material was
        # headers, which was correct exactly as long as an Agent had no way to
        # put bytes in front of a parser. It has one now, so the Agent's view of
        # its own request is scrubbed against the same values the response is
        # scrubbed against, and the wire view stays the bytes that went.
        agent_body = body
        if binding is not None:
            agent_headers, agent_body = project_identity_request(
                agent_headers, body, binding.session.secrets(url)
            )
        sent = transcript(line, agent_headers, agent_body)
        wire_sent = transcript(line, wire_headers, body)
        wire_received = transcript(f"HTTP/1.1 {status} {reason}", back, returned)
        store = self.server.store
        if binding is not None:
            binding.changed = binding.session.capture(url, back)
            if self.server.fence.reads(
                authorization.program_id, capability, digest(wire_received)
            ):
                # This Program already holds an agent-visible reference to these
                # exact bytes, so some earlier exchange of its own obtained them
                # without this Identity's credential and nothing in them can be a
                # reflection of it. Withholding them would withhold nothing --
                # the Agent can read them under the hash it already holds -- and
                # would seal, for a Program, a ciphertext of that Program's own
                # plaintext.
                #
                # Asked of the database and not of the store. The store is a
                # plain content-addressed heap that five other modules also
                # write, so a hit in it proves the bytes are on disk and not that
                # this Agent may read them: bytes filed by another Program, or by
                # the legacy import, answered "the Agent already has these" about
                # an Agent that had nothing. `artifact_references` is where
                # reading is decided, and it is what is asked.
                #
                # `response_for_agent` is still applied, and is a no-op whenever
                # the hit is what the comment above assumes: the unbound path
                # files the projected view, so bytes filed by it are already
                # projected and projecting them twice changes nothing.
                agent_back, agent_returned, agent_reason = (
                    response_for_agent(back),
                    returned,
                    reason,
                )
            else:
                agent_back, agent_returned = project_identity_response(
                    back, returned, binding.session.secrets(url)
                )
                agent_reason = ""
        else:
            agent_back, agent_returned = response_for_agent(back), returned
            agent_reason = reason
        received = transcript(f"HTTP/1.1 {status} {agent_reason}", agent_back, agent_returned)
        try:
            # The newness flag is dropped on purpose. It says this process
            # wrote the file, which is not the question a rollback asks: the
            # store is content-addressed and global, so between this `put` and
            # the refusal below another Program can have `put` the same
            # plaintext, been told it was already filed, and committed a
            # reference to it. Deleting it then would empty a row somebody else
            # holds. `Store.discard` says so itself -- safe for a ciphertext,
            # whose nonce makes its hash unreachable to anyone else, and false
            # of plaintext. Plaintext nobody ends up referencing is retention's
            # to collect -- `artifacts_due_for_purge` is the view that refcounts
            # it across Programs, and no command runs one yet. Bytes left in the
            # store are a bounded cost; bytes deleted out from under another
            # Program's committed reference are evidence loss.
            request_sha, _ = store.put(sent)
            response_sha, _ = store.put(received)
        except (Corrupt, OSError) as error:
            # The exchange happened and its bytes cannot be filed. Answered as a
            # refusal rather than allowed to escape, for the reason every other
            # failure in this method is: the caller must not read a 200 for an
            # exchange nothing recorded, and a `Corrupt` here says another file
            # already under one of these hashes is damaged -- which is a fact
            # about this machine that belongs on a Receipt and in the log, not
            # in a traceback nobody catches.
            return self._refuse(
                authorization.program_id,
                capability,
                Refused("artifact store refused", str(error), status=502,
                        target_status=status),
                arrival,
                url=url,
                authorization=authorization,
                egress=egress,
            )

        seals: list[dict] = []
        ciphertext_new: set[str] = set()
        # Whether a direction was transformed is a question about the bytes: the
        # Agent view and the wire view either differ or they do not. What gets
        # sealed is the exchange's own document, because a hash that another
        # exchange could arrive at is a classification two exchanges have to
        # share, and they cannot.
        exchange = f"{arrival.isoformat()} {self.command} {url}"
        transformations = [
            (bound, agent_sha, field)
            for raw, agent, bound, agent_sha, field in (
                (
                    wire_sent,
                    sent,
                    wire_view(line, wire_headers, body, exchange=exchange),
                    request_sha,
                    "target_request",
                ),
                (
                    wire_received,
                    received,
                    wire_view(
                        f"HTTP/1.1 {status} {reason}", back, returned, exchange=exchange
                    ),
                    response_sha,
                    "target_response",
                ),
            )
            if raw != agent
        ]
        if transformations:
            root = self.server.root_secret
            if root is None:
                return self._refuse(
                    authorization.program_id,
                    capability,
                    Refused(
                        "wire response refused",
                        "the exchange carried authentication material but the door has no artifact key",
                        status=502,
                        target_status=status,
                    ),
                    arrival,
                    url=url,
                    authorization=authorization,
                    egress=egress,
                )
            try:
                generation, key = self.server.fence.wire_key(
                    authorization.program_id, capability, root
                )
            except Refused as refusal:
                refusal.target_status = status
                return self._refuse(
                    authorization.program_id,
                    capability,
                    refusal,
                    arrival,
                    url=url,
                    authorization=authorization,
                    egress=egress,
                )

            for wire, agent_sha, field_name in transformations:
                wire_sha = digest(wire)
                encrypted = seal.seal(
                    key,
                    wire,
                    aad=seal.associated_data(
                        program_id=authorization.program_id,
                        sha256=wire_sha,
                        generation=generation,
                    ),
                )
                envelope = encrypted.encode()
                try:
                    ciphertext_sha, is_new = store.put(envelope)
                except (Corrupt, OSError) as error:
                    for written in ciphertext_new:
                        store.discard(written)
                    return self._refuse(
                        authorization.program_id,
                        capability,
                        Refused("wire response refused", str(error), status=502,
                                target_status=status),
                        arrival,
                        url=url,
                        authorization=authorization,
                        egress=egress,
                    )
                if is_new:
                    ciphertext_new.add(ciphertext_sha)
                seals.append(
                    {
                        "sha256": wire_sha,
                        "byte_size": len(wire),
                        "content_type": TRANSCRIPT,
                        "alg": encrypted.alg,
                        "nonce_hex": encrypted.nonce.hex(),
                        "kek_gen": generation,
                        "ciphertext_sha256": ciphertext_sha,
                        "agent_sha256": agent_sha,
                        "value_fpr_hex": root.fingerprint(wire).hex(),
                        "field": field_name,
                    }
                )

        # Where the target pointed, when it pointed anywhere. The door does not
        # follow it and must not: following would be an exchange the client never
        # asked for, made against a target the client never named, and the whole
        # of §7's subresource rule is that each exchange earns its own verdict.
        # The client follows, and comes back through this fence, where the new
        # URL is canonicalised and decided on its own. What the record owes is
        # the link between the two -- without it the child Receipt names a URL
        # nobody asked for, and an auditor cannot tell a followed redirect from
        # an agent that invented a target for itself.
        #
        # Read off the Agent view rather than off `back`, because an Identity was
        # possibly bound and a redirect target reflects a credential as readily
        # as any other target-controlled field. `project_identity_response`
        # drops a `Location` carrying one, so such an exchange records no link
        # and an auditor reading it sees an unlinked child rather than a link
        # that leaked -- and a Receipt is read by more roles than the Agent view
        # is. Reading `back` here would put those bytes back on the record they
        # were kept off.
        onward = (
            redirected(url, _header(agent_back, "Location")) if status in REDIRECTS else None
        )

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
            "query_sha256": query_sha256(url),
            "status_code": status,
            # Ticket 186. The media type the target declared for what it sent
            # back. Read off the Agent view for the reason `onward` is, and
            # recorded because the door is the only party that ever sees it: the
            # Artifact behind this Receipt is the whole message and is filed as
            # `message/http`, so without this column nothing downstream can tell
            # a bundle from a page -- which is what decides whether these bytes
            # are application source this Program fetched.
            "response_content_type": _media(_header(agent_back, "Content-Type")),
            "ts_arrival": arrival.isoformat(),
            "ts_egress": egress.isoformat(),
            "waited_ms": int((datetime.now(timezone.utc) - egress).total_seconds() * 1000),
            "request_agent_sha": request_sha,
            "request_wire_sha": next(
                (item["sha256"] for item in seals if item["field"] == "target_request"), None
            ),
            "response_agent_sha": response_sha,
            "response_wire_sha": next(
                (item["sha256"] for item in seals if item["field"] == "target_response"), None
            ),
            "identity_entity_id": authorization.identity_entity_id,
            "identity_tls_cert_sha256": client_certificate_sha,
            "scope_class": authorization.scope_class,
            "intercepted": True,
            # Every address the name answered with, and the one that was dialled
            # is the first. All of them, because every one of them had to be an
            # address the public internet routes to for this request to be here
            # at all, and a record naming only the one that was used could not be
            # read back as evidence that the rest were looked at. What the policy
            # was asked about is the first alone -- the one a socket was opened
            # to -- so this column is the lookup's answer and not the verdict's.
            "pinned_ips": pinned_ips(addresses),
            "notes": _notes(f"redirect to {onward}" if onward else None, self.wire),
            # Both sides of the handshake, or neither. The agent's is read off
            # the socket this request arrived on, which inside a tunnel is the
            # door's own TLS -- so the row carries what the agent was shown next
            # to what the target actually presented.
            **transport(handshake(self.connection), self.wire),
        }
        artifacts = [
            {"sha256": request_sha, "byte_size": len(sent), "content_type": TRANSCRIPT},
            {"sha256": response_sha, "byte_size": len(received), "content_type": TRANSCRIPT},
        ]
        try:
            written = self.server.fence.allowed_receipt(
                authorization.program_id,
                capability,
                receipt,
                artifacts,
                seals,
                binding,
            )
        except Refused as refusal:
            # The bytes are spent: the target has answered and cannot be asked to
            # forget. Two things follow from that, and only one of them was here
            # before. The caller must not read a 200 for an exchange with no
            # Receipt behind it -- and the exchange must not vanish either, so the
            # record that can still be written is written: a blocked Receipt
            # naming the target, the status it answered with and the moment of
            # egress. It cannot name the transcripts, because registering them is
            # precisely what failed, and the envelopes this exchange sealed are
            # discarded rather than left in the store for nobody -- those and
            # nothing else, for the reason the `put` above gives.
            for sha256 in ciphertext_new:
                store.discard(sha256)
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
                url=url,
                authorization=authorization,
                egress=egress,
                decision=RECEIPT_REFUSED,
            )

        label = str(written.get("label") or written.get("receipt_id") or "")
        self._answer(
            status,
            None,
            body=agent_returned,
            headers=agent_back,
            receipt=label,
            reason=agent_reason,
            scope_class=authorization.scope_class,
        )
        # After the answer, deliberately. The measurement is a second handshake
        # with the same target, and making the caller wait for it would put the
        # cost of an audit record on the latency of every exchange with a target
        # this door has not met before.
        self._measure(authorization, capability, request, addresses)

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
        detail: str | None = None,
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
        if authorization is not None:
            # The run this attempt was authorised under, said here rather than
            # resolved from the capability again. A capability resolves only
            # while its run is open, and a connect towards a host that never
            # answers takes as long as the timeout allows -- so a run whose
            # last request met a dead target closes while that request is still
            # on the wire, and by the time the refusal is written the capability
            # names nothing. Written from the authorization, the row keeps the
            # run it really belongs to instead of reading as egress nobody
            # asked for. It is only ever the door saying what it already
            # decided: the agent cannot reach this field.
            receipt["tool_run_id"] = authorization.tool_run_id
        if egress is not None:
            receipt["ts_egress"] = egress.isoformat()
            receipt["waited_ms"] = int(
                (datetime.now(timezone.utc) - egress).total_seconds() * 1000
            )
        if refusal.target_status is not None:
            receipt["status_code"] = refusal.target_status
        if refusal.pinned:
            # Only on the refusals that got far enough to have one. A blocked
            # Receipt saying an address was refused, with no address in it, tells
            # an auditor that a name misbehaved without telling them how.
            receipt["pinned_ips"] = pinned_ips(refusal.pinned)
        if refusal.retry_at is not None:
            # In the row and not only in the answer. The answer is read once, by
            # a caller that may not be running any more by the time anyone asks
            # what happened; the Receipt is what a retry is reconstructed from,
            # and a throttle with no time on it is indistinguishable from a
            # refusal that will never lift.
            receipt["retry_after"] = refusal.retry_at.isoformat()
        written: str | None = None
        try:
            written = self.server.fence.blocked_receipt(program_id, capability, receipt)
        except (pg.DatabaseError, pg.ConnectionError_, OSError, Refused) as error:
            self.log_error("no blocked receipt for %s: %s", program_id, error)
        # The refusal names the row it just wrote, in the same words the served
        # path names its own: a caller that cannot cite the record cannot show
        # that its request was refused rather than lost, and the runtime reads a
        # missing name as an integrity failure -- which is what it should mean.
        # `write_blocked_receipt` answers with the label for that reason: a row id
        # would be a name only this process and the schema can resolve, and the
        # thing being told is the agent.
        #
        # What it does not carry is `refusal.detail`. That field holds whatever
        # explained the refusal here, and for a fence refusal what explained it is
        # the database's own error text -- SQLSTATE, message and the PL/pgSQL
        # frame it was raised in. The caller is the thing being fenced. Prose it
        # may read is passed in explicitly by the caller of this method.
        #
        # Which token the answer carries, and under which status, is read off the
        # reason the row was just filed under, so that the record and the answer
        # cannot say two different things. Only the default is replaced: a caller
        # that named a token itself -- a receipt that would not write, a tunnel
        # that was not opened -- knows something this cannot improve on. The
        # status moves for the same reason the token does: 407 asks the caller
        # for a capability, and asking for one here would be this door demanding
        # the one thing that was not missing.
        status = refusal.status
        if decision == REFUSED and refusal.reason in TARGET_FAULT:
            decision, status = UNREACHABLE, 502
        self._answer(
            status,
            decision,
            detail=detail or refusal.reason,
            body=b"",
            receipt=written,
            headers=_retry_after(refusal.retry_at),
            # The same expression the Receipt above is filed with, for the same
            # reason the decision token is read off the reason: the answer and
            # the row say one thing. `denied` is a refusal taken before the
            # policy was asked, which is itself the news.
            scope_class=authorization.scope_class if authorization else "denied",
        )

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
        scope_class: str | None = None,
    ) -> None:
        """One answer to the caller, with the Receipt's name on it when there is one.

        `send_response_only` and not `send_response`, which is the same choice
        the CONNECT above makes and now for a second reason. The difference
        between them is that `send_response` stamps a `Server` and a `Date` of
        this door's own, and the caller reads the header list of this hop as
        what the target answered with. A target that sent its own `Date` -- and
        a cache reading is arithmetic on exactly that one -- would arrive with
        two, one of them this process's clock, and nothing on the hop tells them
        apart. So the door says nothing here it is not asked to say: what it has
        to state about the exchange it states under its own prefix, where the
        name itself says whose statement it is.
        """
        self.close_connection = True
        self.send_response_only(status, reason)
        for name, value in headers or []:
            if not describes_this_hop(name):
                self.send_header(name, value)
        if decision:
            self.send_header(DECISION, decision)
        if detail:
            self.send_header(DETAIL, detail)
        if receipt:
            self.send_header(RECEIPT, receipt)
        if scope_class:
            self.send_header(SCOPE, scope_class)
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


def _header(headers: list[tuple[str, str]], name: str) -> str | None:
    """One header out of what a target answered, by name, case-insensitively.

    The first, when there are several. A target that answered with two `Location`
    lines has not said where it is pointing, and the record says what the first
    one claimed rather than silently joining two claims into one string nobody
    sent.
    """
    wanted = name.lower()
    return next((value for header, value in headers if header.lower() == wanted), None)


def _media(value: str | None) -> str | None:
    """A `Content-Type` reduced to the media type it names, lowercased.

    Parameters dropped, because `application/javascript` and
    `application/javascript; charset=utf-8` are one answer to the question this
    is asked for -- whether what came back is application source -- and keeping
    the charset would make that a question about two strings. Null stays null: a
    target that declared no type has said nothing, which is not the same as
    having said `text/plain`.
    """
    if value is None:
        return None
    return value.split(";", 1)[0].strip().lower() or None


def _authority(host: str, port: int, protocol: str | None) -> str:
    """The `Host` header for a canonicalised target, default port omitted."""
    literal = f"[{host}]" if ":" in host else host
    if (protocol == "http" and port == 80) or (protocol == "https" and port == 443):
        return literal
    return f"{literal}:{port}"


def _hostport(authority: str) -> tuple[str, int]:
    """The target of a CONNECT line, which is a host and a port and nothing else.

    Parsed here rather than by `urlsplit`, because an authority-form request
    target is not a URL: `urlsplit("target.example:443")` reads the host as a
    scheme. A refusal is a 400 rather than a 407 for the same reason `_request`
    uses one -- this was not a proxy request that was refused, it was not a
    proxy request.
    """
    host, separator, port = authority.rpartition(":")
    if not separator or not host:
        raise Refused(
            "not a tunnel request", f"{authority!r} is not host:port", status=400
        )
    host = scope.unbracket(host)
    try:
        number = int(port)
    except ValueError as error:
        raise Refused(
            "not a tunnel request", f"{authority!r} has no readable port", status=400
        ) from error
    if not 0 < number < 65536:
        raise Refused(
            "not a tunnel request", f"{authority!r} names no port that exists", status=400
        )
    return host.lower(), number


def _hostname(parts: SplitResult) -> str | None:
    """The host of a URL that may not have one. `urlsplit` defers the parse."""
    try:
        return parts.hostname
    except ValueError:
        return None


def _port(parts: SplitResult) -> int | None:
    """The port of a URL that may not have a readable one.

    The scheme's default when the URL omits it, because a blocked Receipt is
    read alongside the allowed ones, and those name a port the canonicaliser
    filled in the same way. A row that said `null` for `https://host/path` and
    `443` for `https://host:443/path` would make two spellings of one refusal
    look like two different facts.
    """
    try:
        port = parts.port
    except ValueError:
        return None
    if port is not None:
        return port
    return scope.DEFAULT_PORTS.get(parts.scheme.lower())


def listen(
    address: tuple[str, int],
    *,
    fence: Fence | None,
    store: Store,
    connector: Connector = connect,
    resolver: Resolver = resolve,
    timeout: float = TIMEOUT,
    authority: tls.Authority | None = None,
    root_secret: seal.Root | None = None,
) -> Server:
    """Bind the listening socket without serving on it."""
    return Server(
        address,
        Handler,
        fence=fence,
        store=store,
        connector=connector,
        resolver=resolver,
        timeout=timeout,
        authority=authority,
        root_secret=root_secret,
    )


def serve(
    settings: pg.Settings,
    *,
    root: Path,
    host: str = "127.0.0.1",
    port: int = 0,
    authority: Path | None = None,
    key: seal.Location | None = None,
    contained: bool = False,
    announce: Callable[[str], None] | None = None,
    announce_identity: Callable[[str, str], None] | None = None,
    build_anchor: Traversable | None = None,
) -> Report:
    """Run the fence until it is interrupted.

    Binds before it connects, so an operator who named a port something else
    holds learns that from the report rather than after a database session has
    been opened for a process that cannot listen.

    And by default it binds nowhere but this machine. `endpoint` refuses to send
    a capability to a proxy that is not local; a listener on a routable interface
    is the same hole from the other side, because what arrives at it is bearer
    material that anybody who can reach the port may spend. `contained` is the
    one exception, for the door that has to be an Agent network's peer -- see
    `_unbindable` for what it costs and `door` for who pays it. `rk proxy serve`
    never passes it.

    `announce` is called with the endpoint the moment the socket is bound and
    before anything is served on it. The report is written when the listener
    closes, which is far too late to be a readiness signal, and a starter that
    guessed instead would be a race nobody can reproduce.

    Before any of that it verifies its own install: a door serving code that is
    not the code its build manifest claims writes Receipts it cannot stand
    behind, so it refuses to listen rather than serve one. `build_anchor` names
    the package to check and defaults to the installed one; a source checkout has
    no manifest and passes, which is why the contained door is unaffected.
    """
    ledger = Ledger()

    if not build.record(ledger, build_anchor).ok:
        return report(SERVE, ledger, endpoint=None, certificate=None)

    unbindable = _unbindable(host, contained)
    if unbindable is not None:
        ledger.fail(
            "listener",
            unbindable,
            code=INVALID_CONFIGURATION,
            source="argument:--host",
        )
        return report(SERVE, ledger, endpoint=None, certificate=None)

    signing: tls.Authority | None = None
    if authority is not None:
        try:
            signing = tls.authority(authority)
        except tls.Missing as error:
            ledger.fail(
                "authority", str(error), code=MISSING_DEPENDENCY, source="runtime:program:openssl"
            )
            return report(SERVE, ledger, endpoint=None, certificate=None)
        except tls.Unusable as error:
            ledger.fail(
                "authority", str(error), code=INVALID_CONFIGURATION, source="argument:--authority"
            )
            return report(SERVE, ledger, endpoint=None, certificate=None)
        ledger.hold("authority", f"tunnels are intercepted under {signing.certificate}")
    else:
        # Said out loud rather than left to be discovered: a door with no
        # authority answers CONNECT with a refusal, and an operator who expected
        # HTTPS to work needs to read that here and not in an agent's logs.
        ledger.hold("authority", NO_AUTHORITY + "; a tunnel is refused rather than relayed")
    certificate = str(signing.certificate) if signing else None

    root_secret: seal.Root | None = None
    if key is not None:
        try:
            root_secret = seal.load_root(key)
        except seal.Unusable as error:
            ledger.fail(
                "artifact_key",
                str(error),
                code=INVALID_CONFIGURATION,
                source="argument:--key",
            )
            return report(SERVE, ledger, endpoint=None, certificate=certificate)
        except vault.Refused as refusal:
            ledger.refuse("artifact_key", refusal.violation.detail, [refusal.violation])
            return report(SERVE, ledger, endpoint=None, certificate=certificate)
        ledger.hold("artifact_key", "wire-only target responses will be sealed")
    else:
        ledger.hold(
            "artifact_key",
            f"no key material (${seal.KEY_VARIABLE}); authentication-bearing responses are refused",
        )

    try:
        server = listen(
            (host, port),
            fence=None,
            store=Store(Path(root)),
            authority=signing,
            root_secret=root_secret,
        )
    except OSError as error:
        ledger.fail(
            "listener",
            f"cannot listen on {host}:{port}: {error}",
            code=INVALID_CONFIGURATION,
            source="argument:--port",
        )
        return report(SERVE, ledger, endpoint=None, certificate=certificate)
    endpoint = f"http://{host}:{server.server_address[1]}"
    ledger.hold("listener", f"listening on {host}:{server.server_address[1]}")

    connection = migrate.open_connection(ledger, settings)
    if connection is None:
        server.server_close()
        return report(SERVE, ledger, endpoint=None, certificate=certificate)
    server.fence = Fence(connection)
    # Announced here rather than at the bind, because a socket with no fence
    # behind it answers every request with a refusal: a starter that took the
    # bind for readiness would hand back a door that is up and useless.
    if announce_identity is not None:
        announce_identity(endpoint, pg.database_identity(connection))
    elif announce is not None:
        announce(endpoint)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        ledger.hold("shutdown", "interrupted by the operator")
    finally:
        server.server_close()
        connection.close()
    return report(SERVE, ledger, endpoint=endpoint, certificate=certificate)


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
#: The third verdict. `ask` is not a refusal to work around and not a permission:
#: it is the request ticket 11 reserves for a person, and this is the verb that
#: puts the question where a person can answer it. Everything the parked shape
#: needs -- the pending decision, the notification, the `parked` Tool run naming
#: it, the Agent run ending -- is one transaction inside the database, because a
#: runtime that assembled it here would be a second place the parked shape lives.
PARK_TOOL_RUN = "SELECT park_for_human($1::uuid)"
#: Closing is what revokes: `guard_tool_run_authorization` clears the digest and
#: its expiry on any update that leaves `running`, so a Tool run cannot end and
#: keep a live capability. Stated here rather than written here, because a
#: runtime that cleared it itself would be a second place the rule lives.
#: `closed_by` is deliberately not set: 022 restricts it to the four hook events
#: and exempts a runtime-opened row from carrying one, because the runtime
#: closing its own row has no hook event to cite and inventing one would make the
#: column unusable as evidence.
#:
#: Both are guarded against a row that has already ended, because the close runs
#: in a `finally` and one path -- parking -- closes the run itself, with words
#: this one does not have: the decision it is waiting on, and `parked` rather
#: than an outcome. Unguarded, the last writer would win and erase them.
CLOSE_TOOL_RUN = (
    "UPDATE tool_runs SET status = $2, finished_at = now(),"
    " exit_detail = CASE WHEN $2 = 'error' THEN coalesce(exit_detail,"
    " 'runtime closed the Tool run as error before a Receipt was recorded')"
    " ELSE exit_detail END"
    " WHERE id = $1::uuid AND status = 'running'"
)
CLOSE_RUN = (
    "UPDATE agent_runs SET finished_at = now(), stop_reason = $2"
    " WHERE id = $1::uuid AND finished_at IS NULL"
)


@dataclass(frozen=True)
class Answer:
    """What the door said back, on whichever hop it said it on.

    `decision` is the door's own token and is absent when the request was
    served, which is the only reliable way to tell "this fence refused" from
    "the target answered 407": both are a 407 on the wire, and only one of them
    means no bytes reached the target. Branching on the status alone would make
    a target's own refusal close a Tool run as denied and a fence refusal close
    one as success, which is the same mistake in both directions.

    `headers` is the other half of what the target said, next to the body that
    was already here. Pairs in the order they arrived rather than a mapping,
    because a target that answered with two `Vary` lines said two things and a
    mapping keeps one of them -- the reason `_header` below reads the first of
    several rather than joining them into a value nobody sent.
    """

    status: int
    body: bytes
    receipt: str | None
    decision: str | None
    detail: str | None
    headers: tuple[tuple[str, str], ...] = ()
    #: Ticket 136: the class the policy graded this request at. Absent only from
    #: an answer no door gave -- a hop that failed before the fence saw it.
    scope_class: str | None = None


def _answered(answer: http.client.HTTPResponse) -> Answer:
    """Read one response into the facts the runtime decides on and the caller reads.

    The named fields are the decision and `headers` is the reading, and the
    same predicate that keeps an internal name off a wire is what keeps the two
    apart. `RECEIPT`, `DECISION` and `DETAIL` are read into their own fields and
    then left out of the list: they are this door's statements about the
    exchange rather than anything a target said, and a caller that found them
    among the target's headers would be reading the fence's behaviour while
    believing it was reading the target's.

    Hop-by-hop names are left out for the neighbouring reason. `Content-Length`
    is the length this process measured of the body it re-sent, and
    `Connection: close` is what this hop chose; both describe the door's answer
    to this client and not the target's answer to the request. What the target
    framed its own answer with is in the sealed wire Artifact the Receipt names,
    byte for byte, which is where an auditor who needs that reads it.

    Nothing here filters for credential material, and that absence is
    deliberate. `response_for_agent` has already removed the six
    `WIRE_RESPONSE_HEADERS` and `project_identity_response` has already removed
    a leased Identity's own renderings, both before the door answered, so those
    names are absent from this hop by construction. A second filter here would
    be a second place that rule lives, and a rule with two places is one that
    can be changed in one of them.
    """
    return Answer(
        status=answer.status,
        body=answer.read(CEILING + 1),
        receipt=answer.headers.get(RECEIPT),
        decision=answer.headers.get(DECISION),
        detail=answer.headers.get(DETAIL),
        scope_class=answer.headers.get(SCOPE),
        headers=tuple(
            (name, value)
            for name, value in answer.headers.items()
            if not describes_this_hop(name)
        ),
    )


def send(
    runtime: pg.Settings | None,
    configuration_path: Path,
    url: str,
    *,
    proxy_url: str,
    method: str = "GET",
    timeout: float = TIMEOUT,
    ca_file: Path | None = None,
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
        "decision": None,
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
    ledger.hold("request", f"{method} {request.host}:{request.port}{request.path_norm}")

    trust: ssl.SSLContext | None = None
    if request.protocol == "https":
        # The door is about to present a certificate for a host it does not own,
        # which is what interception is. Verifying it against this run's root is
        # the difference between that and any other machine on the path doing the
        # same thing, so there is no default and no fallback to the system store:
        # without the root the request is refused before a capability is minted.
        if ca_file is None:
            ledger.fail(
                "trust_root",
                f"an https target needs the door's certificate: pass --ca or set {CA_VARIABLE}",
                code=INVALID_CONFIGURATION,
                source=f"environment:{CA_VARIABLE}",
            )
            return report(REQUEST, ledger, **facts)
        try:
            trust = tls.trust(ca_file)
        except (OSError, ssl.SSLError) as error:
            ledger.fail(
                "trust_root",
                f"the door's certificate at {ca_file} cannot be used: {error}",
                code=INVALID_CONFIGURATION,
                source="argument:--ca",
            )
            return report(REQUEST, ledger, **facts)
        ledger.hold("trust_root", f"the tunnel is verified against {ca_file} and nothing else")

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
        _spend(
            ledger,
            facts,
            connection,
            program_id,
            url,
            method,
            (host, port),
            timeout,
            request,
            trust,
        )
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
    request: scope.Request,
    trust: ssl.SSLContext | None,
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
        gate = as_object(connection.execute(AUTHORIZE_TOOL_RUN, (tool_run_id,)).scalar())
        capability = gate.get("capability")
        if not capability and gate.get("decision") == "ask":
            outcome = _park(ledger, facts, connection, tool_run_id, label, gate)
            return
        if not capability:
            ledger.fail(
                "authorization",
                f"the gate answered {gate.get('decision')} for {label}: no capability was minted",
                code=INVALID_CONFIGURATION,
                source="database",
            )
            outcome = "denied"
            return
        # The approval, when a live grant is what admitted this call rather than
        # the policy alone. Reported for the same reason the database records it:
        # an operator reading "allowed" on a call whose class asks a human should
        # be able to see which answer it was allowed under, without going to look
        # for it.
        facts["decision"] = gate.get("approval")
        ledger.hold(
            "authorization",
            f"{label} is {gate.get('risk_class')}/{gate.get('decision')} by {gate.get('rule')}"
            + (f" under {gate['approval']}" if gate.get("approval") else ""),
        )
        answer = _through(
            listener, url, method, capability, program_id, timeout, request, trust
        )
        facts["response"] = {"status": answer.status, "byte_size": len(answer.body)}
        facts["receipt"] = answer.receipt
        if answer.receipt is None:
            ledger.fail(
                "receipt",
                f"the proxy answered {answer.status} without naming a Receipt",
                code=INTEGRITY_FAILED,
                source="proxy",
            )
            return
        ledger.hold("receipt", f"the proxy wrote {answer.receipt} for a {answer.status} answer")
        if answer.decision == UNREACHABLE:
            # Not a refusal at all: the gate said allow, the capability was
            # minted and spent, and what did not answer is the target. Closing
            # this run as `denied` would write the word for "the harness said no"
            # onto a row whose own `decision` column says `allow`, and an
            # operator reading the pair back cannot tell that from a fence that
            # actually refused. `error` is the outcome word for a run that was
            # authorised and did not complete, which is what this is.
            ledger.fail(
                "egress",
                f"the target did not answer: {answer.detail or 'no reason given'}",
                code=TARGET_UNREACHABLE,
                source=f"target:{_hostname(urlsplit(url)) or url}",
            )
            outcome = "error"
            return
        if answer.decision is not None:
            # A refused request is a request that did not happen, and it is the
            # blocked Receipt above that proves it. What it must not become is a
            # Tool run closed as success: the row would say the capability was
            # spent on an exchange, the command would exit 0, and an operator
            # scripting `rk proxy request` would read "refused by the fence" as
            # "served". The Receipt is named either way, because the refusal is
            # as auditable as the exchange.
            ledger.fail(
                "egress",
                f"the proxy refused this request as {answer.decision}: "
                f"{answer.detail or 'no reason given'}",
                code=INVALID_CONFIGURATION,
                source="proxy",
            )
            outcome = "denied"
            return
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


def _park(
    ledger: Ledger,
    facts: dict,
    connection: pg.Connection,
    tool_run_id: str,
    label: str,
    gate: dict,
) -> str:
    """The third verdict: file the question and stop, rather than settle it.

    `ask` is the one answer the gate gives that this process may not act on. The
    shape it had before was to report "no capability was minted" and close the
    Tool run as `denied`, which is this runtime deciding the request it was told
    to bring to a person -- and deciding it in the direction that leaves no trace
    of the question. Nobody was asked, nothing was queued, and the row read as if
    the harness had refused.

    Reported as a failed assertion because the request did not happen and a
    caller must not read the exit as "served", but under its own class: an open
    decision is not a fault to go and fix, and the only thing that resolves it is
    an answer.
    """
    try:
        with connection.transaction():
            decision = str(connection.execute(PARK_TOOL_RUN, (tool_run_id,)).scalar())
    except pg.DatabaseError as error:
        # The question could not be filed, so nobody will be asked it. Loud, and
        # under the integrity class: the parked shape is the whole of ticket 11's
        # answer to a call this harness may not make alone, and a runtime that
        # quietly continued past it would be back to deciding it.
        ledger.fail(
            "authorization",
            f"the gate answered ask for {label} and the question could not be filed: {error}",
            code=INTEGRITY_FAILED,
            source="database",
        )
        return "error"
    facts["decision"] = decision
    ledger.fail(
        "authorization",
        f"{label} is {gate.get('risk_class')}/ask by {gate.get('rule')}: "
        f"filed as {decision} for a human to answer",
        code=AWAITING_DECISION,
        source=f"decision:{decision}",
    )
    return "parked"


def spend(
    listener: tuple[str, int],
    url: str,
    *,
    capability: str,
    program_id: str,
    method: str = "GET",
    headers: Mapping[str, str] | None = None,
    body: bytes = b"",
    timeout: float = TIMEOUT,
    trust: ssl.SSLContext | None = None,
) -> Answer:
    """Spend one already-minted capability on one request, and read the answer.

    The half of `send` that is only the wire. `send` is the operator's whole
    command -- it loads a configuration, opens a Tool run, mints and revokes --
    and none of that is available to an Agent child, which has no database and
    no configuration file and is handed a capability that some other process
    minted and will revoke. What the child does have is exactly this: an
    address, a capability, a Program to claim and one request to make.

    Public so that side does not grow a second client. A hand-rolled request
    inside the boundary would be a second place the control headers are spelled,
    the tunnel is opened and the door's refusal is read back -- and the third of
    those is the one that decides whether a Tool run closes as denied or as
    served.

    The body is bytes and not a string, because what a caller means to send is
    a byte sequence and the encoding it chose is already spent by the time it
    reaches here. Whether the door will accept one is not asked here: the door
    re-decides every request against live policy, and a client that decided for
    itself which of its requests may carry a body would be the second opinion
    this whole arrangement exists to not have.
    """
    return _through(
        listener,
        url,
        method,
        capability,
        program_id,
        timeout,
        scope.canonical_request(url),
        trust,
        headers=headers,
        body=body,
    )


def _through(
    listener: tuple[str, int],
    url: str,
    method: str,
    capability: str,
    program_id: str,
    timeout: float,
    request: scope.Request,
    trust: ssl.SSLContext | None,
    *,
    headers: Mapping[str, str] | None = None,
    body: bytes = b"",
) -> Answer:
    """The request itself, with the capability on the hop that reaches the door.

    Two shapes, one for each protocol. Plain HTTP goes in absolute form, which
    is what a proxy request is. HTTPS opens a tunnel first and then sends an
    ordinary origin-form request inside it, which is what every client does --
    and the control headers go on the CONNECT, because that is the hop the
    capability is for and the one the door can read.

    The caller's own headers ride the hop that carries the message: alongside
    the control headers on plain HTTP, and inside the tunnel on HTTPS, where
    the door cannot read them anyway. The control headers are applied last, so
    a caller that names one is naming a value this hop overwrites rather than
    one it sends.

    The body rides the same hop as the headers that describe it, which on the
    tunnelled shape is inside the tunnel, so the door reads it as the request
    it terminated rather than as anything the CONNECT carried. `http.client`
    frames it with a `Content-Length` it measures itself, which is the only
    length that could be right here: `_carried` has already dropped whatever
    the caller said the length was, because a length this client did not
    measure is a length nothing on this hop may state.
    """
    host, port = listener
    control = {AUTHORIZATION: f"RedKraken {capability}", PROGRAM: program_id}
    carried = _carried(headers)
    if trust is None:
        client = http.client.HTTPConnection(host, port, timeout=timeout)
        try:
            client.request(method.upper(), url, body=body, headers={**carried, **control})
            return _answered(client.getresponse())
        finally:
            client.close()

    raw = socket.create_connection((host, port), timeout=timeout)
    try:
        refusal = _tunnel(raw, request, control)
        if refusal is not None:
            return refusal
        # `set_tunnel` would do all of the above in one call and raise `OSError`
        # on a refusal, which is why it is not used: the door's answer to a
        # CONNECT carries the decision and the name of the Receipt it wrote, and
        # a client that turns that into "Tunnel connection failed" has thrown
        # away the only evidence the refusal produced.
        secured = trust.wrap_socket(raw, server_hostname=request.host)
        client = http.client.HTTPConnection(request.host, request.port, timeout=timeout)
        client.sock = secured
        try:
            client.request(method.upper(), origin_form(url), body=body, headers=carried)
            return _answered(client.getresponse())
        finally:
            client.close()
    finally:
        raw.close()


def _carried(headers: Mapping[str, str] | None) -> dict[str, str]:
    """The caller's own headers, minus anything that describes a hop.

    The rule the door applies to what arrives, applied here to what leaves. A
    caller does not get to name its own capability, the Program it claims or a
    length this client did not measure, and saying so with the predicate that
    already says it means the two sides cannot drift apart on which names are
    the connection's rather than the message's.
    """
    return {
        name: value for name, value in (headers or {}).items() if not describes_this_hop(name)
    }


def _tunnel(
    raw: socket.socket, request: scope.Request, control: dict[str, str]
) -> Answer | None:
    """Ask for the tunnel, and return the refusal if there was one.

    `_authority` with no protocol is the authority form: a CONNECT target
    always carries its port, including the default one, because there is no
    scheme in the request line to imply it.
    """
    authority = _authority(request.host, request.port, None)
    lines = [f"CONNECT {authority} HTTP/1.1", f"Host: {authority}"]
    lines += [f"{name}: {value}" for name, value in control.items()]
    raw.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("latin-1"))
    answer = http.client.HTTPResponse(raw, method="CONNECT")
    try:
        answer.begin()
        if answer.status == 200:
            return None
        return _answered(answer)
    finally:
        # The header reader is closed either way; the socket under it is not,
        # because on the accepted path it is about to carry a TLS session.
        answer.close()
