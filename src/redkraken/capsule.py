"""The bounded capsule a rotated orchestrator session resumes from.

Ticket 28: an orchestrator session has hard ceilings, and when it reaches one it
is closed and replaced. The replacement starts with no transcript -- the closed
session's turns are rows in `agent_runs`, not objects in this process, and a
supervisor that died between passes leaves not even that -- so everything the
next session needs to carry on has to be recompiled from the database. This
module is that recompile.

Five sections, and they are the five the ticket names: where the Program stands,
what the campaign has left to spend, whether the state is sound, what is running
right now, and what may be chosen next. Nothing else. A capsule that carried the
previous session's reasoning would be a transcript by another name, and a
transcript is exactly what a rotation does not preserve.

It is `packet.py`'s problem in a second shape, so it is `packet.py`'s primitives:
`Row`, `Section`, `Limits`, `fit` and `bound`. Two documents cross the boundary
into one child -- the mission packet a Task-holding role reads its world from,
and the capsule a planning session resumes from -- and one fitter answers both.
The rule that comes with them comes too: digests are computed in SQL and never
in Python, so a capsule row can be re-checked against the database that produced
it rather than against a second hash somebody wrote here.

Two sections are built from values this process already holds rather than from a
read of its own -- the integrity checks the pass ran, and the Slate the pass was
offered -- and they are digested by sending the records back to the server. That
is one statement, not a second implementation: `sha256(record::text)` is still
the definition, and `jsonb_array_elements` renders the same canonical text the
other three sections are hashed from.

The capsule is compiled on the runtime connection, unlike a packet, which is
compiled on the agent-scoped one. It has to be: `orchestrator_sessions`,
`program_capacity` and the Task queue are not on the state read surface, and the
session this describes is the one choosing between Programs' Tasks rather than
one reading inside a Task. So the Program is a parameter here and the whole
scope there, and every query says which Program it means.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from redkraken import integrity, packet, pg

#: The sections a capsule carries, in the order a resuming session reads them:
#: where it is, what it may spend, whether anything is broken, what is already
#: running, and only then what it may choose. The order is also the order rows
#: are gathered in for the fit, which is why the Slate is last -- it is the one
#: section the next pass recomputes from the database anyway.
SECTIONS = ("lifecycle", "budget", "integrity", "work", "slate")

#: How many times a capsule over its ceiling is compacted before it is refused.
#: The fit drops rows against a budget that leaves room for the document's own
#: framing, and each pass subtracts exactly the measured excess, so a capsule
#: converges in one or two. Four is the count at which "it is not converging"
#: is a better answer than another pass.
COMPACTIONS = 4


class CapsuleError(ValueError):
    """A capsule that cannot be built or is not one. Raised at the boundary."""


# ---------------------------------------------------------------------------
# The document
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Capsule:
    """One rotated session's inheritance, as one bounded document.

    `session` and `generation` are on it because they are what makes it this
    session's capsule rather than a snapshot of the Program: a resuming model is
    told which campaign it is continuing and how many have come before, which is
    the one piece of history a rotation does preserve.
    """

    session: str = ""
    generation: int = 1
    revision: int = 0
    limits: packet.Limits = field(default_factory=packet.Limits)
    sections: Mapping[str, packet.Section] = field(default_factory=dict)

    def section(self, name: str) -> packet.Section:
        return self.sections.get(name) or packet.Section(name=name, total=0)

    def rows(self) -> list[packet.Row]:
        return [row for name in SECTIONS for row in self.section(name).rows]

    def slate(self) -> list[dict]:
        """The Slate entries, as the records they were compiled from.

        The capsule is where the Slate crosses the boundary, so this is what the
        launcher builds the choice latch out of. One copy: a job document
        carrying both a capsule and a slate could be asked which one the model
        was actually offered, and there would be two answers.
        """
        return [dict(row.record) for row in self.section("slate").rows]

    def brief(self) -> dict:
        """The capsule as the objective states it: everything but the Slate.

        The Slate is dropped because a tool already serves it. Stating it here
        as well would put two copies of the entries in front of one model --
        one prose, one structured -- and the first thing a model does with two
        copies is prefer the one it read first. What it inherits has no such
        tool, so it is stated.
        """
        document = self.as_dict()
        document["sections"] = {
            name: body
            for name, body in document["sections"].items()
            if name != "slate"
        }
        return document

    @property
    def bytes(self) -> int:
        """What the whole document costs, framing included.

        The whole document and not the rows, because the ceiling is on what
        crosses the boundary. `packet.bound` measures rows so it can decide
        which to drop; this measures the thing that is actually sent, which is
        the number the refusal is made on.
        """
        return len(_encode(self.as_dict()))

    @property
    def tokens(self) -> int:
        """The document's size in the same approximate tokens `Limits` bounds."""
        return math.ceil(self.bytes / packet.BYTES_PER_TOKEN)

    def as_dict(self) -> dict:
        return {
            "session": self.session,
            "generation": self.generation,
            "revision": self.revision,
            "limits": self.limits.as_dict(),
            "sections": {name: _stated(self.section(name)) for name in SECTIONS},
        }

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> Capsule:
        """Rebuild a capsule inside the child, refusing anything that is not one.

        Same reason `packet.Packet.from_dict` refuses: the child has no database
        to check the document against, so the one thing it can check is that the
        shape is the shape it will index into, and a malformed capsule is a
        startup refusal rather than a `KeyError` three turns in.
        """
        try:
            return cls(
                session=str(document.get("session", "")),
                generation=int(document.get("generation", 1)),
                revision=int(document.get("revision", 0)),
                limits=packet.Limits.from_dict(dict(document.get("limits", {}))),
                sections={
                    name: packet.Section.from_dict(name, body)
                    for name, body in dict(document.get("sections", {})).items()
                    if name in SECTIONS
                },
            )
        except (AttributeError, KeyError, TypeError, ValueError) as error:
            raise CapsuleError(f"not a capsule: {error}") from error


def _stated(section: packet.Section) -> dict:
    """One section with its omission stated rather than left to be derived.

    `total` and the row count already imply it. Stating it anyway is the Spec's
    "omission markers": a model reading a section is being told what it is not
    seeing, and a subtraction it has to perform first is a subtraction it can
    decline to perform.
    """
    body = section.as_dict()
    body["omitted"] = max(section.total - len(section.rows), 0)
    return body


def _encode(document: Mapping[str, Any]) -> bytes:
    """The document as it goes out, which is the only form worth measuring."""
    return json.dumps(document, separators=(",", ":"), default=str).encode("utf-8")


# ---------------------------------------------------------------------------
# The reads
# ---------------------------------------------------------------------------

#: The Program's high-water Event sequence, which is the revision the capsule
#: as a whole was compiled at. Scoped by an argument rather than by row level
#: security, because the runtime connection sees every Program's rows.
REVISION = "SELECT coalesce(max(seq), 0) FROM events WHERE program_id = $1::uuid"

#: Where the Program stands. The halt is a left join and not a second read
#: because "no row" and "cleared" are the same standing to a resuming session,
#: and `coalesce` says so in the record instead of in Python.
#:
#: The Task counts are an aggregate rather than rows: a capsule that listed the
#: queue would be the full Task queue ticket 27 already refused to hand a model,
#: and what a planner needs from the queue it is not choosing from is its shape.
PROGRAM = (
    "SELECT p.slug,"
    "       rk2_revision('programs', p.id) AS revision,"
    "       encode(sha256(convert_to(rec::text, 'utf8')), 'hex') AS digest,"
    "       rec AS record"
    "  FROM programs p"
    "  LEFT JOIN program_halts h ON h.program_id = p.id"
    "  CROSS JOIN LATERAL (SELECT jsonb_build_object("
    "           'kind', 'program',"
    "           'slug', p.slug,"
    "           'name', p.name,"
    "           'platform', p.platform,"
    "           'scope_version', p.scope_version,"
    "           'opened_at', rk2_instant(p.opened_at),"
    "           'closed_at', rk2_instant(p.closed_at),"
    "           'halt', coalesce(h.status, 'clear'),"
    "           'halt_reason', h.reason,"
    "           'tasks', (SELECT coalesce(jsonb_object_agg(q.status, q.held), '{}'::jsonb)"
    "                       FROM (SELECT t.status, count(*) AS held FROM tasks t"
    "                              WHERE t.program_id = p.id GROUP BY t.status) q)"
    "       )) AS built(rec)"
    " WHERE p.id = $1::uuid"
)

#: The open campaign and what it has spent, from the view that derives both. The
#: predecessor's label comes along because a generation number alone does not
#: say what to read back: a session told it is generation 4 and given `OS3` can
#: ask the operator for one specific closed session's Events.
#:
#: Revision 0, like `packet.Row` says: `orchestrator_sessions` is registered as
#: bookkeeping in `event_table_exempt`, so its rows have no Event sequence of
#: their own to be stale against.
CAMPAIGN = (
    "SELECT u.label, 0 AS revision,"
    "       encode(sha256(convert_to(rec::text, 'utf8')), 'hex') AS digest,"
    "       rec AS record"
    "  FROM orchestrator_session_usage u"
    "  JOIN orchestrator_sessions s ON s.id = u.session_id"
    "  LEFT JOIN orchestrator_sessions prev ON prev.id = s.rotated_from"
    "  CROSS JOIN LATERAL (SELECT jsonb_build_object("
    "           'kind', 'session',"
    "           'label', u.label,"
    "           'generation', u.generation,"
    "           'rotated_from', prev.label,"
    "           'opened_at', rk2_instant(s.opened_at),"
    "           'turns', u.turns, 'max_turns', u.max_turns,"
    "           'tokens', u.tokens, 'max_tokens', u.max_tokens,"
    "           'decisions', u.decisions, 'max_decisions', u.max_decisions"
    "       )) AS built(rec)"
    " WHERE u.program_id = $1::uuid AND u.closed_at IS NULL"
)

#: What the Program may still promise, from the view the claim gate itself asks.
#: `run_tokens` is in it because that is the number a session's own next turn is
#: capped at, and a planner choosing work it cannot afford to dispatch is the
#: waste the whole budget apparatus exists to prevent.
CAPACITY = (
    "SELECT 'program' AS label, 0 AS revision,"
    "       encode(sha256(convert_to(rec::text, 'utf8')), 'hex') AS digest,"
    "       rec AS record"
    "  FROM program_capacity c"
    "  CROSS JOIN LATERAL (SELECT jsonb_build_object("
    "           'kind', 'capacity',"
    "           'token_budget', c.token_budget,"
    "           'tokens_spent', c.tokens_spent,"
    "           'tokens_reserved', c.tokens_reserved,"
    "           'tokens_free', c.tokens_free,"
    "           'run_tokens', c.run_tokens,"
    "           'request_budget', c.request_budget,"
    "           'requests_spent', c.requests_spent,"
    "           'requests_reserved', c.requests_reserved,"
    "           'requests_free', c.requests_free,"
    "           'run_requests', c.run_requests"
    "       )) AS built(rec)"
    " WHERE c.program_id = $1::uuid"
)

#: The same question per lane, because a Program with tokens left and one lane
#: exhausted can still only be worked in the other lanes, and a capsule that
#: reported only the Program total would let a session plan against a number no
#: claim of that kind can draw on.
LANES = (
    "SELECT l.kind AS label, 0 AS revision,"
    "       encode(sha256(convert_to(rec::text, 'utf8')), 'hex') AS digest,"
    "       rec AS record"
    "  FROM lane_budget l"
    "  CROSS JOIN LATERAL (SELECT jsonb_build_object("
    "           'kind', 'lane',"
    "           'lane', l.kind,"
    "           'token_budget', l.token_budget,"
    "           'tokens_spent', l.tokens_spent,"
    "           'tokens_reserved', l.tokens_reserved,"
    "           'tokens_free', l.tokens_free,"
    "           'request_budget', l.request_budget,"
    "           'requests_spent', l.requests_spent,"
    "           'requests_reserved', l.requests_reserved,"
    "           'requests_free', l.requests_free"
    "       )) AS built(rec)"
    " WHERE l.program_id = $1::uuid ORDER BY l.kind"
)

#: What is running right now, and the run and Lease it is running under. This is
#: the section a rotation exists for: the closed session started these attempts
#: and the replacement did not, so without it a resuming model sees a Program
#: with unaccountably fewer free slots than Tasks it would like to dispatch.
#:
#: The Agent run is a lateral rather than a join so a claimed Task whose child
#: has not started yet still describes one row -- the Lease is the Task's and
#: exists before the run does.
WORK = (
    "SELECT t.label,"
    "       rk2_revision('tasks', t.id) AS revision,"
    "       encode(sha256(convert_to(rec::text, 'utf8')), 'hex') AS digest,"
    "       rec AS record"
    "  FROM tasks t"
    "  LEFT JOIN LATERAL ("
    "       SELECT a.label, a.role, a.model, a.started_at"
    "         FROM agent_runs a"
    "        WHERE a.task_id = t.id AND a.finished_at IS NULL"
    "        ORDER BY a.started_at DESC LIMIT 1) live ON true"
    "  CROSS JOIN LATERAL (SELECT jsonb_build_object("
    "           'kind', 'work',"
    "           'task', t.label,"
    "           'task_kind', t.kind,"
    "           'status', t.status,"
    "           'attempts', t.attempts,"
    "           'priority', t.priority,"
    "           'claimed_at', rk2_instant(t.claimed_at),"
    "           'lease_expires_at', rk2_instant(t.lease_expires_at),"
    "           'agent_run', live.label,"
    "           'role', live.role,"
    "           'model', live.model,"
    "           'started_at', rk2_instant(live.started_at)"
    "       )) AS built(rec)"
    " WHERE t.program_id = $1::uuid AND t.status IN ('claimed', 'running')"
    " ORDER BY t.claimed_at NULLS LAST, t.label"
    " LIMIT $2"
)

WORK_COUNT = (
    "SELECT count(*) FROM tasks"
    " WHERE program_id = $1::uuid AND status IN ('claimed', 'running')"
)

#: The digest of records this process built, computed where every other digest
#: is computed. `value::text` is the same canonical rendering `rec::text` gives
#: the three read sections, so a row hashed here and a row hashed there are
#: hashed by one definition.
DIGESTS = (
    "SELECT ordinality::int AS at,"
    "       encode(sha256(convert_to(value::text, 'utf8')), 'hex') AS digest"
    "  FROM jsonb_array_elements($1::jsonb) WITH ORDINALITY"
    " ORDER BY ordinality"
)


# ---------------------------------------------------------------------------
# The compile
# ---------------------------------------------------------------------------


def compile(
    connection: pg.Connection,
    program_id: str,
    *,
    session: str = "",
    generation: int = 1,
    limits: packet.Limits | None = None,
    checks: Sequence[integrity.Check] | None = None,
    slate: Sequence[Mapping[str, object]] = (),
) -> Capsule:
    """Compile one session's capsule on the runtime connection.

    `checks` is what the pass already verified. Passing them is not an
    optimisation: `integrity.verify` runs at the top of every pass against the
    state this capsule describes, and a capsule that ran the standing checks a
    second time would quote a second answer about a moment nobody else saw. When
    no checks are given they are read here, because a section left empty would
    report a sound Program by saying nothing about it.

    `slate` is what the pass was offered, for the same reason: `offer_slate`
    consumes the outstanding Slate and writes a new one, so a capsule that read
    the Slate itself would either read the one this pass is about to hand out or
    quietly offer a second.
    """
    limits = limits or packet.Limits()
    if checks is None:
        checks = integrity.run(connection, families=(integrity.STANDING_FAMILY,))
    staged = {
        "lifecycle": _lifecycle(connection, program_id),
        "budget": _budget(connection, program_id),
        "integrity": _integrity(connection, checks),
        "work": _work(connection, program_id, limits.rows),
        "slate": _slate(connection, slate, limits.rows),
    }
    revision = int(_scalar(connection.execute(REVISION, (program_id,))))

    def build(sections: Mapping[str, packet.Section]) -> Capsule:
        return Capsule(
            session=session,
            generation=generation,
            revision=revision,
            limits=limits,
            sections={name: sections[name] for name in SECTIONS},
        )

    return _compacted(staged, limits, build)


def _compacted(
    staged: Mapping[str, packet.Section],
    limits: packet.Limits,
    build: Callable[[Mapping[str, packet.Section]], Capsule],
) -> Capsule:
    """Fit the capsule under its ceiling, or refuse to send one that is over.

    Criterion 6 names both halves -- "refused or further compacted" -- and they
    are one loop. `packet.bound` fits rows against a byte budget, but what the
    ceiling is on is the serialized document, which is the rows plus its own
    framing; so the budget starts one framing short and each pass subtracts the
    excess the last one actually measured.

    A capsule still over the ceiling with every row dropped is a ceiling smaller
    than the empty document, which no amount of compaction reaches. That is a
    configuration this cannot satisfy, and a refusal names it rather than
    starting a session against a bound the runtime quietly broke.
    """
    budget = limits.byte_ceiling - len(_encode(build(_emptied(staged)).as_dict()))
    for _ in range(COMPACTIONS):
        if budget < 0:
            break
        capsule = build(packet.bound(staged, byte_limit=budget, order=SECTIONS))
        excess = capsule.bytes - limits.byte_ceiling
        if excess <= 0:
            return capsule
        budget -= excess
    raise CapsuleError(
        f"the capsule does not fit: {limits.byte_ceiling} bytes "
        f"({limits.byte_limit} configured, {limits.token_limit} tokens) "
        f"leaves no room for the document itself"
    )


def _emptied(staged: Mapping[str, packet.Section]) -> dict[str, packet.Section]:
    """The same sections with no rows: what the framing alone costs."""
    return {
        name: packet.Section(name=name, total=section.total)
        for name, section in staged.items()
    }


def _lifecycle(connection: pg.Connection, program_id: str) -> packet.Section:
    rows = _read(connection, "lifecycle", PROGRAM, (program_id,))
    rows += _read(connection, "lifecycle", CAMPAIGN, (program_id,))
    return packet.Section(name="lifecycle", total=len(rows), rows=tuple(rows))


def _budget(connection: pg.Connection, program_id: str) -> packet.Section:
    rows = _read(connection, "budget", CAPACITY, (program_id,))
    rows += _read(connection, "budget", LANES, (program_id,))
    return packet.Section(name="budget", total=len(rows), rows=tuple(rows))


def _work(connection: pg.Connection, program_id: str, limit: int) -> packet.Section:
    rows = _read(connection, "work", WORK, (program_id, limit))
    total = int(_scalar(connection.execute(WORK_COUNT, (program_id,))))
    return packet.Section(name="work", total=total, rows=tuple(rows))


def _integrity(
    connection: pg.Connection, checks: Sequence[integrity.Check]
) -> packet.Section:
    """The state's standing, failures first.

    Failures first because `fit` drops from the tail: a capsule cut down to its
    last few integrity rows should be holding the ones that say something is
    wrong, and a section trimmed of exactly those would read as a sound Program.
    """
    ordered = sorted(checks, key=lambda check: (check.ok, check.family, check.name))
    records = [
        {
            "kind": "integrity",
            "family": check.family,
            "check": check.name,
            "ok": check.ok,
            "detail": check.detail,
        }
        for check in ordered
    ]
    rows = _staged(connection, "integrity", [check.source for check in ordered], records)
    return packet.Section(name="integrity", total=len(records), rows=tuple(rows))


def _slate(
    connection: pg.Connection, slate: Sequence[Mapping[str, object]], limit: int
) -> packet.Section:
    """The Slate this pass was offered, carried rather than re-read.

    Entries keep the names `offer_slate` gave them and the ordinal it ranked
    them by, with no record-kind marker added: an entry's `kind` is already the
    Task's kind, which is the word the choice is made on, and overwriting it to
    say "slate" would tell a model the section name has already told it. The
    label is the Task's, like every other row here, so a session citing an entry
    and a session citing the work it became are citing one name.
    """
    entries = [dict(entry) for entry in slate]
    kept = entries[:limit]
    labels = [str(entry.get("task", "")) for entry in kept]
    return packet.Section(
        name="slate",
        total=len(entries),
        rows=tuple(_staged(connection, "slate", labels, kept)),
    )


def _read(
    connection: pg.Connection, section: str, sql: str, parameters: Sequence[object]
) -> list[packet.Row]:
    """One section's rows from one statement, in the shape every section shares."""
    return [
        packet.Row(
            section=section,
            label=str(label),
            revision=int(revision),
            digest=str(digest),
            record=json.loads(str(record)),
        )
        for label, revision, digest, record in connection.execute(sql, parameters).rows
    ]


def _staged(
    connection: pg.Connection,
    section: str,
    labels: Sequence[str],
    records: Sequence[Mapping[str, object]],
) -> list[packet.Row]:
    """Rows this process built, digested by the server in one statement.

    Revision 0 for all of them, and for the same reason `packet.Row` gives: a
    check result and a Slate entry are not canonical rows and have no Event
    sequence to be stale against. What they are stale against is the capsule's
    own revision, which is on the document.
    """
    if not records:
        return []
    digests = connection.execute(DIGESTS, (json.dumps(list(records), default=str),)).rows
    if len(digests) != len(records):
        raise CapsuleError(
            f"the server digested {len(digests)} of {len(records)} {section} records"
        )
    return [
        packet.Row(
            section=section,
            label=label,
            revision=0,
            digest=str(digest),
            record=record,
        )
        for label, record, (_, digest) in zip(labels, records, digests, strict=True)
    ]


def _scalar(result: pg.Result) -> object:
    """The one value of a one-row read, or a refusal naming the read that missed."""
    if not result.rows:
        raise CapsuleError("the capsule read no row where it needs exactly one")
    return result.rows[0][0]
