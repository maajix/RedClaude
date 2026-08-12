# 73 — State the cross-role subagent cap once

**What to build:** One statement of how many subagents may run at once, so the pre-tool gate and the scheduler cannot answer differently.

**Blocked by:** 23 — Offer and claim a deterministic Slate.

**Status:** ready-for-agent

- [ ] The cap the gate refuses at and the cap the scheduler ranks and claims under are the same number, from one source.
- [ ] Changing the number in that one place changes both, and a test proves it by changing it.
- [ ] Where the two counters count different populations, the difference is stated rather than left to two equal constants to hide.

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
