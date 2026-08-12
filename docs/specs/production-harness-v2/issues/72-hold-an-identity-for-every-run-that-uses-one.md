# 72 — Hold an Identity for every run that uses one

**What to build:** Make `clamp_to_identity_leases` mean one thing at claim time, so a role the roster clamps cannot start a run that touches a target without holding the Identity it acts as.

**Blocked by:** 24 — Manage Task and Identity Leases through crashes.

**Status:** ready-for-agent

- [ ] A clamped role's run holds an identity lease for every Identity it will act as, including on a Task that names no hypothesis.
- [ ] Where a clamped Task cannot name the Identity it needs, the claim is refused rather than granted leaseless.
- [ ] `effective_lane_capacity.clamp_to_identity_leases` either bounds something or is gone from the view.
- [ ] A negative control claims two clamped Tasks that want the same Identity and proves the second does not start.

## Why

Ticket 18 wrote the clamp into the roster as a field because migration 0019
carries it as a column, and the roster says what it is for: "two hunters sharing
one upstream slot is the session mixing that the identity model exists to
prevent." `web_hunter` is the only role that sets it.

The scheduler enforces that in two places, and neither is keyed on the flag.
`ready_for()` refuses any Task whose hypothesis names an Identity somebody else
holds (`0023_scheduler_ranking.sql:424-431`), for every role, clamped or not.
`claim_task()` takes the leases at `0023_scheduler_ranking.sql:962`, under a
condition with a second half:

```sql
IF v_clamp AND v_task.hypothesis_id IS NOT NULL THEN
```

`tasks.hypothesis_id` is nullable (`0006_tasks_and_runs.sql:11`) and nothing
constrains a `hunt` Task to carry one, so a hunt Task with no hypothesis takes no
lease and passes no gate -- both halves of the clamp are hypothesis-shaped, and
the Task is not. Two such Tasks claim concurrently up to `max_concurrent = 2`
and reach the target through whatever upstream slot the proxy has, which is the
mixing the flag names.

The view side is the smaller half of the same confusion.
`effective_lane_capacity` selects `clamp_to_identity_leases`
(`0023_scheduler_ranking.sql:221`) and no query reads the column. Its own comment
says `max_slots` "is always the roster's per-role `max_concurrent`", so the
column sits in a capacity view without bounding capacity, next to a name that
says it does.

This is out of scope for ticket 18, which compiled and enforced the roster at the
tool call. The clamp is the scheduler's -- 18's job was to stop the roster and
0019 disagreeing about whether the flag is set, which is now under test.

## How

Decide first what a clamped role's Identity requirement is a property of, because
the two halves currently answer differently. Either it is the hypothesis, in
which case a clamped role may only hold hypothesis-bearing Tasks and the
constraint belongs on `tasks` where it can be checked; or it is the Task, in
which case a clamped Task carries the Identities it will act as in its own
column and `claim_task()` leases those.

The second is the one that matches the roster's sentence. A hunt against a
freshly reconned surface, before any hypothesis exists, is exactly the run that
most needs a session of its own.

Whichever is chosen, the failure has to be a refusal rather than a lease-free
start: `claim_task()` already raises `check_violation` for a Task that is no
longer claimable, and "clamped and no Identity to hold" is the same kind of
answer.

Then resolve the view. If capacity is meant to fall when Identities are held,
`max_slots` should be the smaller of `max_concurrent` and the free-lease count
and the column is an input to that; if it is not, the column comes out and the
clamp stays a claim-time property alone.
