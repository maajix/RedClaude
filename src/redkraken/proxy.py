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

import http.client
import hmac
import ipaddress
import json
import re
import socket
import ssl
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.message import Message
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import SplitResult, urljoin, urlsplit

from redkraken import config, identity, migrate, pg, program, scope, seal, tls
from redkraken.outcome import (
    INTEGRITY_FAILED,
    INVALID_CONFIGURATION,
    MISSING_DEPENDENCY,
    Ledger,
    Report,
    report,
)
from redkraken.store import Store, digest


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
    "pinned_ips",
    "query_sha256",
    "redirected",
    "response_for_agent",
    "resolve",
    "send",
    "serve",
    "take_control",
    "unroutable",
]


COMMAND = "proxy"
SERVE = f"{COMMAND} serve"
REQUEST = f"{COMMAND} request"

#: Where the door listens, for the runtime that has to reach it. Deliberately not
#: a connection string: the fence's own login is `RK_PROXY_DATABASE_URL` and it is
#: `rk2_proxy`, so no single exported variable runs both sides of the fence.
PROXY_URL = "RK_PROXY_URL"

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

#: The statuses that point a client somewhere else. Named because the door does
#: not follow one -- the client does, back through this same fence, where the
#: new URL is canonicalised and decided on its own -- and what the door owes the
#: record is the target it handed over, canonicalised the same way.
REDIRECTS = frozenset({301, 302, 303, 307, 308})

# Response fields whose value is authentication material issued by the target,
# rather than content the Agent may consume.  Header names are the enforceable
# boundary available before ticket 12 adds per-Identity body projections.
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
    headers: list[tuple[str, str]], body: bytes
) -> tuple[list[tuple[str, str]], bytes]:
    """Withhold target-controlled Identity response fields from the Agent view.

    Credential reflection is not safely recognizable: a target may transform,
    split or encode a value before returning it. The exact headers and body
    remain available only through the sealed wire view.
    """
    return [], b""


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
    "SELECT program_id::text, tool_run_id::text, scope_version, scope_class,"
    "       identity_entity_id::text, identity_label"
    "  FROM authorize_identity_egress_request($1, $2, $3, $4, $5::integer, $6, $7)"
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

#: What that function says when the capability, rather than the address, is what
#: it refused. Matched as a string because it arrives as one: both refusals carry
#: `23514`, so the code separates them from a constraint violation and this
#: separates them from each other.
LAPSED = "egress capability refused"

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

WIRE_KEYING = (
    "SELECT generation, salt_hex, root_check_hex"
    "  FROM ensure_proxy_wire_keying($1, $2::bytea, $3::bytea)"
)

BLOCKED = "SELECT write_blocked_receipt($1::uuid, $2::jsonb, $3)::text"

BIND = "SELECT set_config('rk2.program_id', $1, false)"


def _object(answer: object) -> dict:
    """One `jsonb` answer as a mapping, whichever shape the driver returned it in.

    Both sides of this module read a function that answers with an object, and a
    second spelling of the same two-branch decode is a second place for the two
    to disagree about what an answer with no rows looks like.
    """
    return json.loads(answer) if isinstance(answer, str) else dict(answer)


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
        return _object(answer)

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
Connector = Callable[
    [str, int, float, str, str, identity.ClientCertificate | None],
    http.client.HTTPConnection,
]


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


def connect(
    host: str,
    port: int,
    timeout: float,
    protocol: str,
    address: str,
    client_certificate: identity.ClientCertificate | None,
) -> http.client.HTTPConnection:
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

    An https target is verified against the system trust store, and this is the
    only place in the harness where a real certificate is seen at all. The agent
    is looking at this door's certificate by construction, so a claim about the
    target's -- issuer, expiry, name, chain -- can only be made on this side of
    the door. `intercepted` on the Receipt is what stops the agent's view from
    being read as the target's.
    """
    context: ssl.SSLContext | None = None
    if protocol == "https":
        context = ssl.create_default_context()
        if client_certificate is not None:
            client_certificate.install(context)
    raw = socket.create_connection((address, port), timeout=timeout)
    try:
        if protocol == "https":
            assert context is not None
            connection: http.client.HTTPConnection = http.client.HTTPSConnection(
                host, port, timeout=timeout, context=context
            )
            connection.sock = context.wrap_socket(raw, server_hostname=host)
        else:
            connection = http.client.HTTPConnection(host, port, timeout=timeout)
            connection.sock = raw
    except OSError:
        # The handshake is where this happens, and a target whose certificate
        # does not verify has already been given a socket. Closing it here is
        # what stops a refused exchange from holding a descriptor open until the
        # collector notices: nothing else refers to it, because the connection
        # object that would have owned it was never returned.
        raw.close()
        raise
    return connection


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

    def _serve(self) -> None:
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

        try:
            request = self._request(url)
            if control.capability is None:
                raise Refused("capability refused", "no capability was offered")
            authorization = self.server.fence.authorize(
                program_id, control.capability, self.command, request
            )
            body = self._body()
        except Refused as refusal:
            return self._refuse(program_id, control.capability, refusal, arrival, url=url)

        try:
            addresses = self._pin(authorization, control.capability, request)
        except Refused as refusal:
            # Its own block, because by here there is an `authorization` and the
            # record has to say so. A request refused for its address was in
            # scope by name and spent a live capability to get that far, and a
            # Receipt that filed it as `denied` alongside the ones that never
            # resolved anything would hide exactly the case worth seeing: a name
            # the policy allows, pointing somewhere the policy does not.
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
        authority = self.server.authority
        if authority is None:
            return self._answer(405, TUNNEL, detail=NO_AUTHORITY, body=b"")
        try:
            host, port = _hostport(self.path)
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
    ) -> tuple[str, ...]:
        """Turn the authorized name into the address that will be dialled.

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

        What comes back is every address, not the one that was chosen. The
        Receipt names them all: an auditor asking why a name was refused needs to
        see what it answered with, and an auditor reading an allowed exchange
        needs to see that the other answers were checked too. Only the first is
        put to the policy, because only the first is dialled -- the rest are held
        to being routable and to being recorded, and a Program that withdrew one
        of them has withdrawn a machine this request never contacted.
        """
        addresses = destination(request.host, request.port, self.server.resolver)
        self.server.fence.authorize_address(
            authorization.program_id, capability, request, addresses[0]
        )
        return addresses

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
        try:
            connection = self.server.connector(
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

        binding: IdentityBinding | None = None
        client_certificate: identity.ClientCertificate | None = None
        client_certificate_sha: str | None = None
        wire_headers = list(agent_headers)
        if authorization.identity_entity_id is not None:
            root = self.server.root_secret
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

        sent = transcript(line, agent_headers, body)
        wire_sent = transcript(line, wire_headers, body)
        if binding is not None:
            binding.changed = binding.session.capture(url, back)
            agent_back, agent_returned = project_identity_response(back, returned)
            agent_reason = ""
        else:
            agent_back, agent_returned = response_for_agent(back), returned
            agent_reason = reason
        received = transcript(f"HTTP/1.1 {status} {agent_reason}", agent_back, agent_returned)
        wire_received = transcript(f"HTTP/1.1 {status} {reason}", back, returned)
        store = self.server.store
        request_sha, request_new = store.put(sent)
        response_sha, response_new = store.put(received)

        seals: list[dict] = []
        ciphertext_new: set[str] = set()
        transformations = [
            (wire_sent, request_sha, "target_request")
            for _ in range(1 if wire_sent != sent else 0)
        ] + [
            (wire_received, response_sha, "target_response")
            for _ in range(1 if wire_received != received else 0)
        ]
        if transformations:
            root = self.server.root_secret
            if root is None:
                if request_new:
                    store.discard(request_sha)
                if response_new:
                    store.discard(response_sha)
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
                if request_new:
                    store.discard(request_sha)
                if response_new:
                    store.discard(response_sha)
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
                ciphertext_sha, is_new = store.put(envelope)
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
            "notes": f"redirect to {onward}" if onward else None,
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
            # precisely what failed, and bytes no row can reach are discarded
            # rather than left in the store for nobody.
            if request_new:
                store.discard(request_sha)
            if response_new:
                store.discard(response_sha)
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
        )

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
        written: str | None = None
        try:
            written = self.server.fence.blocked_receipt(program_id, capability, receipt)
        except (pg.DatabaseError, OSError, Refused) as error:
            self.log_error("no blocked receipt for %s: %s", program_id, error)
        # The refusal names the row it just wrote, for the same reason the served
        # path names its label: a caller that cannot cite the record cannot show
        # that its request was refused rather than lost, and the runtime reads a
        # missing name as an integrity failure -- which is what it should mean.
        #
        # What it does not carry is `refusal.detail`. That field holds whatever
        # explained the refusal here, and for a fence refusal what explained it is
        # the database's own error text -- SQLSTATE, message and the PL/pgSQL
        # frame it was raised in. The caller is the thing being fenced. Prose it
        # may read is passed in explicitly by the caller of this method.
        self._answer(
            refusal.status,
            decision,
            detail=detail or refusal.reason,
            body=b"",
            receipt=written,
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
            self.send_header(DETAIL, detail)
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


def _header(headers: list[tuple[str, str]], name: str) -> str | None:
    """One header out of what a target answered, by name, case-insensitively.

    The first, when there are several. A target that answered with two `Location`
    lines has not said where it is pointing, and the record says what the first
    one claimed rather than silently joining two claims into one string nobody
    sent.
    """
    wanted = name.lower()
    return next((value for header, value in headers if header.lower() == wanted), None)


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
    key: Path | None = None,
) -> Report:
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
    ledger.hold("listener", f"listening on {host}:{server.server_address[1]}")

    connection = migrate.open_connection(ledger, settings)
    if connection is None:
        server.server_close()
        return report(SERVE, ledger, endpoint=None, certificate=certificate)
    server.fence = Fence(connection)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        ledger.hold("shutdown", "interrupted by the operator")
    finally:
        server.server_close()
        connection.close()
    return report(
        SERVE,
        ledger,
        endpoint=f"http://{host}:{server.server_address[1]}",
        certificate=certificate,
    )


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


@dataclass(frozen=True)
class Answer:
    """What the door said back, on whichever hop it said it on.

    `decision` is the door's own token and is absent when the request was
    served, which is the only reliable way to tell "this fence refused" from
    "the target answered 407": both are a 407 on the wire, and only one of them
    means no bytes reached the target. Branching on the status alone would make
    a target's own refusal close a Tool run as denied and a fence refusal close
    one as success, which is the same mistake in both directions.
    """

    status: int
    body: bytes
    receipt: str | None
    decision: str | None
    detail: str | None


def _answered(answer: http.client.HTTPResponse) -> Answer:
    """Read one response into the four facts the runtime decides on."""
    return Answer(
        status=answer.status,
        body=answer.read(CEILING + 1),
        receipt=answer.headers.get(RECEIPT),
        decision=answer.headers.get(DECISION),
        detail=answer.headers.get(DETAIL),
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


def _through(
    listener: tuple[str, int],
    url: str,
    method: str,
    capability: str,
    program_id: str,
    timeout: float,
    request: scope.Request,
    trust: ssl.SSLContext | None,
) -> Answer:
    """The request itself, with the capability on the hop that reaches the door.

    Two shapes, one for each protocol. Plain HTTP goes in absolute form, which
    is what a proxy request is. HTTPS opens a tunnel first and then sends an
    ordinary origin-form request inside it, which is what every client does --
    and the control headers go on the CONNECT, because that is the hop the
    capability is for and the one the door can read.
    """
    host, port = listener
    control = {AUTHORIZATION: f"RedKraken {capability}", PROGRAM: program_id}
    if trust is None:
        client = http.client.HTTPConnection(host, port, timeout=timeout)
        try:
            client.request(method.upper(), url, headers=control)
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
            client.request(method.upper(), origin_form(url))
            return _answered(client.getresponse())
        finally:
            client.close()
    finally:
        raw.close()


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
