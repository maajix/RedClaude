"""`rk artifact`: store bytes by their hash, read them back by a Program's label.

The store is one namespace keyed by the SHA-256 of the plaintext, shared by
every Program on the installation, and that is deliberate: the same bytes seen
twice are one copy. What is not shared is who may name them. A Program reaches
an artifact through a reference it holds -- a labelled row of
`artifact_references` -- and the policy on `artifacts` is that reachability, so
a hash on its own answers with nothing whether or not the bytes are there. That
is the difference ticket 06 is about: deduplicating storage is not
deduplicating access, and the second one is not a smaller version of the first.

Three verbs, and the connection each one uses is part of what it means:

* `put` runs as the runtime. It reads a file, files it under its hash, and
  records that this Program holds it. Storing the same plaintext twice is one
  artifact and one reference; storing it from two Programs is one artifact and
  two references.
* `get` runs as both, like `rk state`. The Program is resolved on the runtime
  connection, which can read the registry, and the label is resolved on the
  agent's, which cannot -- so the answer to "does this Program hold `AF3`" is
  produced under the isolation it claims rather than beside it. The bytes
  themselves are read and re-hashed by the runtime process, which is the half of
  the store the database cannot see.
* `audit` runs as the runtime and is where criterion 6 lives. A hash recorded in
  a row is only an integrity claim while something checks it against the bytes;
  `check_artifact_reachability()` holds the database's half of that and cannot
  reach the filesystem, so this verb walks the Program's references, reads every
  one of them, and reports the store unsound if any is missing or does not hash
  to the name it is filed under. `rk db verify --artifacts` asks the same
  question across every Program, so a store that fails it stops the gate rather
  than only this command.

Two more verbs are the credential-bearing half, and they are separate verbs
rather than flags on the first three because what they do is different in kind:

* `seal` takes the wire bytes and the redacted bytes and produces two artifacts.
  The redacted one is stored and referenced exactly as `put` would store it; the
  wire one is encrypted under a key derived for this Program, filed under the
  hash of its envelope, and given no reference at all -- a reference is an
  agent-reachable name, and the whole point of the wire artifact is that no
  session can name it. Neither view is derived from the other, so each hash
  describes exactly the bytes its party saw.
* `open` is the only thing that decrypts, and it refuses unless an operator says
  in the invocation that they meant to. It never returns plaintext in the report:
  a report is printed, logged and pasted, and §6 allows identifiers, lengths and
  digests into those places and nothing else. The bytes go to a file the caller
  names, and the report says where, how many and which hash. Every attempt, taken
  or refused, is a `secret_access_log` row.

Every read verifies the whole plaintext, including when the caller asked for a
range. Verifying only the bytes returned would make a corrupt artifact readable
in every window that misses the damage, which is a way of answering with
corrupted data and no sign of it.

The filesystem half lives in `store.py`, not here: `rk db verify` has to be able
to ask, and a command that runs through the gate cannot be what the gate imports.
The cryptography lives in `seal.py` for a second reason as well as that one --
it is over bytes and a key, it reaches no database, and the property that the
root secret never leaves the process is easier to hold when the module holding
it cannot open a connection.
"""

from __future__ import annotations

import hmac
import os
from dataclasses import dataclass
from pathlib import Path

from redkraken import config, migrate, pg, program, seal, state
from redkraken.outcome import (
    INTEGRITY_FAILED,
    INVALID_CONFIGURATION,
    Ledger,
    Report,
    report,
)
from redkraken.store import (
    DEFAULT_BYTES,
    ROOT_VARIABLE,
    Corrupt,
    Missing,
    Store,
    Window,
    carried,
    digest,
    path_for,
    root_from_environment,
    window,
)


#: Re-exported so `rk artifact` is one import for a caller and the split between
#: the record and the bytes stays an argument about layering rather than a thing
#: the command line has to know.
__all__ = [
    "AUDIT",
    "COMMAND",
    "DEFAULT_BYTES",
    "FACTS",
    "GET",
    "KEY_VARIABLE",
    "KINDS",
    "OPEN",
    "PUT",
    "ROOT_VARIABLE",
    "SEAL",
    "Corrupt",
    "Missing",
    "Store",
    "Window",
    "audit",
    "carried",
    "digest",
    "filed",
    "get",
    "holding",
    "holdings",
    "key_from_environment",
    "open_wire",
    "path_for",
    "put",
    "root_from_environment",
    "seal_wire",
    "window",
]


COMMAND = "artifact"

#: One name per verb, because an operator reading a refusal has to know which of
#: the five produced it and the report is the only place that says so.
PUT = f"{COMMAND} put"
GET = f"{COMMAND} get"
AUDIT = f"{COMMAND} audit"
SEAL = f"{COMMAND} seal"
OPEN = f"{COMMAND} open"

#: Re-exported beside the store root: the key is the second thing this command
#: needs that is not in the database, and an operator who moved one has not
#: necessarily moved the other.
KEY_VARIABLE = seal.KEY_VARIABLE
key_from_environment = seal.key_from_environment

#: Why a Program holds these bytes. The third component of the uniqueness rule,
#: so one file arriving as a tool's output and again as fetched source is two
#: references to one artifact rather than one reference with a lost distinction.
KINDS = ("runtime", "tool_output", "source")

#: What this command reports, on every path. `holdings` is the audit's answer
#: and `content` the read's; a verb with nothing to say under a key says null,
#: so an operator parses one document across all three.
FACTS = (
    "program_id",
    "program_slug",
    "artifact",
    "window",
    "content",
    "holdings",
    "seals",
    "released",
    "integrity",
)

#: The agent-facing read. One label, no hash, no Program: `v_artifacts` is what
#: row level security leaves the session, and the label resolves only through a
#: reference this Program holds.
HOLDING = (
    "SELECT label, kind, sha256, byte_size, content_type, created_at"
    "  FROM v_artifacts WHERE label = $1"
)

#: The operator's enumeration, on the runtime connection. This one does name a
#: Program, because the runtime is the role that owns the store and is not what
#: isolation is measured on.
HOLDINGS = (
    "SELECT x.label, x.kind, x.sha256, a.byte_size"
    "  FROM artifact_references x JOIN artifacts a ON a.sha256 = x.sha256"
    " WHERE x.program_id = $1::uuid ORDER BY x.label"
)

#: Storing is two writes and both are idempotent. The artifact is global and may
#: already be there because another Program stored the same bytes; the reference
#: is this Program's and may already be there because this Program did.
STORE = (
    "INSERT INTO artifacts (sha256, byte_size, content_type, visibility)"
    " VALUES ($1, $2, $3, 'agent_visible') ON CONFLICT (sha256) DO NOTHING"
)
REFER = (
    "INSERT INTO artifact_references (program_id, sha256, kind)"
    " VALUES ($1::uuid, $2, $3) ON CONFLICT (program_id, sha256, kind) DO NOTHING"
    " RETURNING label"
)
REFERENCE = (
    "SELECT label FROM artifact_references"
    " WHERE program_id = $1::uuid AND sha256 = $2 AND kind = $3"
)

#: The wire artifact. `encrypted` is stated rather than defaulted because the
#: table's own CHECK ties it to `visibility`, and a row that relied on the
#: default would be a row asserting one of the two and hoping for the other.
STORE_SEALED = (
    "INSERT INTO artifacts (sha256, byte_size, content_type, visibility, encrypted)"
    " VALUES ($1, $2, $3, 'credential_bearing', true) ON CONFLICT (sha256) DO NOTHING"
)

#: One seal per plaintext hash, and the conflict is not silently absorbed: two
#: Programs sealing identical wire bytes would be one row describing a ciphertext
#: only one of them can open, so the second is refused rather than deduplicated.
#: Re-sealing the same bytes for the same Program is refused for the same reason
#: from the other direction -- the row is immutable and a fresh nonce would make
#: it describe a ciphertext that is no longer the one on disk.
INSCRIBE = (
    "INSERT INTO artifact_seal"
    " (sha256, scope_kind, scope_id, visibility, byte_size, alg, nonce, kek_gen,"
    "  ciphertext_sha256, agent_sha256)"
    " VALUES ($1, 'program', $2::uuid, 'credential_bearing', $3::bigint, $4, $5::bytea,"
    "  $6::integer, $7, $8) ON CONFLICT (sha256) DO NOTHING RETURNING sha256"
)

#: The seal behind one agent-visible label. The Program is in the query twice --
#: on the reference and on the seal's own scope -- so a label another Program
#: holds answers with nothing rather than with someone else's ciphertext.
SEALED = (
    "SELECT x.label, s.sha256, s.alg, encode(s.nonce, 'hex'), s.kek_gen,"
    "       s.ciphertext_sha256, a.byte_size"
    "  FROM artifact_seal s"
    "  JOIN artifact_references x"
    "    ON x.program_id = s.scope_id AND x.sha256 = s.agent_sha256"
    "  JOIN artifacts a ON a.sha256 = s.sha256"
    " WHERE s.scope_kind = 'program' AND s.scope_id = $1::uuid AND x.label = $2"
)

#: Every seal this Program holds, for the audit. The label is the agent view's,
#: because that is the only name for the pair an operator ever sees.
SEALS = (
    "SELECT x.label, s.sha256, s.alg, s.kek_gen, s.ciphertext_sha256, a.byte_size"
    "  FROM artifact_seal s"
    "  JOIN artifact_references x"
    "    ON x.program_id = s.scope_id AND x.sha256 = s.agent_sha256"
    "  JOIN artifacts a ON a.sha256 = s.sha256"
    " WHERE s.scope_kind = 'program' AND s.scope_id = $1::uuid ORDER BY x.label"
)

#: The key generation in force, and the two values that are safe to keep beside
#: it: a random salt and an HMAC output. Neither is key material.
GENERATION = (
    "SELECT gen, encode(salt, 'hex'), encode(root_check, 'hex') FROM secret_kek"
    " WHERE retired_at IS NULL ORDER BY gen DESC LIMIT 1"
)
GENERATIONS = "SELECT count(*) FROM secret_kek"
GENERATION_BY = (
    "SELECT encode(salt, 'hex'), encode(root_check, 'hex') FROM secret_kek"
    " WHERE gen = $1::integer"
)
FIRST_GENERATION = (
    "INSERT INTO secret_kek (gen, salt, root_check) VALUES (1, $1::bytea, $2::bytea)"
)

#: The audit row, written on every attempt including the refused ones. `peer_pid`,
#: `peer_uid` and `peer_exe` stay null on purpose: they exist to record what a
#: keyholder reads off SO_PEERCRED about somebody else, and a process writing
#: them about itself would be recording a claim it could have made up.
ACCESS = (
    "INSERT INTO secret_access_log"
    " (verb, scope_kind, scope_id, kek_gen, program_id, field, value_len, value_fpr,"
    "  outcome, detail)"
    " VALUES ($1, 'program', $2::uuid, $3::integer, $2::uuid, $4, $5::integer,"
    "  $6::bytea, $7, $8)"
)

#: What the audit row is about. One value, because there is one field this
#: command ever handles: the whole wire message.
FIELD = "wire_artifact"


def holding(connection: pg.Connection, label: str) -> dict | None:
    """One artifact this Program holds, by label, or nothing at all.

    Nothing at all is the answer for a label this Program never held and for a
    label another Program holds right now, including when both name the same
    bytes. Not by a check: the query is the same query, and the second case is a
    row row level security did not return.
    """
    rows = connection.execute(HOLDING, (label,)).rows
    if not rows:
        return None
    found, kind, sha256, byte_size, content_type, created_at = rows[0]
    return {
        "label": str(found),
        "kind": str(kind),
        "sha256": str(sha256),
        "byte_size": int(byte_size),
        "content_type": None if content_type is None else str(content_type),
        "created_at": str(created_at),
    }


def holdings(connection: pg.Connection, program_id: str) -> list[dict]:
    """Every reference one Program holds, for the operator's audit."""
    return [
        {
            "label": str(label),
            "kind": str(kind),
            "sha256": str(sha256),
            "byte_size": int(byte_size),
        }
        for label, kind, sha256, byte_size in connection.execute(
            HOLDINGS, (program_id,)
        ).rows
    ]


def filed(
    connection: pg.Connection,
    keep: Store,
    program_id: str,
    data: bytes,
    *,
    kind: str,
    content_type: str | None = None,
) -> dict:
    """File these bytes under their hash and record that this Program holds them.

    The order is the one thing this function exists to state once: the bytes go
    down first, so no committed row ever names a file that was never written --
    the one direction of skew `audit` cannot repair. The other direction is left
    alone on purpose. A failed insert leaves the bytes filed under their own hash
    and nothing else, which no reader can reach and which the next caller storing
    the same plaintext adopts; deleting them on the way out would be a race,
    since another process may already have committed a reference to exactly these
    bytes.

    Both writes are idempotent, and they are idempotent for different reasons.
    The artifact is global and may already be there because another Program
    stored the same bytes; the reference is this Program's and may already be
    there because this Program did.
    """
    sha256, written = keep.put(data)
    connection.execute(STORE, (sha256, len(data), content_type))
    rows = connection.execute(REFER, (program_id, sha256, kind)).rows
    label = str(
        rows[0][0]
        if rows
        else connection.execute(REFERENCE, (program_id, sha256, kind)).scalar()
    )
    return {
        "label": label,
        "kind": kind,
        "sha256": sha256,
        "byte_size": len(data),
        "content_type": content_type,
        "stored": written,
        "referenced": bool(rows),
    }


def put(
    runtime: pg.Settings,
    configuration_path: Path,
    source: Path,
    *,
    root: Path,
    kind: str = "runtime",
    content_type: str | None = None,
) -> Report:
    """Store one file's bytes and record that this Program holds them."""
    ledger = Ledger()
    answers = _Answers(PUT)

    slug = _configuration(ledger, answers, configuration_path)
    if slug is None:
        return _report(ledger, answers)
    if kind not in KINDS:
        ledger.fail(
            "kind",
            f"{kind} is not a reference kind; one of {', '.join(KINDS)}",
            code=INVALID_CONFIGURATION,
            source="argument:--kind",
        )
        return _report(ledger, answers)

    data = _source(ledger, source)
    if data is None:
        return _report(ledger, answers)
    ledger.hold(
        "source", f"{len(data)} byte(s) from {Path(source).name}, sha256 {digest(data)[:12]}"
    )

    connection = migrate.open_connection(ledger, runtime)
    if connection is None:
        return _report(ledger, answers)

    keep = Store(Path(root))
    with connection:
        program.assert_runtime_connection(ledger, connection)
        if ledger.violations:
            return _report(ledger, answers)
        program_id = _program(ledger, answers, connection, slug)
        if program_id is None:
            return _report(ledger, answers)

        with connection.transaction():
            connection.execute("SELECT set_actor('runtime', $1)", (f"rk {PUT}",))
            answers.artifact = filed(
                connection, keep, program_id, data, kind=kind, content_type=content_type
            )

    record = answers.artifact
    ledger.hold(
        "artifact",
        f"{record['label']} names {record['sha256'][:12]}: "
        + ("bytes written" if record["stored"] else "bytes already in the store")
        + (", reference created" if record["referenced"] else ", reference already held"),
    )
    answers.integrity = _verify(ledger, keep, [answers.artifact])
    return _report(ledger, answers)


def get(
    runtime: pg.Settings,
    agent: pg.Settings,
    configuration_path: Path,
    *,
    root: Path,
    label: str,
    offset: int = 0,
    limit: int | None = DEFAULT_BYTES,
) -> Report:
    """Read one artifact this Program holds, bounded, as the agent connection sees it."""
    ledger = Ledger()
    answers = _Answers(GET)

    slug = _configuration(ledger, answers, configuration_path)
    if slug is None:
        return _report(ledger, answers)

    # The identifier crosses here, once, and in this direction only, for the
    # reason `rk state` gives: the runtime knows which Program the operator's
    # file names, and the agent connection is told by having its session bound.
    connection = migrate.open_connection(ledger, runtime)
    if connection is None:
        return _report(ledger, answers)
    with connection:
        program_id = _program(ledger, answers, connection, slug)
        if program_id is None:
            return _report(ledger, answers)

    session = migrate.open_connection(ledger, agent)
    if session is None:
        return _report(ledger, answers)
    with session:
        if not state.assert_agent_connection(ledger, session):
            return _report(ledger, answers)
        with session.transaction():
            session.execute("SET TRANSACTION READ ONLY")
            if not state.bind_agent_session(ledger, session, program_id):
                return _report(ledger, answers)
            found = holding(session, label)

    if found is None:
        # The same answer, and the same exit code, for a label nobody holds and
        # for a label the other Program holds. Nothing below this line runs, so
        # there is no second observation for the two cases to differ in.
        answers.artifact = {"label": label, "present": False}
        ledger.hold("artifact", f"{label} is not an artifact of this Program")
        return _report(ledger, answers)

    answers.artifact = {"present": True, **found}
    try:
        view = window(found["byte_size"], offset=offset, limit=limit)
    except ValueError as error:
        ledger.fail("window", str(error), code=INVALID_CONFIGURATION, source="argument:--offset")
        return _report(ledger, answers)

    keep = Store(Path(root))
    try:
        chunk = keep.read(found["sha256"], view)
    except (Missing, Corrupt) as error:
        # Fail closed and say the store is unsound. A partial answer here would
        # be an answer nothing in the database can be trusted about afterwards.
        answers.integrity = {
            "sound": False,
            "verified": 0,
            "broken": [{"label": found["label"], "detail": str(error)}],
            "root": str(keep.root),
        }
        ledger.fail(
            "integrity",
            f"{found['label']} cannot be read: {error}",
            code=INTEGRITY_FAILED,
            source="artifact_store",
        )
        return _report(ledger, answers)

    answers.window = view.summary()
    answers.content = carried(chunk)
    answers.integrity = {"sound": True, "verified": 1, "broken": [], "root": str(keep.root)}
    ledger.hold(
        "artifact",
        f"{found['label']} is {found['byte_size']} byte(s); "
        f"{view.length} returned, {view.omitted_before + view.omitted_after} omitted",
    )
    return _report(ledger, answers)


def audit(runtime: pg.Settings, configuration_path: Path, *, root: Path) -> Report:
    """Check every artifact this Program holds against the bytes behind it.

    The database records a hash and can never check one: the bytes are on a
    filesystem no SQL statement reaches. So this is the verb that makes the
    integrity claim in `artifact_references.sha256` mean something, and a store
    that fails it makes every check depending on those hashes unsound rather
    than merely noisy.

    Sealed wire artifacts are audited beside the references, and no key is
    involved: the envelope is filed under the hash of the envelope, so checking
    that the ciphertext is the ciphertext the row names is the same arithmetic as
    checking any other artifact. Whether it still decrypts is `open`'s question,
    and asking it here would mean this verb had to hold the key.
    """
    ledger = Ledger()
    answers = _Answers(AUDIT)

    slug = _configuration(ledger, answers, configuration_path)
    if slug is None:
        return _report(ledger, answers)

    connection = migrate.open_connection(ledger, runtime)
    if connection is None:
        return _report(ledger, answers)
    with connection:
        program.assert_runtime_connection(ledger, connection)
        if ledger.violations:
            return _report(ledger, answers)
        program_id = _program(ledger, answers, connection, slug)
        if program_id is None:
            return _report(ledger, answers)
        held = holdings(connection, program_id)
        sealed = _seals(connection, program_id)

    answers.holdings = held
    answers.seals = sealed
    answers.integrity = _verify(
        ledger,
        Store(Path(root)),
        held
        + [
            {"label": f"{item['label']}/wire", "sha256": item["ciphertext_sha256"]}
            for item in sealed
        ],
    )
    return _report(ledger, answers)


def seal_wire(
    runtime: pg.Settings,
    configuration_path: Path,
    wire: Path,
    redacted: Path,
    *,
    root: Path,
    key: Path,
    content_type: str | None = None,
) -> Report:
    """Store one exchange as two artifacts: the redacted view, and the wire view encrypted.

    The order of the two is the order `put` established and for the same reason:
    bytes before rows, and nothing taken back up. What is added is that the wire
    bytes never exist in the store as plaintext at all -- the envelope is what is
    written, and it is filed under its own hash, so `rk db verify --artifacts` can
    check it without holding the key that opens it.
    """
    ledger = Ledger()
    answers = _Answers(SEAL)

    slug = _configuration(ledger, answers, configuration_path)
    if slug is None:
        return _report(ledger, answers)

    root_secret = _secret(ledger, key)
    if root_secret is None:
        return _report(ledger, answers)

    plaintext = _source(ledger, wire, flag="--wire")
    if plaintext is None:
        return _report(ledger, answers)
    visible = _source(ledger, redacted, flag="--redacted")
    if visible is None:
        return _report(ledger, answers)
    if visible == plaintext:
        # The pair would be one artifact twice, and the table says so: the two
        # hashes are the same hash, which the seal's own CHECK refuses. Refusing
        # here says which argument to change.
        ledger.fail(
            "redaction",
            "the redacted view is byte-for-byte the wire view; there are not two views to keep apart",
            code=INVALID_CONFIGURATION,
            source="argument:--redacted",
        )
        return _report(ledger, answers)

    connection = migrate.open_connection(ledger, runtime)
    if connection is None:
        return _report(ledger, answers)

    keep = Store(Path(root))
    wire_sha = digest(plaintext)
    with connection:
        program.assert_runtime_connection(ledger, connection)
        if ledger.violations:
            return _report(ledger, answers)
        program_id = _program(ledger, answers, connection, slug)
        if program_id is None:
            return _report(ledger, answers)

        keying = _keying(ledger, connection, root_secret, program_id)
        if keying is None:
            return _report(ledger, answers)

        if connection.execute("SELECT 1 FROM artifact_seal WHERE sha256 = $1", (wire_sha,)).rows:
            return _refuse_seal(
                ledger, answers, connection, program_id, root_secret, keying, plaintext
            )

        sealed = seal.seal(
            keying.key,
            plaintext,
            aad=seal.associated_data(
                program_id=program_id, sha256=wire_sha, generation=keying.generation
            ),
        )
        envelope = sealed.encode()

        try:
            with connection.transaction():
                connection.execute("SELECT set_actor('runtime', $1)", (f"rk {SEAL}",))
                agent = filed(
                    connection,
                    keep,
                    program_id,
                    visible,
                    kind="runtime",
                    content_type=content_type,
                )
                agent_sha = agent["sha256"]
                ciphertext_sha, wire_written = keep.put(envelope)
                connection.execute(STORE_SEALED, (wire_sha, len(plaintext), content_type))
                if not connection.execute(
                    INSCRIBE,
                    (
                        wire_sha,
                        program_id,
                        len(plaintext),
                        sealed.alg,
                        sealed.nonce,
                        keying.generation,
                        ciphertext_sha,
                        agent_sha,
                    ),
                ).rows:
                    raise _Contested
                _access(
                    connection,
                    "seal",
                    program_id,
                    generation=keying.generation,
                    outcome="ok",
                    detail=f"{agent['label']} pairs with sealed wire artifact {wire_sha}",
                    length=len(plaintext),
                    fingerprint=root_secret.fingerprint(plaintext),
                )
        except _Contested:
            # Someone else sealed the same bytes between the check above and this
            # insert. The same refusal, from the losing side of a race -- and the
            # envelope goes with it. Ticket 06's rule is that bytes are never
            # taken back up, because another writer may already have committed a
            # reference to them; that reasoning does not reach a ciphertext. This
            # one was sealed under a nonce drawn a moment ago, so no other writer
            # can arrive at its hash, no row will ever name it, and leaving it
            # would be an unreferenceable file no check can reach and no purge
            # can collect.
            if wire_written:
                keep.discard(ciphertext_sha)
            return _refuse_seal(
                ledger, answers, connection, program_id, root_secret, keying, plaintext
            )

    answers.artifact = agent
    label = agent["label"]
    answers.seals = [
        {
            "label": label,
            "sha256": wire_sha,
            "alg": sealed.alg,
            "kek_gen": keying.generation,
            "nonce": sealed.nonce.hex(),
            "ciphertext_sha256": ciphertext_sha,
            "byte_size": len(plaintext),
            "stored": wire_written,
        }
    ]
    ledger.hold(
        "seal",
        f"{label} is {len(visible)} agent-visible byte(s); the wire view is "
        f"{len(plaintext)} byte(s) sealed under {sealed.alg} as {ciphertext_sha[:12]}",
    )
    answers.integrity = _verify(
        ledger,
        keep,
        [
            {"label": label, "sha256": agent_sha},
            {"label": f"{label}/wire", "sha256": ciphertext_sha},
        ],
    )
    return _report(ledger, answers)


def open_wire(
    runtime: pg.Settings,
    configuration_path: Path,
    *,
    root: Path,
    key: Path,
    label: str,
    into: Path,
    authorize: str | None = None,
) -> Report:
    """Decrypt one wire artifact, once, deliberately, and to a file rather than to a report.

    Criterion 5 has two halves and both are here. "Explicitly authorized" is
    `--authorize`, carrying the operator's reason: without it the command refuses
    before it reads any key material, and the refusal is recorded. "Audited" is a
    `secret_access_log` row on every outcome, carrying the length and a keyed
    fingerprint of the plaintext and never the plaintext -- enough to answer
    whether the value released here is the one that turned up somewhere else, and
    not enough to reconstruct it.

    The bytes leave through the file the caller names, never through the report.
    A report is printed to a terminal, redirected into a log and pasted into a
    ticket, which is precisely the set of places §6 says a credential may not
    reach.
    """
    ledger = Ledger()
    answers = _Answers(OPEN)

    slug = _configuration(ledger, answers, configuration_path)
    if slug is None:
        return _report(ledger, answers)

    root_secret = _secret(ledger, key)
    if root_secret is None:
        return _report(ledger, answers)

    connection = migrate.open_connection(ledger, runtime)
    if connection is None:
        return _report(ledger, answers)

    with connection:
        program.assert_runtime_connection(ledger, connection)
        if ledger.violations:
            return _report(ledger, answers)
        program_id = _program(ledger, answers, connection, slug)
        if program_id is None:
            return _report(ledger, answers)

        # Authorization is decided before the lookup, so an unauthorized caller
        # learns nothing about which labels have a seal behind them.
        if not (authorize or "").strip():
            _access(
                connection,
                "open",
                program_id,
                outcome="denied",
                detail=f"no authorization given for {label}",
            )
            ledger.fail(
                "authorization",
                "opening a wire artifact needs --authorize with the reason it is being opened",
                code=INVALID_CONFIGURATION,
                source="argument:--authorize",
            )
            return _report(ledger, answers)

        rows = connection.execute(SEALED, (program_id, label)).rows
        if not rows:
            # The same answer for a label nobody holds, a label another Program
            # holds, and a label whose artifact was never sealed.
            _access(
                connection,
                "open",
                program_id,
                outcome="denied",
                detail=f"{label} names no sealed artifact of this Program",
            )
            answers.artifact = {"label": label, "present": False}
            ledger.hold("artifact", f"{label} names no sealed artifact of this Program")
            return _report(ledger, answers)

        found, wire_sha, alg, nonce, generation, ciphertext_sha, byte_size = rows[0]
        answers.artifact = {
            "present": True,
            "label": str(found),
            "sha256": str(wire_sha),
            "alg": str(alg),
            "kek_gen": int(generation),
            "nonce": str(nonce),
            "ciphertext_sha256": str(ciphertext_sha),
            "byte_size": int(byte_size),
        }

        keying = _keying(ledger, connection, root_secret, program_id, generation=int(generation))
        if keying is None:
            # `_keying` has already said which of the two it was -- a generation
            # that is gone, or a key file that is not this installation's -- so
            # the trail records the attempt and adds no second verdict.
            return _refuse_open(
                ledger,
                answers,
                connection,
                program_id,
                generation=int(generation),
                recorded="key material does not match the generation this seal names",
            )

        try:
            envelope = Store(Path(root)).load(str(ciphertext_sha))
        except (Missing, Corrupt) as error:
            answers.integrity = {
                "sound": False,
                "verified": 0,
                "broken": [{"label": f"{found}/wire", "detail": str(error)}],
                "root": str(root),
            }
            return _refuse_open(
                ledger,
                answers,
                connection,
                program_id,
                generation=int(generation),
                recorded=f"the sealed bytes cannot be read: {error}",
                name="integrity",
                detail=f"{found} cannot be opened: {error}",
            )

        try:
            envelope_seal = seal.Sealed.decode(envelope)
            if not envelope_seal.describes(alg, nonce):
                # The record and the bytes disagree about what this ciphertext
                # is. Nothing is decrypted on that, because the recorded
                # description is what the audit trail says was released.
                raise seal.Tampered(
                    "the recorded algorithm and nonce are not the ones in the sealed bytes"
                )
            plaintext = seal.unseal(
                keying.key,
                envelope_seal,
                aad=seal.associated_data(
                    program_id=program_id, sha256=str(wire_sha), generation=int(generation)
                ),
            )
            if digest(plaintext) != str(wire_sha):
                raise seal.Tampered("the opened bytes are not the plaintext this seal names")
        except seal.Tampered as error:
            return _refuse_open(
                ledger,
                answers,
                connection,
                program_id,
                generation=int(generation),
                recorded=str(error),
                name="integrity",
                detail=f"{found} does not authenticate: {error}",
            )

        # The audit row goes down before the bytes do. Each of these is its own
        # statement, so a failure between them leaves one of two states, and only
        # one of them is acceptable: a recorded open whose file never appeared is
        # an over-report an operator can dismiss, while plaintext on disk that
        # the trail does not account for is the thing §5 exists to prevent. The
        # release failing after this row is recorded too, so the pair reads as
        # what happened rather than as a contradiction.
        _access(
            connection,
            "open",
            program_id,
            generation=int(generation),
            outcome="ok",
            detail=f"{found} released to a file: {authorize}",
            length=len(plaintext),
            fingerprint=root_secret.fingerprint(plaintext),
        )
        try:
            written = _release(Path(into), plaintext)
        except OSError as error:
            return _refuse_open(
                ledger,
                answers,
                connection,
                program_id,
                generation=int(generation),
                recorded=f"the plaintext could not be written out: {error}",
                name="released",
                detail=f"the plaintext could not be written to {Path(into).name}: {error}",
                code=INVALID_CONFIGURATION,
                source="argument:--into",
            )

    answers.released = {
        "path": str(written),
        "byte_size": len(plaintext),
        "sha256": str(wire_sha),
        "fingerprint": root_secret.fingerprint(plaintext).hex(),
        "authorized": authorize,
    }
    answers.integrity = {"sound": True, "verified": 1, "broken": [], "root": str(root)}
    ledger.hold(
        "released",
        f"{found} opened under generation {generation}: {len(plaintext)} byte(s) "
        f"written to {written.name}, audited, and not in this report",
    )
    return _report(ledger, answers)


@dataclass
class _Answers:
    """What the command has established so far, in report terms."""

    command: str
    slug: str | None = None
    program_id: str | None = None
    artifact: dict | None = None
    window: dict | None = None
    content: dict | None = None
    holdings: list | None = None
    seals: list | None = None
    released: dict | None = None
    integrity: dict | None = None


def _report(ledger: Ledger, answers: _Answers) -> Report:
    return report(
        answers.command,
        ledger,
        program_id=answers.program_id,
        program_slug=answers.slug,
        artifact=answers.artifact,
        window=answers.window,
        content=answers.content,
        holdings=answers.holdings,
        seals=answers.seals,
        released=answers.released,
        integrity=answers.integrity,
    )


def _configuration(ledger: Ledger, answers: _Answers, path: Path) -> str | None:
    """The Program's slug, or a refusal that never reached a database."""
    configuration, refusals = config.load(Path(path))
    if configuration is None:
        ledger.refuse("configuration", f"refused by {len(refusals)} violation(s)", refusals)
        return None
    answers.slug = configuration.document["program"]["name"]
    ledger.hold("configuration", f"{answers.slug}, schema {configuration.schema_version}")
    return answers.slug


def _program(
    ledger: Ledger, answers: _Answers, connection: pg.Connection, slug: str
) -> str | None:
    """The Program this configuration names, kept where the report can see it."""
    answers.program_id = program.resolve(ledger, connection, slug)
    return answers.program_id


def _source(ledger: Ledger, source: Path, *, flag: str = "--from") -> bytes | None:
    """The plaintext, or a refusal that never reached a database."""
    try:
        return Path(source).read_bytes()
    except OSError as error:
        ledger.fail(
            "source",
            f"cannot read {Path(source).name}: {error}",
            code=INVALID_CONFIGURATION,
            source=f"argument:{flag}",
        )
        return None


def _secret(ledger: Ledger, key: Path) -> seal.Root | None:
    """The root secret, or a refusal that never reached a database.

    `seal.load_root` refuses a key file this process will not use -- missing, not
    a regular file, readable by anyone but its owner, or too short to be a key.
    Those are configuration problems and they are reported as configuration
    problems, before a connection is opened, because a key file the group can
    read is a key file that has to be replaced rather than retried.
    """
    try:
        return seal.load_root(Path(key))
    except seal.Unusable as error:
        ledger.fail(
            "key", str(error), code=INVALID_CONFIGURATION, source="argument:--key"
        )
        return None


@dataclass(frozen=True)
class _Keying:
    """The generation in force and the Program key derived under it."""

    generation: int
    key: bytes


class _Contested(Exception):
    """Another process sealed these bytes first; roll back and refuse."""


def _keying(
    ledger: Ledger,
    connection: pg.Connection,
    root: seal.Root,
    program_id: str,
    *,
    generation: int | None = None,
) -> _Keying | None:
    """Resolve the key generation and derive this Program's key under it.

    Two things happen here and the order matters. The generation carries a random
    salt and a check value, and the check value is compared against one derived
    from the key material this process actually holds -- so a wrong key file is
    caught here, against a value stored for exactly this purpose, rather than
    later against a ciphertext. Sealing with the wrong key would produce an
    envelope nothing can open; opening with it would produce an authentication
    failure that reads like corruption. Neither is the true answer, which is that
    the operator handed over the wrong file.

    Nothing key-shaped is stored by any of this. The salt is random, the check is
    16 bytes of an HMAC output, and the key is derived from the root secret every
    time it is needed.
    """
    if generation is None:
        rows = connection.execute(GENERATION).rows
        if not rows:
            if int(connection.execute(GENERATIONS).scalar() or 0):
                # Every generation retired and no successor. Rotation is not this
                # command's business, so it says so instead of inventing one.
                ledger.fail(
                    "key",
                    "every key generation is retired; a successor has to be established"
                    " before wire artifacts can be sealed again",
                    code=INVALID_CONFIGURATION,
                    source="secret_kek",
                )
                return None
            salt = seal.new_salt()
            connection.execute(FIRST_GENERATION, (salt, root.check(salt, generation=1)))
            ledger.hold(
                "key",
                "generation 1 established: a random salt and a check value, and no key"
                " material, are what the database holds",
            )
            return _Keying(1, root.program_key(salt, generation=1, program_id=program_id))
        found, salt_hex, check_hex = rows[0]
        generation = int(found)
    else:
        rows = connection.execute(GENERATION_BY, (generation,)).rows
        if not rows:
            ledger.fail(
                "key",
                f"this artifact names key generation {generation}, which no longer exists",
                code=INVALID_CONFIGURATION,
                source="secret_kek",
            )
            return None
        salt_hex, check_hex = rows[0]

    salt = bytes.fromhex(str(salt_hex))
    if not hmac.compare_digest(root.check(salt, generation=generation), bytes.fromhex(str(check_hex))):
        ledger.fail(
            "key",
            f"the key file does not match key generation {generation}"
            " recorded on this installation",
            code=INVALID_CONFIGURATION,
            source="argument:--key",
        )
        return None
    ledger.hold("key", f"the key file matches key generation {generation}")
    return _Keying(
        generation, root.program_key(salt, generation=generation, program_id=program_id)
    )


def _seals(connection: pg.Connection, program_id: str) -> list[dict]:
    """Every sealed wire artifact this Program holds, described and not opened."""
    return [
        {
            "label": str(label),
            "sha256": str(sha256),
            "alg": str(alg),
            "kek_gen": int(generation),
            "ciphertext_sha256": str(ciphertext_sha256),
            "byte_size": int(byte_size),
        }
        for label, sha256, alg, generation, ciphertext_sha256, byte_size in connection.execute(
            SEALS, (program_id,)
        ).rows
    ]


def _access(
    connection: pg.Connection,
    verb: str,
    program_id: str,
    *,
    outcome: str,
    detail: str,
    generation: int | None = None,
    length: int | None = None,
    fingerprint: bytes | None = None,
) -> None:
    """Record one attempt on key material, whatever became of it.

    Refusals are logged as loudly as successes, and for the more useful reason:
    an audit trail with only the successes in it answers "who opened this" and
    cannot answer "who tried". The value never appears -- what is kept is its
    length and a keyed fingerprint, which is enough to recognise the same value
    turning up elsewhere and not enough to reconstruct it.

    No `set_actor` precedes this, unlike every other write in this module. The
    row is the audit record itself: `0030_corpus_corrections.sql` classifies
    `secret_access_log` as `audit` rather than registering it with the emitter,
    so it carries no `emit_event` trigger and nothing here would read the actor.
    More to the point, most of these rows are written on a path that has just
    refused to do anything -- outside any transaction, with nothing else to
    attribute -- and a refusal that could not be recorded because it had declared
    no writer would be the one outcome missing from the trail.
    """
    connection.execute(
        ACCESS,
        (
            verb,
            program_id,
            generation,
            FIELD,
            length,
            fingerprint,
            outcome,
            detail,
        ),
    )


def _release(into: Path, plaintext: bytes) -> Path:
    """Write the opened bytes to a file only this user can read, refusing to clobber.

    `O_EXCL` rather than a truncating open, because the caller naming a path that
    already exists is more likely to be a mistake than an instruction, and the
    mistake destroys evidence. The mode is set at creation, not afterwards, so
    the bytes are never briefly readable by anyone else.
    """
    handle = os.open(into, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(handle, plaintext)
    finally:
        os.close(handle)
    return into


def _refuse_open(
    ledger: Ledger,
    answers: _Answers,
    connection: pg.Connection,
    program_id: str,
    *,
    generation: int | None,
    recorded: str,
    name: str | None = None,
    detail: str = "",
    code: int = INTEGRITY_FAILED,
    source: str = "artifact_store",
) -> Report:
    """Refuse an open, record the attempt, and return nothing of the plaintext.

    Every way this command can fail once it has been authorized ends here, and
    the order is the point: the audit row is written before the refusal is
    composed, so an outcome the operator never sees is still an outcome the trail
    holds. `recorded` is what the trail says happened; `name` and `detail` are
    what the operator is told, and `name` is None where the refusal is already in
    the ledger because something further down decided it.
    """
    _access(
        connection,
        "open",
        program_id,
        generation=generation,
        outcome="error",
        detail=recorded,
    )
    if name is not None:
        ledger.fail(name, detail, code=code, source=source)
    return _report(ledger, answers)


def _refuse_seal(
    ledger: Ledger,
    answers: _Answers,
    connection: pg.Connection,
    program_id: str,
    root: seal.Root,
    keying: _Keying,
    plaintext: bytes,
) -> Report:
    """Refuse to seal bytes that already carry a seal, and record the attempt."""
    _access(
        connection,
        "seal",
        program_id,
        generation=keying.generation,
        outcome="denied",
        detail=f"{digest(plaintext)} already carries a seal",
        length=len(plaintext),
        fingerprint=root.fingerprint(plaintext),
    )
    ledger.fail(
        "seal",
        "these wire bytes already carry a seal; the record is immutable and"
        " re-sealing them would describe a ciphertext that is not the one stored",
        code=INVALID_CONFIGURATION,
        source="argument:--wire",
    )
    return _report(ledger, answers)


def _verify(ledger: Ledger, keep: Store, held: list[dict]) -> dict:
    """Read every artifact named here and hold its hash against its bytes."""
    answer = keep.verify(held)
    broken = answer["broken"]
    if broken:
        ledger.fail(
            "integrity",
            f"{len(broken)} of {len(held)} artifact(s) cannot be verified: "
            + "; ".join(f"{item['label']} ({item['detail']})" for item in broken),
            code=INTEGRITY_FAILED,
            source="artifact_store",
        )
    else:
        ledger.hold(
            "integrity", f"{len(held)} artifact(s) hash to the identifier recorded for them"
        )
    return answer
