# 75 — Refuse a claim for the concurrency it would actually spend

**What to build:** Make `global_subagent_cap` gate the claims that start a subagent, so a validate or a report Task is not refused for concurrency it does not use.

**Blocked by:** nothing.

**Status:** resolved

**Reading on the How:** the first of the two options -- ask the cap only when the claimed
Task's own lane role runs as a subagent. The column's name and 73's comment already say
what the number bounds, and both populations it bounds are populations of subagents. The
count is untouched; only which claims have to answer to it.

- [x] A Program at `max_concurrent_subagents` still claims a Task whose role runs as a session or a renderer.
- [x] The Ranking pass and the claim agree on that, so a Task the slate offers is not refused the moment it is acted on.
- [x] A test claims past the cap with a non-subagent kind, and fails if the cap comes back to refusing it.

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

## Comments

Implemented on 2026-08-17.

`src/redkraken/migrations/20260907T000000Z__a_claim_is_refused_for_the_concurrency_it_would_spend.sql`,
`SlateClaimTest` and one `Control` in `tests/test_database.py`. No Python: `roster.Gate` counts a
different population -- one orchestrator session's outstanding delegations -- against the
same number, and that count is already a count of subagents, so nothing on that side of the
seam was measuring the wrong thing.

### One site, because 73 left one

The Why cites `0023_scheduler_ranking.sql:917-922` and `claimable_for`'s arm as two places
that have to move together. They are one place now: 73 folded `claim_task`'s own copy into
`claimable_for`, and `check_slate_claim()` fails a `rank_candidates` or a `claim_task` that
decides eligibility without asking it. So the offer and the claim move together here by
construction rather than by two edits made in step, which is what ticket 23 exists to
prevent. The live definition is `20260814T000000Z`, not 023 -- three files replace that
function between them, and the last one sorting is the one running.

### The guard is a predicate, not a branch

`subagent_started_for(t)` is a function of its own, in the shape and the naming `ready_for`,
`identity_held_for` and `skills_ungranted_for` are in: one question about one Task. It reads
`effective_lane_capacity` rather than `role_task_kinds`, though the two agree by
construction, because the count in the same `IF` reads the view -- one source for "the role
that runs this kind" is what keeps the guard and the count talking about the same
population. It is a second condition on the same `IF` rather than a nested one so that the
count and its bound stay a single statement, which is what `check_subagent_cap()` (73)
matches on: a cap compared against anything but `max_concurrent_subagents` fails that check,
and a guard that split the statement would have silently stopped being checked.

### What keeps the narrowing made

`check_subagent_cap_guard()`, registered as a standing check of this ticket's own rather
than as three arms added to 73's and 23's -- 026 states the reason where it added an arm to
its own: a check that has to be edited in a neighbour's file to cover a new function is a
check the next ticket forgets. Three arms. A function that bounds a claim by the count of
running subagents without asking `subagent_started_for` is the defect coming back, and it
would come back silently for the same reason it was silent the first time. The other two are
what the rest of the eligibility rule is already held to: 025's no-clock rule, because the
ranking filter runs this predicate now, and 23's arm (h), because the `REVOKE` is made once
and a later `CREATE OR REPLACE` that dropped and recreated the function would hand it back
to PUBLIC.

Every check the gate runs owes a negative control, and `NegativeControlTest` fails naming
any check that has none. This one's is the defect written back in: a function that counts
the running subagents, bounds them by the weights row, and asks that of every claim. It
passes 73's check, because the bound is the row; it fails this one, because the question is
asked of claims that add nothing to what is being counted.

### What the fixture stopped doing

`arrange_model_and_effort` (71) closed each run before claiming the next, and said in its
own docstring that the closing was a workaround for this defect. It closes nothing now: all
five kinds are claimed in one Program and left open, `subagents_open` records what each
claim was standing at (`recon` 0, `hunt` 1, `analyze` 2, `validate` 3, `report` 3) and reads
that count through `subagent_started_for` rather than through a second spelling of its join,
and the validate is taken at a count that equals the roster's cap. Every claim is made off a
Ranking pass of its own, which is criterion 2 asked five times: one slate taken before any
of this was claimed could agree with all five claims by being stale. With the guard removed the
arrangement does not merely refuse the fourth claim -- `offer_slate` drops the Task first,
so the claim fails `task T4 is not on the current slate`, which is the two halves agreeing
about the wrong answer and is exactly why nothing had failed before.
