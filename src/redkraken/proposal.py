"""One agent run's result, staged. The entire write an executing role can cause.

Spec section 13: an Agent submits one result "containing proposed Entities,
Relationships, Observations, Hypotheses, evidence edges, suggested Tasks and a
completion claim", and it "is staging data, not canonical truth". This module
is the second half of that sentence -- the part that makes it structurally true
rather than a convention the next handler could forget.

Three separate things make it true, and none of them relies on the other two.
The child has no database: `isolation.py` gives it one network whose only peer
is the capability proxy, so a handler inside the container has nothing to write
to. The roster refuses at compile time to let any model-facing contract write a
`CANONICAL` table. And here, the runtime's own write path touches `proposals`
and `proposal_drops` and no other relation.

What it does not do is judge. A proposal is staged whether or not its elements
survive provenance: an Observation citing a Receipt that does not exist is kept,
with a row saying which element was refused and why. Migration 0020 gives the
reason -- "a silent drop is indistinguishable from a thing the agent never
proposed" -- and grading an agent needs the difference.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from redkraken import pg

#: The status every row this module writes carries. There is no argument for
#: any other value here: `promoted` is the promotion step's word and `rejected`
#: is a decision about the whole proposal, which this is not making.
STAGED = "staged"

#: `proposals.completion`, from migration 0020's check constraint.
COMPLETIONS = ("complete", "partial", "unproven")

#: What a completion claim becomes when the model did not make one this schema
#: recognises. Unproven rather than partial: "the agent said nothing legible
#: about whether it finished" and "the agent said it half finished" are
#: different claims, and only one of them was made.
UNCLAIMED = "unproven"

#: `proposal_drops.reason`, from migration 0020's check constraint. Every one
#: of these is a statement the runtime can prove from a row; there is no
#: `looked_wrong`.
REASONS = (
    "no_such_receipt",
    "receipt_other_program",
    "receipt_proxy_internal",
    "receipt_other_run",
    "no_such_tool_run",
    "no_such_label",
    "label_other_program",
    "no_provenance",
)
#: Not every reason the column admits, and deliberately: a source citation that
#: does not hold is refused by a trigger on `proposals`, so those words are the
#: database's rather than this module's. `stage` reads back what the table holds
#: instead of listing them here, because a second copy of that vocabulary could
#: only ever be out of date.


# ---------------------------------------------------------------------------
# What the child sent
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Drop:
    """One element the runtime refused, and the reason it can prove."""

    ordinal: int
    element_path: str
    reason: str
    cited: str | None = None

    def as_dict(self) -> dict:
        return {
            "ordinal": self.ordinal,
            "element_path": self.element_path,
            "reason": self.reason,
            "cited": self.cited,
        }


@dataclass(frozen=True, slots=True)
class Result:
    """An agent run's result as the child returned it, before anything checked it."""

    payload: Mapping[str, Any] = field(default_factory=dict)

    @property
    def completion(self) -> str:
        """The claim, clamped to a word the column accepts.

        The contract closes `completion_claim` to a `status` and a `note`, but
        it does not close what the status says: the schema is checked by the
        CLI, `status` is a string there, and the column takes one of three
        words. Anything else is not a lenient parse away from being a claim of
        completeness; it is the absence of one.
        """
        claim = self.payload.get("completion_claim")
        if not isinstance(claim, Mapping):
            return UNCLAIMED
        stated = claim.get("status")
        return stated if stated in COMPLETIONS else UNCLAIMED

    def elements(self, name: str) -> list[Mapping[str, Any]]:
        """One element list, with anything that is not an object left out.

        The names are `submit_mission_result`'s argument names, which
        `roster.CONTRACTS` declares and this module does not re-list: a
        `proposal_drops.element_path` has to point at something the agent can
        find in what it sent, so a second copy of those names here is a second
        copy that could be right about a list the schema no longer accepts.

        Left out of the walk, not out of the payload: the payload is stored as
        it arrived. A string where an Observation belongs cites no provenance
        and cannot be checked for any, so it is not something this module has a
        reason to drop -- the promotion step is where a shapeless element stops
        being a candidate.
        """
        value = self.payload.get(name)
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            return []
        return [item for item in value if isinstance(item, Mapping)]


# ---------------------------------------------------------------------------
# The provenance check
# ---------------------------------------------------------------------------

#: A Receipt by label, across every Program. The `rk2_runtime` policy is
#: `USING (true)` -- migration 0020 -- which is what lets this tell "no such
#: Receipt" from "another Program's Receipt". A label is unique per Program and
#: not globally, so this can return more than one row and the Program is the
#: column that picks.
RECEIPT = (
    "SELECT r.program_id::text, r.lane, tr.agent_run_id::text"
    "  FROM receipts r LEFT JOIN tool_runs tr ON tr.id = r.tool_run_id"
    " WHERE r.label = $1"
)

TOOL_RUN = "SELECT program_id::text, agent_run_id::text FROM tool_runs WHERE label = $1"

ENTITY = "SELECT program_id::text FROM entities WHERE label = $1"


def review(
    connection: pg.Connection,
    result: Result,
    *,
    program_id: str,
    agent_run_id: str,
) -> list[Drop]:
    """Every Observation element whose provenance the runtime can disprove.

    Only Observations. The other five lists are proposals about things that do
    not exist yet -- a new Entity has no label, a Relationship names two
    Entities that may both be proposed beside it, and an evidence edge cites
    the Hypothesis proposed three keys above it -- so checking them against
    canonical rows would refuse exactly the elements an agent run is for. An
    Observation is the one element that is a claim about something that already
    happened, which is why migration 0007 makes the same demand of the
    canonical table.

    Which is also why the criterion this satisfies names Observations and only
    them: "Observation proposals referencing absent, foreign or incompatible
    provenance are retained as rejected staging outcomes". A Relationship that
    names another Program's Entity is refused by promotion, where the Entity it
    names either does or does not resolve.
    """
    drops: list[Drop] = []
    for ordinal, element in enumerate(result.elements("observations")):
        fault = _provenance(connection, element, program_id, agent_run_id)
        if fault is not None:
            reason, cited = fault
            drops.append(
                Drop(
                    ordinal=len(drops),
                    element_path=f"observations[{ordinal}]",
                    reason=reason,
                    cited=cited,
                )
            )
    return drops


def _provenance(
    connection: pg.Connection,
    element: Mapping[str, Any],
    program_id: str,
    agent_run_id: str,
) -> tuple[str, str | None] | None:
    """The one thing wrong with this element's provenance, or nothing.

    Exactly one provenance, which is migration 0007's rule for the canonical
    row: an Observation stands on a Receipt or on a Tool Run, and an element
    citing both is not twice as well evidenced -- it is ambiguous about which
    evidence it means.
    """
    receipt = _cited(element, "receipt_label")
    tool_run = _cited(element, "tool_run_label")
    if (receipt is None) == (tool_run is None):
        return "no_provenance", receipt or tool_run
    if receipt is not None:
        fault = _receipt_fault(connection, receipt, program_id, agent_run_id)
    else:
        fault = _tool_run_fault(connection, str(tool_run), program_id)
    if fault is not None:
        return fault, receipt or tool_run
    return _subject_fault(connection, element, program_id)


def _receipt_fault(
    connection: pg.Connection, label: str, program_id: str, agent_run_id: str
) -> str | None:
    rows = connection.execute(RECEIPT, (label,)).rows
    if not rows:
        return "no_such_receipt"
    mine = [row for row in rows if str(row[0]) == program_id]
    if not mine:
        return "receipt_other_program"
    lane, run = str(mine[0][1]), mine[0][2]
    if lane == "proxy_internal":
        return "receipt_proxy_internal"
    # A Receipt with no Tool Run behind it belongs to no run in particular, and
    # `receipt_other_run` is a claim about which run produced it. Unprovable is
    # not the same as false, so it is not a drop.
    if run is not None and str(run) != agent_run_id:
        return "receipt_other_run"
    return None


def _tool_run_fault(connection: pg.Connection, label: str, program_id: str) -> str | None:
    rows = connection.execute(TOOL_RUN, (label,)).rows
    if not rows:
        return "no_such_tool_run"
    if not any(str(row[0]) == program_id for row in rows):
        return "label_other_program"
    return None


def _subject_fault(
    connection: pg.Connection, element: Mapping[str, Any], program_id: str
) -> tuple[str, str | None] | None:
    """The Entity the Observation is about, if it says it is about a known one.

    An Observation may name no subject, or may name one this run is
    proposing in the same packet. Neither is a fault. Naming a label that
    resolves to another Program's row is, and it is the one case a Program
    boundary can be crossed by citation rather than by query.
    """
    subject = _cited(element, "subject_label")
    if subject is None:
        return None
    rows = connection.execute(ENTITY, (subject,)).rows
    if not rows:
        return None
    if not any(str(row[0]) == program_id for row in rows):
        return "label_other_program", subject
    return None


def _cited(element: Mapping[str, Any], key: str) -> str | None:
    value = element.get(key)
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


# ---------------------------------------------------------------------------
# The write
# ---------------------------------------------------------------------------

#: No `label` and no `status`. The label comes from the same `assign_label`
#: trigger every other labelled table uses, and the status comes from the
#: column default, which is `staged`. A caller that could pass either could
#: pass `promoted`.
INSERT = (
    "INSERT INTO proposals (program_id, agent_run_id, task_id, payload, completion)"
    " VALUES ($1::uuid, $2::uuid, $3::uuid, $4::jsonb, $5)"
    " RETURNING id::text, label, status"
)

INSERT_DROP = (
    "INSERT INTO proposal_drops"
    " (proposal_id, program_id, ordinal, element_path, reason, cited)"
    " VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6)"
)

#: Where this side's drops start. The database drops elements of its own the
#: moment the proposal lands -- an ungrounded source citation is refused by a
#: trigger, so that a promotion cannot be reached by not going through here --
#: and those rows are already numbered when this asks. The ordinal is a key
#: rather than a rank, so continuing the numbering is all this has to do.
NEXT_DROP = "SELECT coalesce(max(ordinal) + 1, 0) FROM proposal_drops WHERE proposal_id = $1::uuid"

#: Every element this proposal lost, whoever refused it. Read back rather than
#: assembled from what this module wrote, because a caller told only about the
#: half this side found would read a proposal as more accepted than it is.
DROPS = (
    "SELECT ordinal, element_path, reason, cited FROM proposal_drops"
    " WHERE proposal_id = $1::uuid ORDER BY ordinal"
)


@dataclass(frozen=True, slots=True)
class Staged:
    """The staging row that now exists, and what it did not accept."""

    proposal_id: str
    label: str
    status: str
    completion: str
    drops: tuple[Drop, ...] = ()

    def as_dict(self) -> dict:
        return {
            "proposal_id": self.proposal_id,
            "label": self.label,
            "status": self.status,
            "completion": self.completion,
            "drops": [drop.as_dict() for drop in self.drops],
        }


def stage(
    connection: pg.Connection,
    result: Result,
    *,
    program_id: str,
    agent_run_id: str,
    task_id: str,
) -> Staged:
    """Write one agent run's result as staging rows, and nothing else, ever.

    Two tables, one transaction. The transaction is not for speed: a proposal
    whose drops did not commit with it would read as a proposal that passed
    provenance, which is the one misreading these rows exist to prevent.

    Two writers, one table. What this side proves it reads off Receipts and Tool
    runs before the proposal exists; what the database proves it reads off the
    proposal itself, so it has to happen after. Both end in `proposal_drops`
    because that is the one seam every promotion walk already consults, and this
    side goes second: it continues the numbering rather than owning it, and what
    it returns is what the table holds rather than what it put there.
    """
    found = review(
        connection, result, program_id=program_id, agent_run_id=agent_run_id
    )
    with connection.transaction():
        rows = connection.execute(
            INSERT,
            (
                program_id,
                agent_run_id,
                task_id,
                json.dumps(dict(result.payload), separators=(",", ":")),
                result.completion,
            ),
        ).rows
        proposal_id, label, status = (str(value) for value in rows[0])
        base = int(connection.execute(NEXT_DROP, (proposal_id,)).scalar())
        for offset, drop in enumerate(found):
            connection.execute(
                INSERT_DROP,
                (
                    proposal_id,
                    program_id,
                    base + offset,
                    drop.element_path,
                    drop.reason,
                    drop.cited,
                ),
            )
        drops = tuple(
            Drop(
                ordinal=int(ordinal),
                element_path=str(path),
                reason=str(reason),
                cited=None if cited is None else str(cited),
            )
            for ordinal, path, reason, cited in connection.execute(DROPS, (proposal_id,)).rows
        )
    return Staged(
        proposal_id=proposal_id,
        label=label,
        status=status,
        completion=result.completion,
        drops=drops,
    )
