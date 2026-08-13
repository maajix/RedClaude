# 75 — Refuse a claim for the concurrency it would actually spend

**What to build:** Make `global_subagent_cap` gate the claims that start a subagent, so a validate or a report Task is not refused for concurrency it does not use.

**Blocked by:** nothing.

**Status:** ready-for-agent

- [ ] A Program at `max_concurrent_subagents` still claims a Task whose role runs as a session or a renderer.
- [ ] The Ranking pass and the claim agree on that, so a Task the slate offers is not refused the moment it is acted on.
- [ ] A test claims past the cap with a non-subagent kind, and fails if the cap comes back to refusing it.

## Why

`0023_scheduler_ranking.sql:917-922` counts, and refuses, without looking at
what the claim in front of it would start:

```sql
ELSIF (SELECT count(*) FROM tasks c
         JOIN effective_lane_capacity lc
           ON lc.program_id = c.program_id AND lc.kind = c.kind
         JOIN roles r ON r.role = lc.role
        WHERE c.program_id = p AND c.status IN ('claimed','running')
          AND r.runs_as = 'subagent') >= w.max_concurrent_subagents THEN
    v_reason := 'global_subagent_cap';
```

The count is over the Tasks already claimed or running. The candidate's own
role never enters it. So a Program holding three subagent Tasks refuses every
further claim of every kind -- including `validate`, whose validator holds a
session, and `report`, whose reporter is a renderer that spends no model at
all. `roles` (019) makes three of the five agent roles subagents, so three
concurrent hunts is not an unusual state to be in: it is the state the roster's
own cap of 3 describes as full.

`claimable_for`'s ranking-side arm (`:770-777`) has the same shape, so the two
agree -- the slate stops offering those Tasks too. That is why nothing has
failed: the scheduler is consistently refusing work it has the capacity for.

Found by `SlateClaimTest.arrange_model_and_effort` (PH2-71), which claims one
Task of every kind in one Program and could not get past the fourth:

```
23514: task T4 is no longer claimable: global_subagent_cap
```

The fixture closes each run before claiming the next, which frees the count and
says why; that workaround is a symptom, not the ticket.

## How

Not decided here. The reading that makes the current code right is "three
children at a time, whatever kind" -- but then the column is misnamed and the
renderer, which starts no child, should still be exempt. The reading the name
gives is that the cap belongs to the claims that add a subagent, which is one
predicate in two places:

- Ask the cap only when the claimed Task's own lane role runs as a subagent,
  in both `claim_task` and `claimable_for`. Cheapest, and leaves the count as
  it is.
- Or keep the cap on every claim and rename it to what it then means, plus a
  reason on `scheduler_weights` saying why a renderer counts against it.

Whichever is chosen, the two sites have to move together: a slate that offers a
Task the claim then refuses is what ticket 23 exists to prevent.
