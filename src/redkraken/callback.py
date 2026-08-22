"""The one Observation this harness does not fetch.

Every other piece of evidence here is a request the installation made and a
Receipt the door wrote for it. An out-of-band interaction is the opposite: a
request somebody else made, arriving at a name we published, and the only thing
tying it to a Program is a correlator that travelled out in a payload and came
back in a query.

So the module has three verbs and one idea between them. `provision` mints a
correlator for one subject and hands back the address to embed. `accept` takes
an arrival the operator's own listener recorded, recovers the correlator from
wherever the channel keeps it, and asks the database to admit it. `clear` ends
one early, by the id `provision` printed, and says what it caught before it
ended.

Where the correlator sits is the channel's placement, and it is the one thing
about a channel this module keeps asking. A `label` channel is addressed as
`<correlator>.<endpoint>`, which is how a DNS canary has to work; a `path`
channel is addressed as `https://<endpoint>/<correlator>/`, which is how one
bound hostname with no wildcard serves every canary of a Program. And on a
channel whose provider binds its name at run time the endpoint is not in the
configuration at all: it is read from the live binding, and a channel with
nothing bound has no address to hand out.

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
import uuid
from datetime import datetime
from pathlib import Path

from redkraken import config, migrate, pg, program, scope
from redkraken.outcome import INVALID_CONFIGURATION, Ledger, Report, report
from redkraken.store import Store


COMMAND = "callback"
PROVISION = f"{COMMAND} provision"
ACCEPT = f"{COMMAND} accept"
CLEAR = f"{COMMAND} clear"

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
END_CORRELATOR = "SELECT clear_callback_correlator($1::uuid)"
BINDING = "SELECT callback_channel_binding($1)"
CONTROL_ARRIVAL = "SELECT callback_control_arrival($1)"


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

    On a channel this harness publishes, nothing is minted until something has
    demonstrated that an arrival on it reaches the record. That is what makes
    the reading this canary produces readable in both directions: an arrival
    refutes on its own, and no arrival is a finding only beside a control. On a
    channel whose endpoint the operator declared there is no publisher of ours
    to take one at, and the report says so rather than refusing a mint it has no
    way to improve.
    """
    ledger = Ledger()
    facts: dict[str, object] = {"program_id": None, "callback": None}

    policy, slug = policy_for(ledger, configuration_path)
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
        program_id = open_program(ledger, connection, slug)
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

        # Where the channel is answering, asked of the database rather than of
        # the configuration: a static channel answers with the host the operator
        # wrote down, and a bound one with whatever `rk oob up` last bound. The
        # configuration cannot know the second, and a name this process composed
        # from a stale binding would be a canary nothing can reach.
        binding = _decode(str(connection.execute(BINDING, (channel,)).scalar()))
        if not binding.get("bound"):
            ledger.fail(
                "callback_channel",
                f"channel {channel} is declared with provider "
                f"{binding.get('provider', endpoint.provider)} and has no live "
                "binding, so there is no name to embed; `rk oob up` binds one",
                code=INVALID_CONFIGURATION,
                source="argument:--channel",
            )
            return report(PROVISION, ledger, **facts)
        host = str(binding["endpoint"])

        # And what proves the channel records, asked before anything is minted.
        # A canary is embedded to be read either way round: an arrival is a
        # finding on its own, and no arrival is a finding only if something
        # demonstrates that an arrival would have been written down. Without
        # that, a dead publisher and an uninteresting target produce the same
        # silence, and an operator reading the second has read the first.
        #
        # `rk oob up` is what takes the control, and this is the same reader
        # `request_callback_correlator` asks -- the window is written down in
        # that function and in neither of its callers, so the operator's path
        # and the agent's cannot come to different answers about the same
        # channel.
        control = _decode(str(connection.execute(CONTROL_ARRIVAL, (channel,)).scalar()))
        if control.get("publishable") and not control.get("fresh"):
            ledger.fail(
                "callback_control",
                f"channel {channel} has no proof-of-life arrival inside the last "
                f"{control.get('window_seconds')} second(s) "
                f"({_unproved(control)}), so nothing failing to come back on it "
                f"would be a fact about {subject}; `rk oob up` takes one when "
                "it binds the name",
                code=INVALID_CONFIGURATION,
                source="argument:--channel",
            )
            return report(PROVISION, ledger, **facts)

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

    address = _address(endpoint.placement, host, correlator)
    facts["callback"] = {
        "channel": channel,
        "kind": endpoint.kind,
        "correlator_id": correlator_id,
        "address": address,
        "endpoint": host,
        "placement": endpoint.placement,
        "provider": endpoint.provider,
        "subject": subject,
        "subject_type": entity_type,
        "expires_at": expires,
        "lifetime_seconds": lifetime,
        "control": control,
    }
    ledger.hold(
        "callback",
        f"channel {channel} ({endpoint.kind}) is listening for {subject}: "
        f"embed {address}, live until {expires}{_vouched(control)}",
    )
    return report(PROVISION, ledger, **facts)


def _unproved(control: dict) -> str:
    """Why this channel is standing on nothing, in the reader's own words.

    The database says it when the answer is structural -- no binding, no control
    ever -- and says nothing when the control merely aged out, because a moment
    and an age are what it returned instead. This composes the second case and
    passes the first through untouched.
    """
    said = control.get("reason")
    if said:
        return str(said)
    return (
        f"{control.get('interaction')} arrived {control.get('age_seconds')} "
        "second(s) ago"
    )


def _vouched(control: dict) -> str:
    """What the reading this correlator produces may be read against.

    In the same sentence as the address, because the two are read together: an
    arrival refutes on its own, and no arrival is a finding only beside a
    control. A channel this harness does not publish gets the honest half of
    that -- there is no publisher of ours to take a control at, so silence on it
    stays the absence of a refutation rather than becoming one.
    """
    if not control.get("publishable"):
        return (
            "; this harness does not publish this channel, so no arrival on it "
            "is the absence of a refutation and not a refutation"
        )
    return (
        f"; {control.get('interaction')} arrived at {control.get('endpoint')} "
        f"{control.get('age_seconds')} second(s) ago, so nothing coming back is "
        "a reading about the subject rather than about this channel"
    )


def _address(placement: str, host: str, correlator: str) -> str:
    """The one string an operator embeds, for wherever this channel keeps its name.

    A label channel is addressed by name alone, because a DNS query carries no
    path and an HTTP request to `<correlator>.<endpoint>` carries the correlator
    in the name it resolved. A path channel is a URL: the endpoint is one host
    serving every canary, so the correlator is the first segment, and the
    trailing slash is there because the directory is what gets published.
    """
    if placement == "path":
        return f"https://{host}/{correlator}/"
    return f"{correlator}.{host}"


def accept(
    runtime: pg.Settings | None,
    configuration_path: Path,
    host: str,
    source: Path,
    *,
    root: Path,
    peer: str = "unknown",
    at: str | None = None,
    path: str | None = None,
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

    `path` is the request target the listener saw, for a channel that carries
    its correlator there rather than in a label. It is passed on exactly as
    received -- not lowercased, not decoded -- because it is part of what
    arrived, and the correlator is read from its first segment.
    """
    ledger = Ledger()
    facts: dict[str, object] = {"program_id": None, "callback": None}

    policy, slug = policy_for(ledger, configuration_path)
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
    if path is not None and not path.startswith("/"):
        ledger.fail(
            "callback_path",
            f"{path} is not a request target a listener saw; one begins at /",
            code=INVALID_CONFIGURATION,
            source="argument:--path",
        )
        return report(ACCEPT, ledger, **facts)

    data = _arrival(ledger, Path(source))
    if data is None:
        return report(ACCEPT, ledger, **facts)

    def unadmitted(reason: str) -> None:
        # Refused rather than filed. A declared channel compiles to an egress
        # rule as well, so for those this is the same answer the proxy gives;
        # a channel bound at run time compiles to no rule at all, and its name
        # is read from the bindings instead -- which is why this is written
        # once here and reached from both of the asks below.
        ledger.fail(
            "callback_channel",
            f"{observed} is not a name any channel {slug} declares admits ({reason})",
            code=INVALID_CONFIGURATION,
            source="argument:--host",
        )

    # Attribution is asked of the configuration first, and for every Program
    # whose channels are all declared it is answered here: an arrival at
    # somebody else's host, or at an endpoint carrying no correlator, is refused
    # before a connection exists, which is ticket 14's rule and the reason its
    # bytes are never stored. A channel whose name is bound at run time is the
    # one thing the configuration cannot settle -- the name is in the database
    # and nowhere else -- so only an arrival no declared channel admits, at a
    # Program that has such a channel, pays a connection to find out.
    verdict = scope.decide_callback(policy, observed)
    dynamic = any(entry.dynamic for entry in policy.channels)
    endpoint = policy.channel(verdict.channel) if verdict.allowed else None
    correlator = None
    if endpoint is not None:
        correlator = _correlator(ledger, observed, endpoint, {}, path)
        if correlator is None:
            return report(ACCEPT, ledger, **facts)
    elif not dynamic:
        unadmitted(verdict.reason)
        return report(ACCEPT, ledger, **facts)

    connection = migrate.open_connection(ledger, runtime)
    if connection is None:
        return report(ACCEPT, ledger, **facts)
    keep = Store(Path(root))
    with connection:
        program_id = open_program(ledger, connection, slug)
        if program_id is None:
            return report(ACCEPT, ledger, **facts)
        facts["program_id"] = program_id

        if endpoint is None:
            # And re-asked with the live names. Still before a byte is stored,
            # so an arrival at a name nobody bound leaves nothing behind either.
            bindings = _bindings(connection, policy)
            verdict = scope.decide_callback(policy, observed, bindings)
            if not verdict.allowed:
                unadmitted(verdict.reason)
                return report(ACCEPT, ledger, **facts)
            endpoint = policy.channel(verdict.channel)
            assert endpoint is not None  # named by the verdict just returned
            correlator = _correlator(ledger, observed, endpoint, bindings, path)
            if correlator is None:
                return report(ACCEPT, ledger, **facts)

        arrival = {
            "host": observed,
            "arrival_kind": endpoint.kind,
            "peer_class": peer,
            # Null when the caller stated no moment, which is how the writer is
            # told to file the arrival under the moment it accepted it.
            "received_at": received,
            # And null when the listener saw no request target, which is every
            # DNS query and every HTTP arrival on a label channel.
            "path": path,
        }
        try:
            answer, sha256, written = record(
                connection, keep, correlator, arrival, data, actor=f"rk {ACCEPT}"
            )
        except pg.DatabaseError as error:
            ledger.fail(
                "callback",
                f"the interaction was refused: {error}",
                code=INVALID_CONFIGURATION,
                source="database",
            )
            return report(ACCEPT, ledger, **facts)

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


def record(
    connection: pg.Connection,
    keep: Store,
    correlator: str,
    arrival: dict,
    data: bytes,
    *,
    actor: str,
) -> tuple[dict, str, bool]:
    """File one arrival: the bytes into the store, then the row through the writer.

    One transaction, and the bytes first, so no committed row names a file that
    was never stored -- `artifact put`'s rule, and the same one direction of skew
    an audit cannot repair. A refused arrival leaves its bytes filed under their
    own hash with nothing pointing at them, which no reader can reach.

    Shared by `accept` and by the publisher in `oob`, because they differ only in
    where the arrival came from: one is a recording an operator hands over, the
    other is a request this machine answered a moment ago. What is written, and
    the order it is written in, is the same question and gets one answer.

    Raises `pg.DatabaseError` when the writer refuses, because the reason is the
    database's sentence and the caller is the one with a ledger to put it in.
    """
    with connection.transaction():
        connection.execute("SELECT set_actor('runtime', $1)", (actor,))
        sha256, written = keep.put(data)
        registration = {
            "sha256": sha256,
            "byte_size": len(data),
            "content_type": _content_type(str(arrival["arrival_kind"])),
        }
        answer = connection.execute(
            RECORD, (correlator, _encode(arrival), _encode(registration))
        ).scalar()
    return _decode(str(answer)), sha256, written


def clear(
    runtime: pg.Settings | None,
    configuration_path: Path,
    correlator_id: str,
) -> Report:
    """End one correlator early, and say what it had already caught.

    By row id rather than by the address it was embedded in: the plaintext is
    not stored, and an operator ending a canary because a payload went somewhere
    it should not have is holding what `provision` printed. Ending one is
    idempotent -- a second call changes nothing and says so -- and a correlator
    this Program does not have is answered exactly as an id nobody minted,
    because the two must not be tellable apart.
    """
    ledger = Ledger()
    facts: dict[str, object] = {"program_id": None, "callback": None}

    identifier = _identifier(ledger, correlator_id)
    if identifier is None:
        return report(CLEAR, ledger, **facts)

    policy, slug = policy_for(ledger, configuration_path)
    if policy is None or slug is None:
        return report(CLEAR, ledger, **facts)

    connection = migrate.open_connection(ledger, runtime)
    if connection is None:
        return report(CLEAR, ledger, **facts)
    with connection:
        program_id = open_program(ledger, connection, slug)
        if program_id is None:
            return report(CLEAR, ledger, **facts)
        facts["program_id"] = program_id

        with connection.transaction():
            connection.execute("SELECT set_actor('runtime', $1)", (f"rk {CLEAR}",))
            try:
                ended = connection.execute(END_CORRELATOR, (identifier,)).scalar()
            except pg.DatabaseError as error:
                # The same shape `accept` uses, for the same reason: a database
                # that refused is a refusal an operator can read, and letting it
                # out of here would be reported as the command having stopped
                # part-way -- the sentence reserved for what nobody enumerated.
                ledger.fail(
                    "callback",
                    f"the correlator was not ended: {error}",
                    code=INVALID_CONFIGURATION,
                    source="database",
                )
                return report(CLEAR, ledger, **facts)

    answer = _decode(str(ended))
    cleared = bool(answer.get("cleared"))
    known = bool(answer.get("known"))
    arrivals = int(answer.get("interactions", 0))
    facts["callback"] = {
        "correlator_id": identifier,
        "cleared": cleared,
        "known": known,
        "channel": answer.get("channel"),
        "interactions": arrivals,
    }
    # An operator ending a canary in a hurry is asking two things: is it over,
    # and did it already fire. The count is in every sentence that has one to
    # give, including the one for the second call, which is the call made after
    # a crash.
    if cleared:
        said = (
            f"{identifier} is ended on channel {answer.get('channel')}: it "
            f"admitted {arrivals} arrival(s) and will admit no more"
        )
    elif known:
        said = (
            f"{identifier} was already over on channel {answer.get('channel')}: "
            f"it admitted {arrivals} arrival(s) and this call changed nothing"
        )
    else:
        said = (
            f"{identifier} is not a correlator this Program minted: nothing was "
            "changed, and nothing is claimed about whose it is"
        )
    ledger.hold("callback", said)
    return report(CLEAR, ledger, **facts)


def policy_for(
    ledger: Ledger, configuration_path: Path
) -> tuple[scope.Policy | None, str | None]:
    """The compiled policy and the Program it names, or a refusal saying why not.

    Public because `oob` asks it too: a publisher and a canary read the same
    configuration to learn the same two things, and a second copy of this would
    be a second answer to "which Program is this" waiting to disagree.
    """
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


def open_program(ledger: Ledger, connection: pg.Connection, slug: str) -> str | None:
    """The open Program this slug names, with the session bound to it.

    Public for the same reason `policy_for` is: every verb that writes on a
    runtime connection has to bind `rk2.program_id` before it writes, because
    the row-level policies and the callback verbs all read `rk2_program()`, and
    a verb that forgot would be answered as though the Program had nothing.
    """
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


def _bindings(connection: pg.Connection, policy: scope.Policy) -> dict[str, str]:
    """What each bound channel of this Program is answering at right now.

    Only the bound ones are asked about: a static channel answers with the host
    already in the policy, so asking would be one round trip to be told what the
    configuration said. A channel with nothing bound is simply absent, which is
    what makes it admit nothing.
    """
    live: dict[str, str] = {}
    for channel in policy.channels:
        if not channel.dynamic:
            continue
        answer = _decode(str(connection.execute(BINDING, (channel.name,)).scalar()))
        if answer.get("bound"):
            live[channel.name] = str(answer["endpoint"])
    return live


def _correlator(
    ledger: Ledger,
    observed: str,
    endpoint: scope.Channel,
    bindings: dict[str, str],
    path: str | None,
) -> str | None:
    """The correlator the arrival carries, from wherever this channel keeps it.

    Two placements and one rule between them: the correlator is the part of the
    arrival the canary was addressed by, and everything around it is the
    target's business. Beneath a label endpoint that is the label immediately
    below it -- a resolver that queried `www.<correlator>.<endpoint>` reported
    one arrival on one canary, not a longer one. On a path endpoint it is the
    first segment, because one bound host serves every canary of the channel and
    the segment is what tells them apart.

    An arrival that carries a path on a label channel, or none on a path
    channel, is refused rather than read: the placement says where the
    correlator is, and reading one from somewhere else would be attributing an
    arrival by a rule nobody declared.
    """
    if (endpoint.placement == "path") != (path is not None):
        ledger.fail(
            "callback_correlator",
            f"channel {endpoint.name} carries its correlator in the "
            f"{endpoint.placement}, and this arrival "
            + ("states a request target" if path is not None else "states none"),
            code=INVALID_CONFIGURATION,
            source="argument:--path",
        )
        return None
    if endpoint.placement == "path":
        assert path is not None  # the agreement above
        # A target begins at `/`, so the split always has a second element and
        # it is empty exactly when the request named the root. The query is cut
        # first for the same reason the publisher cuts it: `/<correlator>?x=1`
        # is a request for that canary, and a correlator read with the query
        # still attached would match nothing that was ever minted.
        correlator = path.split("?", 1)[0].split("/")[1]
        if not correlator:
            ledger.fail(
                "callback_correlator",
                f"{path} names no first segment beneath {endpoint.endpoint(bindings)}, "
                "so it carries no correlator",
                code=INVALID_CONFIGURATION,
                source="argument:--path",
            )
            return None
        return correlator

    host = endpoint.endpoint(bindings)
    if observed == host:
        ledger.fail(
            "callback_correlator",
            f"{observed} is the channel endpoint itself and carries no correlator; "
            "an interaction nobody can attribute is not evidence",
            code=INVALID_CONFIGURATION,
            source="argument:--host",
        )
        return None
    assert host is not None  # `decide_callback` admitted this name on this channel
    prefix = observed[: -(len(host) + 1)]
    correlator = prefix.rsplit(".", 1)[-1]
    if not correlator:
        ledger.fail(
            "callback_correlator",
            f"{observed} carries no label beneath {host}",
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


def _identifier(ledger: Ledger, value: str) -> str | None:
    """The correlator row id, or a refusal that what was given is not one.

    Checked here so a mistyped id is an argument the operator can see named
    rather than a `22P02` from the cast. It is the id `provision` printed; the
    address the canary was embedded in is not stored and is not what this verb
    takes.

    Only the shape is checked, and a correlator's plaintext has that shape: it
    is 16 bytes of hex, which is a UUID with its dashes taken out. Nothing here
    can tell the two apart, so a plaintext handed to this verb reaches the
    database and comes back as the answer an id nobody minted gets. Refusing
    that shape would mean refusing ids that are real.

    What comes back is the canonical spelling rather than the argument, so the
    report names the id the database was asked about: `uuid.UUID` also reads
    braces, a `urn:uuid:` prefix and upper case, and a report echoing those back
    would name something no row is keyed by.
    """
    try:
        return str(uuid.UUID(value))
    except ValueError:
        ledger.fail(
            "callback_correlator",
            f"{value} is not a correlator id; the id is the one `rk callback "
            "provision` printed, and it is not the address that was embedded",
            code=INVALID_CONFIGURATION,
            source="argument:--correlator",
        )
        return None


def _encode(value: dict) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _decode(value: str) -> dict:
    decoded = json.loads(value)
    return decoded if isinstance(decoded, dict) else {}
