# 73 — State the cross-role subagent cap once

**What to build:** One statement of how many subagents may run at once, so the pre-tool gate and the scheduler cannot answer differently.

**Blocked by:** 23 — Offer and claim a deterministic Slate.

**Status:** resolved

- [x] The cap the gate refuses at and the cap the scheduler ranks and claims under are the same number, from one source.
- [x] Changing the number in that one place changes both, and a test proves it by changing it.
- [x] Where the two counters count different populations, the difference is stated rather than left to two equal constants to hide.

## Why

The number 3 is written twice.

`src/redkraken/roster.py:661` holds `GLOBAL_SUBAGENTS = 3`, and the pre-tool gate
refuses a delegation once that many are outstanding
(`src/redkraken/roster.py:875-880`). `0019_role_kinds.sql:220-221` adds
`scheduler_weights.max_concurrent_subagents smallint NOT NULL DEFAULT 3`, which
`0023_scheduler_ranking.sql:777` filters candidates by, `0023:921` refuses a
claim by, and `0037_lane_quota.sql:794-795` bounds the sum of lane entitlements
against.

They are equal today by coincidence of both being 3, and one of them is a column
on a versioned weights row -- the whole point of which is that an operator sets
it per program. Raise it to 4 and the scheduler offers a fourth hunt, the
orchestrator delegates it, and the gate denies it: the Task is claimed, the run
row exists, and the child never starts. Lower it to 2 and the gate is dead code
that never fires.

The two counters are also not counting the same thing, which is worth stating
even after they share a source. The gate counts delegations outstanding inside
one orchestrator session, which is the SDK's concurrency and the machine's
containers. The scheduler counts `claimed` and `running` Tasks whose role is a
subagent, across the Program, which survives an orchestrator rotation. Those
populations differ during a rotation, and two constants that happen to match
make that look like agreement.

Ticket 18 left this alone deliberately: it compiled the roster and enforced it at
the tool call, and the constant was already there. Making the runtime read a
scheduler weight is a scheduler change.

## How

The database row is the one that can vary per Program and per weights version, so
it is the source and the runtime reads it -- the same direction ticket 18 already
took for the per-role numbers, where `roles.max_concurrent` is the roster's and
the schema-agreement test holds the two to each other.

The roster is a compile-time document and the weight is a runtime value, so the
honest shape is not a constant in `roster.py` at all: the `Gate` takes the cap
when the runtime constructs it, from the active `scheduler_weights` row it has
already read to claim the Task. `GLOBAL_SUBAGENTS` stays only as the default the
schema also defaults to, if a default is wanted at all.

Then say what each counter counts, next to where it is enforced, so the next
reader does not have to derive that the gate's population is a subset.

## Comments

Implemented on 2026-08-13. The number now travels: `execution.STARTED` reads
`max_concurrent_subagents` off the active weights row in the same transaction
as the claim, it lands on `Claimed.subagent_cap`, goes out on
`AgentRunRequest.subagent_cap` and then on the job document, and `_launch`
gives it to `roster.Gate(role, subagents)`. One migration,
`20260813T210000Z__state_the_cross_role_subagent_cap_once.sql`, adds no column
and changes no function: what it adds is the comment saying what the number
means on each side, and one standing check, `subagent_cap`.

### The shape the How named, and the constant that stayed

`GLOBAL_SUBAGENTS` is still there, and it is no longer a cap: it is the default
argument of `Gate.__init__` and the value `_launch._subagent_cap` falls back to
for a job carrying no cap. `SchemaAgreementTest` holds it equal to 019's
`DEFAULT 3` by reading the `ALTER TABLE` text, which is what makes the fallback
the schema's answer rather than a second opinion. A gate built without a cap is
now only reachable from a caller with no weights row to read; the runtime is
not one of those.

`Gate` also refuses a cap below 1, which is 019's own
`CHECK (max_concurrent_subagents >= 1)` restated where the number is spent. It
raises `RosterError`, the same exception an unknown role raises, so `_gate`
already turned it into "no gate" -- and no gate is no options value, which
`assess` refuses field by field. That path was checked rather than assumed: a
launch with no options value is refused by `_option_violations` on `env` alone,
so an unusable cap cannot reach the `assert gate is not None` below it.

### The claim's own transaction, not a second read

The cap is read by `STARTED`, which is the statement the runtime already runs
inside the claim's transaction to describe the run it just opened. A second
statement afterwards would be a second read of a row an operator can activate
between the two, and a child started under a cap no part of its own attempt was
scheduled by is the failure this ticket is about, one transaction later.
`execution.LEASE_TTL` is the precedent and not the model here: the TTL is read
once per pass and belongs to the pass, while the cap belongs to one claim.

### What the two counters count

The comment on the column says both populations, because that is where a reader
of either predicate ends up. The scheduler counts `claimed` and `running` Tasks
whose lane role runs as a subagent, across the Program and across orchestrator
rotations. The gate counts the delegations one session is holding, which is
that SDK's concurrency and that machine's containers. The session's population
is a subset of the Program's, which is why one number bounds both and why they
disagree during a rotation -- the old session's delegations are gone while its
Tasks are still claimed. The same sentence is on `roster.Gate`, for the reader
who arrives from the Python side.

### One arm, and the reason it is textual

`check_subagent_cap()` fires on a function body that counts concurrent
subagents and does not name `max_concurrent_subagents`. Textual for PH2-71's
reason in its third version: a bound compared against a literal that happens to
equal today's weights row is indistinguishable, row by row, from one that read
the row, and they differ on exactly the day an operator moves it. It matches
the counting subquery rather than `runs_as` alone, so a function that merely
tells subagent roles from session ones is not caught -- a check that fires on
honest code is one that gets worked around. Comments are stripped first, as
both of 71's arms do. The runtime's half cannot be checked from SQL at all;
`SchemaAgreementTest` and `tests/test_agent.py` are what hold that side.

### The test that moves the number

`SlateClaimTest.arrange_subagent_cap` is an eleventh Program, `capped`, with one
recon Task and one hunt Task offered on one slate before the row is touched.
With the cap at 1 and the recon claimed, the hunt is refused
`global_subagent_cap`; with the cap at 2 the same Task off the same slate is
taken. Both runs are read back through `execution.STARTED` itself, so what the
test asserts is the number the runtime would carry to a child, and
`roster.Gate` is then built from each one and refuses at it. The row is put
back to what the fixture found, and one test says so:
`scheduler_weights` is one global row, and a scenario that
moved it and left it would schedule every case after it, in this file and every
other, under a cap this fixture chose.

The refusal at cap 1 is also PH2-75 in passing: the count that refuses the hunt
is the recon's, and the arm would have refused a validate or a report the same
way. That defect is unchanged here -- this ticket moved where the number comes
from, not which claims are asked about it.
