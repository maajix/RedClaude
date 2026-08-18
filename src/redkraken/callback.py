"""The one Observation this harness does not fetch.

Every other piece of evidence here is a request the installation made and a
Receipt the door wrote for it. An out-of-band interaction is the opposite: a
request somebody else made, arriving at a name we published, and the only thing
tying it to a Program is a correlator that travelled out in a payload and came
back in a query.

So the module has two verbs and one idea between them. `provision` mints a
correlator for one subject and hands back the address to embed --
`<correlator>.<channel host>`, because a canary is addressed by its label.
`accept` takes an arrival the operator's own listener recorded, recovers the
correlator from the name it came in at, and asks the database to admit it.

The decision is not made here. `record_callback_interaction` re-asks every
question -- is the channel still declared, is the correlator live, is this the
Program it was minted for, is the name one that channel admits -- and an
`ENABLE ALWAYS` trigger re-asks them again beneath it. What this module does is
parsing and byte handling: find where the correlator ends and the channel
begins, put the exact inbound bytes in the content-addressed store, and report
what the database decided.

A correlator is not a credential, and it is printed. It has to be: an operator
cannot embed a canary they were never told. Holding one authorises no read, no
write and no request; what it does is make an arrival attributable, and it stops
doing even that when it expires.
"""

from __future__ import annotations

import json
import secrets
from datetime import datetime
from pathlib import Path

from redkraken import config, migrate, pg, program, scope
from redkraken.outcome import INVALID_CONFIGURATION, Ledger, Report, report
from redkraken.store import Store


COMMAND = "callback"
PROVISION = f"{COMMAND} provision"
ACCEPT = f"{COMMAND} accept"

#: 128 bits, hex. Long enough that guessing one is not a strategy, short enough
#: to be a single DNS label with room to spare.
CORRELATOR_BYTES = 16

#: How long a correlator stays live when the operator does not say. An hour is
#: about the length of one test, and a canary that outlives the test it was
#: embedded in is a name that confirms a Hypothesis for a reason nobody
#: remembers.
DEFAULT_LIFETIME = 3600

#: And the ceiling. Not a security boundary -- an operator who wants a long
#: canary can mint another -- but a lifetime nobody chose is the one that ends
#: up being forever.
MAX_LIFETIME = 30 * 24 * 3600

#: Where the inbound bytes may have come from, as far as the listener could
#: tell. `unknown` is the honest default: a DNS query arrives from a resolver
#: that is not the target and may not be anywhere near it.
PEERS = ("unknown", "resolver", "client")

#: An arrival bigger than this is not one interaction. The listener writes what
#: it received; a file this size means something else happened.
MAX_ARRIVAL_BYTES = 1 << 20

MINT = (
    "SELECT mint_callback_correlator($1, $2, $3::uuid, make_interval(secs => $4),"
    "                                $5::uuid, $6::uuid)"
)
RECORD = "SELECT record_callback_interaction($1, $2::jsonb, $3::jsonb)"
SUBJECT = "SELECT id::text, type FROM entities WHERE program_id = $1::uuid AND label = $2"
EXPIRY = "SELECT expires_at::text FROM callback_correlators WHERE id = $1::uuid"


def provision(
    runtime: pg.Settings | None,
    configuration_path: Path,
    channel: str,
    subject: str,
    *,
    lifetime: int = DEFAULT_LIFETIME,
    tool_run: str | None = None,
    test_run: str | None = None,
) -> Report:
    """Mint one correlator for one subject on one declared channel.

    The correlator is generated here, digested by the database and kept by
    neither: `mint_callback_correlator` stores the SHA-256 and the plaintext
    exists in this process and in whatever payload the operator puts it in.
    There is no second chance to read it, which is the same property a
    capability has and for the opposite reason -- not because it would be
    dangerous to keep, but because a stored canary is one more place a name can
    be learned from.
    """
    ledger = Ledger()
    facts: dict[str, object] = {"program_id": None, "callback": None}

    policy, slug = _policy(ledger, configuration_path)
    if policy is None or slug is None:
        return report(PROVISION, ledger, **facts)
    endpoint = policy.channel(channel)
    if endpoint is None:
        declared = sorted(entry.name for entry in policy.channels)
        ledger.fail(
            "callback_channel",
            f"{slug} declares no callback channel named {channel}; it declares "
            + (", ".join(declared) if declared else "none"),
            code=INVALID_CONFIGURATION,
            source="argument:--channel",
        )
        return report(PROVISION, ledger, **facts)
    if lifetime < 1 or lifetime > MAX_LIFETIME:
        ledger.fail(
            "callback_lifetime",
            f"{lifetime} second(s) is not a lifetime a correlator may have; "
            f"between 1 and {MAX_LIFETIME}",
            code=INVALID_CONFIGURATION,
            source="argument:--for",
        )
        return report(PROVISION, ledger, **facts)

    connection = migrate.open_connection(ledger, runtime)
    if connection is None:
        return report(PROVISION, ledger, **facts)
    with connection:
        program_id = _open(ledger, connection, slug)
        if program_id is None:
            return report(PROVISION, ledger, **facts)
        facts["program_id"] = program_id

        rows = connection.execute(SUBJECT, (program_id, subject)).rows
        if not rows:
            ledger.fail(
                "callback_subject",
                f"{slug} holds no entity labelled {subject}; a correlator has a "
                "subject because the Observation it produces has one",
                code=INVALID_CONFIGURATION,
                source="argument:--subject",
            )
            return report(PROVISION, ledger, **facts)
        entity_id, entity_type = str(rows[0][0]), str(rows[0][1])

        correlator = secrets.token_hex(CORRELATOR_BYTES)
        with connection.transaction():
            connection.execute("SELECT set_actor('runtime', $1)", (f"rk {PROVISION}",))
            try:
                correlator_id = str(
                    connection.execute(
                        MINT,
                        (channel, correlator, entity_id, lifetime, tool_run, test_run),
                    ).scalar()
                )
            except pg.DatabaseError as error:
                ledger.fail(
                    "callback",
                    f"the correlator was refused: {error}",
                    code=INVALID_CONFIGURATION,
                    source="database",
                )
                return report(PROVISION, ledger, **facts)
        expires = str(connection.execute(EXPIRY, (correlator_id,)).scalar())

    facts["callback"] = {
        "channel": channel,
        "kind": endpoint.kind,
        "correlator_id": correlator_id,
        "address": f"{correlator}.{endpoint.host}",
        "subject": subject,
        "subject_type": entity_type,
        "expires_at": expires,
        "lifetime_seconds": lifetime,
    }
    ledger.hold(
        "callback",
        f"channel {channel} ({endpoint.kind}) is listening for {subject}: "
        f"embed {correlator}.{endpoint.host}, live until {expires}",
    )
    return report(PROVISION, ledger, **facts)


def accept(
    runtime: pg.Settings | None,
    configuration_path: Path,
    host: str,
    source: Path,
    *,
    root: Path,
    peer: str = "unknown",
    at: str | None = None,
) -> Report:
    """Admit one arrival the operator's listener recorded, or refuse it.

    The bytes go into the content-addressed store before the row is written, so
    no committed record names a file that was never stored -- `artifact put`'s
    rule, and the same one direction of skew an audit cannot repair. A refused
    arrival leaves its bytes filed under their own hash and nothing pointing at
    them, which no reader can reach.

    `at` is the moment the listener recorded, and it is what makes handing the
    same recording over twice one arrival rather than two: the database keys an
    arrival on the Program, the correlator, the name, the bytes and that moment,
    so a replay resolves to the row it already wrote. Without it the arrival is
    filed under the acceptance moment, which is different every time.
    """
    ledger = Ledger()
    facts: dict[str, object] = {"program_id": None, "callback": None}

    policy, slug = _policy(ledger, configuration_path)
    if policy is None or slug is None:
        return report(ACCEPT, ledger, **facts)
    if peer not in PEERS:
        ledger.fail(
            "callback_peer",
            f"{peer} is not something a listener can say about a peer; "
            f"one of {', '.join(PEERS)}",
            code=INVALID_CONFIGURATION,
            source="argument:--peer",
        )
        return report(ACCEPT, ledger, **facts)

    received = _moment(ledger, at)
    if ledger.violations:
        return report(ACCEPT, ledger, **facts)

    observed = _name(ledger, host)
    if observed is None:
        return report(ACCEPT, ledger, **facts)
    verdict = scope.decide_callback(policy, observed)
    if not verdict.allowed:
        # The same function the proxy asks, so a name admitted here is a name
        # admitted there. Refused here as well as at the door, and this is the
        # cheaper half: nothing about an undeclared name reaches the database,
        # and the bytes of an arrival at somebody else's host are never stored.
        ledger.fail(
            "callback_channel",
            f"{observed} is not a name any channel {slug} declares admits "
            f"({verdict.reason})",
            code=INVALID_CONFIGURATION,
            source="argument:--host",
        )
        return report(ACCEPT, ledger, **facts)
    endpoint = policy.channel(verdict.channel)
    assert endpoint is not None  # `decide_callback` names a channel of this policy
    correlator = _correlator(ledger, observed, endpoint)
    if correlator is None:
        return report(ACCEPT, ledger, **facts)

    data = _arrival(ledger, Path(source))
    if data is None:
        return report(ACCEPT, ledger, **facts)

    connection = migrate.open_connection(ledger, runtime)
    if connection is None:
        return report(ACCEPT, ledger, **facts)
    keep = Store(Path(root))
    with connection:
        program_id = _open(ledger, connection, slug)
        if program_id is None:
            return report(ACCEPT, ledger, **facts)
        facts["program_id"] = program_id

        with connection.transaction():
            connection.execute("SELECT set_actor('runtime', $1)", (f"rk {ACCEPT}",))
            sha256, written = keep.put(data)
            arrival = {
                "host": observed,
                "arrival_kind": endpoint.kind,
                "peer_class": peer,
                # Null when the caller stated no moment, which is how the writer
                # is told to file the arrival under the moment it accepted it.
                "received_at": received,
            }
            registration = {
                "sha256": sha256,
                "byte_size": len(data),
                "content_type": _content_type(endpoint.kind),
            }
            try:
                accepted = connection.execute(
                    RECORD,
                    (correlator, _encode(arrival), _encode(registration)),
                ).scalar()
            except pg.DatabaseError as error:
                ledger.fail(
                    "callback",
                    f"the interaction was refused: {error}",
                    code=INVALID_CONFIGURATION,
                    source="database",
                )
                return report(ACCEPT, ledger, **facts)

    answer = _decode(str(accepted))
    interaction = answer.get("interaction")
    observation = answer.get("observation")
    duplicate = bool(answer.get("duplicate"))
    facts["callback"] = {
        "interaction": interaction,
        "observation": observation,
        "artifact": answer.get("artifact"),
        "channel": answer.get("channel"),
        "kind": endpoint.kind,
        "sha256": sha256,
        "byte_size": len(data),
        "received_at": answer.get("received_at"),
        "stored": written,
        "duplicate": duplicate,
    }
    # Both sentences name the arrival the call resolved to, because that is the
    # question an operator re-running the command after a crash is asking. The
    # duplicate one holds rather than refuses: what they asked for -- this
    # arrival on the record -- is true, and it was true before they asked.
    if duplicate:
        said = (
            f"{interaction} is already on the record: this arrival resolved to "
            f"it and to {observation}, and nothing was written"
        )
    else:
        said = (
            f"{interaction} arrived on channel {answer.get('channel')} "
            f"({endpoint.kind}): {len(data)} byte(s) stored as "
            f"{answer.get('artifact')}, recorded as {observation}"
        )
    ledger.hold("callback", said)
    return report(ACCEPT, ledger, **facts)


def _policy(
    ledger: Ledger, configuration_path: Path
) -> tuple[scope.Policy | None, str | None]:
    """The compiled policy and the Program it names, or a refusal saying why not."""
    configuration, refusals = config.load(Path(configuration_path))
    if configuration is None:
        ledger.refuse("configuration", f"refused by {len(refusals)} violation(s)", refusals)
        return None, None
    policy, policy_refusals = scope.compile_policy(configuration)
    if policy is None:
        ledger.refuse(
            "scope_policy",
            f"refused by {len(policy_refusals)} violation(s)",
            policy_refusals,
        )
        return None, None
    return policy, str(configuration.document["program"]["name"])


def _open(ledger: Ledger, connection: pg.Connection, slug: str) -> str | None:
    """The open Program this slug names, with the session bound to it."""
    program.assert_runtime_connection(ledger, connection)
    if ledger.violations:
        return None
    program_id = program.resolve(ledger, connection, slug)
    if program_id is None:
        return None
    connection.execute("SELECT set_config('rk2.program_id', $1, false)", (program_id,))
    return program_id


def _name(ledger: Ledger, host: str) -> str | None:
    """The observed name in the one spelling the policy compares in.

    `normalize_host` rather than a local lowercase, because a name canonicalised
    two ways is a name the channel list and the database disagree about, and the
    disagreement would be resolved in favour of whichever half was asked second.
    """
    try:
        return scope.normalize_host(host)
    except scope.PolicyError as error:
        ledger.fail(
            "callback_host",
            f"an arrival names the host it came in at: {error.detail}",
            code=INVALID_CONFIGURATION,
            source="argument:--host",
        )
        return None


def _moment(ledger: Ledger, at: str | None) -> str | None:
    """The moment the listener recorded, or a refusal saying why it is not one.

    Parsed here rather than left to the database so that a mistyped timestamp is
    an argument the operator can see named, and refused when it carries no
    offset: a wall clock with no zone is not a moment, and the database would
    resolve it against whatever `TimeZone` the session happened to hold. What is
    passed on is the parsed value re-rendered, so the string the database reads
    is one this process understood.

    Truncated to microseconds, because that is the resolution `timestamptz` has.
    A listener recording nanoseconds -- interactsh does -- therefore has two
    arrivals in the same microsecond collapse into one, which is the same trade
    the identity of an arrival makes everywhere else.
    """
    if at is None:
        return None
    try:
        moment = datetime.fromisoformat(at)
    except ValueError as error:
        ledger.fail(
            "callback_arrival",
            f"{at} is not a moment a listener could have recorded: {error}",
            code=INVALID_CONFIGURATION,
            source="argument:--at",
        )
        return None
    if moment.tzinfo is None or moment.tzinfo.utcoffset(moment) is None:
        ledger.fail(
            "callback_arrival",
            f"{at} names no offset from UTC; an arrival is a moment rather than "
            "a reading of somebody's clock",
            code=INVALID_CONFIGURATION,
            source="argument:--at",
        )
        return None
    return moment.isoformat()


def _correlator(ledger: Ledger, observed: str, endpoint: scope.Channel) -> str | None:
    """The label the canary was addressed by, recovered from the name.

    The correlator is the label immediately beneath the channel endpoint, not
    the whole prefix: a resolver that queried `www.<correlator>.<endpoint>` is
    reporting one arrival on one canary, and the extra label is the target's
    business rather than ours.
    """
    if observed == endpoint.host:
        ledger.fail(
            "callback_correlator",
            f"{observed} is the channel endpoint itself and carries no correlator; "
            "an interaction nobody can attribute is not evidence",
            code=INVALID_CONFIGURATION,
            source="argument:--host",
        )
        return None
    prefix = observed[: -(len(endpoint.host) + 1)]
    correlator = prefix.rsplit(".", 1)[-1]
    if not correlator:
        ledger.fail(
            "callback_correlator",
            f"{observed} carries no label beneath {endpoint.host}",
            code=INVALID_CONFIGURATION,
            source="argument:--host",
        )
        return None
    return correlator


def _arrival(ledger: Ledger, source: Path) -> bytes | None:
    """The exact bytes the listener recorded, unmodified.

    Not a line, not a trimmed string: what is promoted into an Observation is
    what arrived, and a record this command had to repair is one nobody checked.
    An empty file is refused, because a stored artifact of nothing is a citation
    that says nothing.
    """
    try:
        data = source.read_bytes()
    except OSError as error:
        ledger.fail(
            "callback_arrival",
            f"the interaction cannot be read: {error}",
            code=INVALID_CONFIGURATION,
            source="argument:--from",
        )
        return None
    if not data:
        ledger.fail(
            "callback_arrival",
            "the interaction is empty; an Observation cites bytes that exist",
            code=INVALID_CONFIGURATION,
            source="argument:--from",
        )
        return None
    if len(data) > MAX_ARRIVAL_BYTES:
        ledger.fail(
            "callback_arrival",
            f"the interaction is {len(data)} bytes; one arrival stops at "
            f"{MAX_ARRIVAL_BYTES}",
            code=INVALID_CONFIGURATION,
            source="argument:--from",
        )
        return None
    return data


def _content_type(kind: str) -> str:
    """What the stored bytes are, said rather than sniffed."""
    return "application/dns-message" if kind == "dns" else "message/http"


def _encode(value: dict) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _decode(value: str) -> dict:
    decoded = json.loads(value)
    return decoded if isinstance(decoded, dict) else {}
