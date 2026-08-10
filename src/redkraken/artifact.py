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

Every read verifies the whole plaintext, including when the caller asked for a
range. Verifying only the bytes returned would make a corrupt artifact readable
in every window that misses the damage, which is a way of answering with
corrupted data and no sign of it.

The filesystem half lives in `store.py`, not here: `rk db verify` has to be able
to ask, and a command that runs through the gate cannot be what the gate imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from redkraken import config, migrate, pg, program, state
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
    "KINDS",
    "PUT",
    "ROOT_VARIABLE",
    "Corrupt",
    "Missing",
    "Store",
    "Window",
    "audit",
    "carried",
    "digest",
    "get",
    "holding",
    "holdings",
    "path_for",
    "put",
    "root_from_environment",
    "window",
]


COMMAND = "artifact"

#: One name per verb, because an operator reading a refusal has to know which of
#: the three produced it and the report is the only place that says so.
PUT = f"{COMMAND} put"
GET = f"{COMMAND} get"
AUDIT = f"{COMMAND} audit"

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
            # The bytes go down first, so no committed row ever names a file
            # that was never written -- the one direction of skew `audit` cannot
            # repair. The other direction is left alone on purpose: a failed
            # insert leaves the bytes filed under their own hash and nothing
            # else, which no reader can reach and which the next `put` of the
            # same plaintext adopts. Deleting them on the way out would be a
            # race, since another process may already have committed a
            # reference to exactly these bytes.
            sha256, written = keep.put(data)
            connection.execute(STORE, (sha256, len(data), content_type))
            rows = connection.execute(REFER, (program_id, sha256, kind)).rows
            referenced = bool(rows)
            label = str(
                rows[0][0]
                if rows
                else connection.execute(REFERENCE, (program_id, sha256, kind)).scalar()
            )

    answers.artifact = {
        "label": label,
        "kind": kind,
        "sha256": sha256,
        "byte_size": len(data),
        "content_type": content_type,
        "stored": written,
        "referenced": referenced,
    }
    ledger.hold(
        "artifact",
        f"{label} names {sha256[:12]}: "
        + ("bytes written" if written else "bytes already in the store")
        + (", reference created" if referenced else ", reference already held"),
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

    answers.holdings = held
    answers.integrity = _verify(ledger, Store(Path(root)), held)
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


def _source(ledger: Ledger, source: Path) -> bytes | None:
    """The plaintext, or a refusal that never reached a database."""
    try:
        return Path(source).read_bytes()
    except OSError as error:
        ledger.fail(
            "source",
            f"cannot read {Path(source).name}: {error}",
            code=INVALID_CONFIGURATION,
            source="argument:--from",
        )
        return None


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
