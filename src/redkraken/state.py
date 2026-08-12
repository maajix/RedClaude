"""`rk state`: read a Program's records by label, bounded, on the agent's own connection.

Every other command in this package talks to the database as the runtime. This
one exists to talk to it as the model does, and the difference is the point.
`rk2_state` owns nothing, may write nothing, cannot read the Program registry,
and sees exactly the rows row level security leaves it. What it is given
instead is a session bound to one Program, and from there the state is
reachable by label and by nothing else.

Three properties follow, and each is a privilege or a refusal rather than a
convention:

* No read verb takes a Program. The binding is `rk2.program_id` on the session,
  set once, from an identifier the runtime resolved on its own connection. A
  verb that accepted one would make isolation depend on every caller passing
  the right value. What the binding rests on is that the process holding the
  session sets it and the model never reaches the session: `rk2_state` may set
  the setting again, but nothing it can read yields another Program's
  identifier to set it to.
* An unknown label and another Program's label produce the same answer. They
  are the same answer because they are the same query: the row is not there,
  and nothing on this connection can ask a second question that would tell the
  two cases apart.
* A read is bounded and says what it left out. `bound` drops until the answer
  fits and reports the size of what was dropped, so a caller working from a
  compact read knows it is compact. The ceiling is over the record index, which
  is the part that grows with the Program; a full record asked for by name is
  the one thing a caller has already sized by asking for it.

Reads run in a read-only transaction. Criterion 6 asks that repeating a read
leave the database unchanged; the cheapest way to mean it is for a write to be
impossible rather than merely absent.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from redkraken import config, migrate, packet, pg, program
from redkraken.outcome import (
    INTEGRITY_FAILED,
    INVALID_CONFIGURATION,
    Ledger,
    Report,
    report,
)


COMMAND = "state"

#: The role this command must be, and the one thing it must not be able to do.
#: Asserted on the connection rather than trusted from the URL: an operator who
#: points `RK_STATE_URL` at the runtime would otherwise get a read that looks
#: identical and is not isolated by anything.
STATE_ROLE = "rk2_state"

#: The eight labelled record kinds `v_records` carries, in the order a report
#: names them. Fixed here as well as in the view so that a kind the database
#: stops returning reads as zero rather than as a missing key.
KINDS = (
    "entity",
    "finding",
    "hypothesis",
    "observation",
    "receipt",
    "task",
    "test",
    "tool_run",
)

#: How much state one read may carry. Rows first, per kind, so one large kind
#: cannot crowd out the others; then bytes, because rows are not the unit a
#: context window is spent in.
DEFAULT_RECORDS = 10
DEFAULT_BYTES = 8192

#: Everything the command reports. The same keys on every path: an operator
#: parses one document whether the read reached a Program or not.
FACTS = (
    "program_id",
    "program_slug",
    "limits",
    "state",
    "record",
)

#: The compact index, ranked so that a bounded read carries the part of the
#: state that moved most recently. No Program appears in it, and none can:
#: `v_records` is row level security's answer to the session it is asked on.
COMPACT = (
    "SELECT kind, label, revision, digest"
    "  FROM (SELECT kind, label, revision, digest,"
    "               row_number() OVER (PARTITION BY kind ORDER BY revision DESC, label) AS rank"
    "          FROM v_records) ranked"
    " WHERE rank <= $1"
    " ORDER BY kind, rank"
)

COUNTS = "SELECT kind, count(*) FROM v_records GROUP BY kind"

RECORD = "SELECT kind, revision, digest, record FROM v_records WHERE label = $1"

#: How much of the Program registry this connection can read, counted per
#: column rather than per table. `has_table_privilege` would answer "no" to a
#: role holding `SELECT (slug)`, and one readable column is enough to tell a
#: label nobody holds from a label another Program holds.
REGISTRY = (
    "SELECT count(*) FROM pg_attribute"
    " WHERE attrelid = 'programs'::regclass AND attnum > 0 AND NOT attisdropped"
    "   AND has_column_privilege(attrelid, attnum, 'SELECT')"
)


@dataclass(frozen=True)
class Entry:
    """One record as a compact read names it: what it is, and whether it moved."""

    kind: str
    label: str
    revision: int
    digest: str

    def summary(self) -> dict:
        return {
            "kind": self.kind,
            "label": self.label,
            "revision": self.revision,
            "digest": self.digest,
        }


@dataclass(frozen=True)
class Compact:
    """A bounded read, and the size of what it did not carry.

    `counts` is what the Program holds and comes from the database; `entries`
    is what survived both limits. The omission markers are the difference, so
    they cannot drift from either: a marker computed from anything else would
    be a second opinion about the same subtraction.
    """

    entries: tuple[Entry, ...]
    counts: Mapping[str, int]
    bytes: int

    def summary(self) -> dict:
        returned = _per_kind(self.entries)
        return {
            "records": [item.summary() for item in self.entries],
            "kinds": [
                {
                    "kind": kind,
                    "count": self.counts.get(kind, 0),
                    "returned": returned.get(kind, 0),
                    "omitted": self.counts.get(kind, 0) - returned.get(kind, 0),
                }
                for kind in KINDS
            ],
            "bytes": self.bytes,
        }


def bound(
    entries: Sequence[Entry], counts: Mapping[str, int], *, byte_limit: int
) -> Compact:
    """Fit the entries under the byte ceiling, dropping the stalest first.

    The rule itself is `packet.fit`, because the mission packet needs the same
    one and two implementations of "which row goes first" would eventually
    answer differently for an operator read and for an Agent's read of the same
    Program. What is local here is only the unit: this bounds compact entries
    by kind, and a packet bounds records by section.
    """
    remaining = packet.fit(
        entries, byte_limit=byte_limit, group=lambda entry: entry.kind, size=_size
    )
    return Compact(
        entries=tuple(remaining), counts=dict(counts), bytes=_size(remaining)
    )


def records(
    connection: pg.Connection,
    *,
    per_kind: int = DEFAULT_RECORDS,
    byte_limit: int = DEFAULT_BYTES,
) -> Compact:
    """The compact index of everything this session's Program holds."""
    entries = [
        Entry(kind=str(kind), label=str(label), revision=int(revision), digest=str(digest))
        for kind, label, revision, digest in connection.execute(COMPACT, (per_kind,)).rows
    ]
    counts = {str(kind): int(total) for kind, total in connection.execute(COUNTS).rows}
    return bound(entries, counts, byte_limit=byte_limit)


def record(connection: pg.Connection, label: str) -> dict | None:
    """One full record, by a label, or nothing at all.

    Nothing at all is the answer for a label this Program never held and for a
    label another Program holds right now. Not by a check: the query is the
    same query, and the second case is a row row level security did not return.
    """
    rows = connection.execute(RECORD, (label,)).rows
    if not rows:
        return None
    kind, revision, digest, document = rows[0]
    return {
        "label": label,
        "kind": str(kind),
        "revision": int(revision),
        "digest": str(digest),
        "document": json.loads(str(document)),
    }


def read(
    runtime: pg.Settings,
    agent: pg.Settings,
    configuration_path: Path,
    *,
    label: str | None = None,
    per_kind: int = DEFAULT_RECORDS,
    byte_limit: int = DEFAULT_BYTES,
) -> Report:
    """Read the Program this configuration names, as the agent connection sees it."""
    ledger = Ledger()
    state = _State(limits={"records_per_kind": per_kind, "bytes": byte_limit})

    configuration, refusals = config.load(Path(configuration_path))
    if configuration is None:
        ledger.refuse("configuration", f"refused by {len(refusals)} violation(s)", refusals)
        return _report(ledger, state)
    slug = configuration.document["program"]["name"]
    state.slug = slug
    ledger.hold("configuration", f"{slug}, schema {configuration.schema_version}")

    # The identifier crosses here, once, and in this direction only: the runtime
    # knows which Program the operator's file names, and the agent connection is
    # told by having its session bound. Nothing the agent asks afterwards names
    # a Program, and nothing it can ask would resolve one.
    connection = migrate.open_connection(ledger, runtime)
    if connection is None:
        return _report(ledger, state)
    with connection:
        state.program_id = program.resolve(ledger, connection, slug)
        if state.program_id is None:
            return _report(ledger, state)

    session = migrate.open_connection(ledger, agent)
    if session is None:
        return _report(ledger, state)
    with session:
        if not assert_agent_connection(ledger, session):
            return _report(ledger, state)
        with session.transaction():
            session.execute("SET TRANSACTION READ ONLY")
            if not bind_agent_session(ledger, session, state.program_id):
                return _report(ledger, state)

            compact = records(session, per_kind=per_kind, byte_limit=byte_limit)
            state.compact = compact.summary()
            if label is not None:
                state.record = _record_fact(ledger, session, label)

    total = sum(compact.counts.get(kind, 0) for kind in KINDS)
    ledger.hold(
        "state",
        f"{len(compact.entries)} of {total} record(s) in {compact.bytes} byte(s)",
    )
    return _report(ledger, state)


@dataclass
class _State:
    """What the read has established so far, in report terms."""

    limits: dict
    slug: str | None = None
    program_id: str | None = None
    compact: dict | None = None
    record: dict | None = None


def _report(ledger: Ledger, state: _State) -> Report:
    return report(
        COMMAND,
        ledger,
        program_id=state.program_id,
        program_slug=state.slug,
        limits=state.limits,
        state=state.compact,
        record=state.record,
    )


def assert_agent_connection(ledger: Ledger, session: pg.Connection) -> bool:
    """Refuse a connection that is not the one this command is about.

    Two properties, and the second is the one worth spending a query on. A
    connection that can read `programs` can tell a label nobody holds from a
    label another Program holds, by asking a second question — so a read that
    claims indistinguishable absence has to establish that it cannot.

    Public because `rk artifact get` makes the same claim about the same role,
    and two copies of "is this really the agent connection" would be two answers
    the day one of them is updated.
    """
    user = str(session.execute("SELECT current_user").scalar())
    if user != STATE_ROLE:
        ledger.fail(
            "state_connection",
            f"connected as {user}; this read is only meaningful as {STATE_ROLE}, "
            "whose isolation is enforced by row level security rather than by a query",
            code=INVALID_CONFIGURATION,
            source="database",
        )
        return False
    readable = int(session.execute(REGISTRY).scalar() or 0)
    if readable:
        ledger.fail(
            "state_connection",
            f"{user} can read {readable} column(s) of the Program registry, so an absent "
            "label and a foreign one are distinguishable from this connection; "
            "`rk db verify` names it",
            code=INTEGRITY_FAILED,
            source="database",
        )
        return False
    ledger.hold("state_connection", f"connected as {user}; the Program registry is unreadable")
    return True


def bind_agent_session(ledger: Ledger, session: pg.Connection, program_id: str) -> bool:
    """Tell the agent's session which Program it is, and check that it took.

    Called inside the caller's transaction, because `set_config(..., true)` is
    scoped to one and a binding that outlived it would be a Program the next
    statement inherits by accident. The read-back is not ceremony: if the setting
    did not land, `rk2_program()` is null, every policy denies, and the session
    would report an empty Program rather than a broken one -- which reads exactly
    like isolation working.

    Public for the same reason `assert_agent_connection` is: `rk state` and
    `rk artifact get` bind the same way, and the day the mechanism changes it
    should change in one place.
    """
    session.execute("SELECT set_config('rk2.program_id', $1, true)", (program_id,))
    bound = session.execute("SELECT rk2_program()::text").scalar()
    if str(bound) != program_id:
        ledger.fail(
            "program_binding",
            "the session did not bind to the Program; every read would be refused",
            code=INTEGRITY_FAILED,
            source="database",
        )
        return False
    ledger.hold("program_binding", "bound by session context; no read names a Program")
    return True


def _record_fact(ledger: Ledger, session: pg.Connection, label: str) -> dict:
    """One record by label, and the same answer for both ways of not having it."""
    found = record(session, label)
    if found is None:
        ledger.hold("record", f"{label} is not a record of this Program")
        return {"label": label, "present": False}
    ledger.hold("record", f"{label} is a {found['kind']} at revision {found['revision']}")
    return {"present": True, **found}


def _per_kind(entries: Sequence[Entry]) -> dict[str, int]:
    """How many entries each kind contributed, which is both limits' unit."""
    return Counter(item.kind for item in entries)


def _size(entries: Sequence[Entry]) -> int:
    """What the entries cost a caller, in the bytes they are sent as."""
    return packet.sent_bytes(entries, lambda item: item.summary())
