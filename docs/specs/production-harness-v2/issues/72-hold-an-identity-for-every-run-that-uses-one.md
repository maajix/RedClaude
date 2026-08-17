# 72 — Hold an Identity for every run that uses one

**What to build:** Make `clamp_to_identity_leases` mean one thing at claim time, so a role the roster clamps cannot start a run that touches a target without holding the Identity it acts as.

**Blocked by:** 24 — Manage Task and Identity Leases through crashes.

**Status:** resolved

**Reading on the How:** the second -- the Identity requirement is a property of
the Task. A clamped Task carries what it will act as in rows of its own, derived
from its Hypothesis where there is one and from the Program's anonymous Identity
where there is not, and nothing in the claim path reads `hypotheses` for the
question any more.

- [x] A clamped role's run holds an identity lease for every Identity it will act as, including on a Task that names no hypothesis.
- [x] Where a clamped Task cannot name the Identity it needs, the claim is refused rather than granted leaseless.
- [x] `effective_lane_capacity.clamp_to_identity_leases` either bounds something or is gone from the view.
- [x] A negative control claims two clamped Tasks that want the same Identity and proves the second does not start.

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

## Comments

Implemented on 2026-08-17.

`src/redkraken/migrations/20260908T010000Z__a_clamped_run_holds_the_identity_it_acts_as.sql`,
one new `IdentityClampTest` and four `Control`s in `tests/test_database.py`. No
Python: what a run acts as is decided inside `claim_task`, and nothing in `src/`
reads or writes the answer.

### Two things in the Why are not reachable, and the defect is worse than both

The Why names `0023_scheduler_ranking.sql:424-431` as `ready_for()` refusing a
Task whose hypothesis names a held Identity. That is `confidence_for()`'s Gate 2,
and it returns `0` rather than a refusal -- a priority of zero, not a
disqualification. The refusal the scheduler actually has is
`identity_held_for(t)` in `claimable_for`, which 023 added later.

The Why's reachable case -- "a hunt Task with no hypothesis takes no lease and
passes no gate. Two such Tasks claim concurrently" -- is closed and was closed
before this ticket opened. `claimable_for` asks `ready_for`, and `ready_for`
returns `hunt.no_hypothesis` at `0023_scheduler_ranking.sql:482`. Such a Task is
never offered and never claimed. `IdentityClampTest` writes one and records both
halves rather than leaving the correction as prose: it does carry Identities, and
it is refused before the Lease question is asked at all.

What is open is one step to the left. The Task has a Hypothesis; the Hypothesis
names nobody. `claim_task` wrote its Leases under
`IF v_clamp AND v_task.hypothesis_id IS NOT NULL` and then only for the non-NULL
of two nullable columns, and `identity_held_for` asks the same two columns -- so
an unauthenticated hunt took no Lease and blocked nobody.

The population that escaped is the both-NULL one, not every NULL one: the old
INSERT leased each non-NULL slot, so a single-identity Hypothesis took its one
Lease and was gated on it. Ticket 18's measurement of the corpus this schema was
drawn from (`0018:26`) puts the escaping case inside a larger bucket without
splitting it -- "49 of 55 investigations in the corpus have at least one NULL
identity slot -- every unauthenticated hypothesis, and every single-identity
one" -- so the unauthenticated share is at or below 49 in 55 and 018 does not say
where. It is the ordinary shape of a hunt either way, which is the roster's
sentence about two hunters sharing one upstream slot, in the case it was written
for.

### The anonymous Identity

No criterion asks for it and the design does not work without it. If a clamped
Task must name what it acts as, an unauthenticated hunt has to name something,
and refusing it instead -- the other end of criterion 2 -- would refuse every
hunt that has not logged in. `rk2_anonymous_identity(program)` returns the
Program's one `class = 'anonymous'` Identity, minting it the first time a clamped
Task needs it and finding it by `dedup_key` thereafter. Its `slot_name` is
`_anonymous`, and the leading underscore is load-bearing: `reconcile_identities`
writes `slot_name` from the configured `identity.name`, which `config.SLUG`
requires to start `[a-z0-9]`, so no configuration can collide with the reserved
slot on `identities_slot_idx`. Spelling it `anonymous` would have made the
collision an ordering question, and the losing order raises `unique_violation`
inside the first hunt Task's INSERT.

Its consequence is deliberate and visible: two anonymous hunters share one
upstream slot and one cookie jar exactly as two authenticated ones would, so
while one unauthenticated hunt runs a second one waits, and `web_hunter`'s two
slots are reachable only by two hunts that act as different Identities. That is
the whole of criterion 4, and `IdentityClampTest` claims it that way round --
two Tasks, one Identity, the second refused `identity_held`.

### What the rows are, and what may write them

`task_identities` is a projection, not a column an agent fills in: a trigger on
`tasks` derives it at INSERT and re-derives it on `UPDATE OF kind, hypothesis_id`,
and a guard trigger refuses any other hand. The re-derivation is not optional
tidiness -- five sites in `tests/test_database.py` point a Task at a Hypothesis
after opening it, and `SlateClaimTest.arrange_held` is one of them, so a
projection that only ran at INSERT would have left that Task acting as the
anonymous Identity while the fixture leased `slate-member`, turning its refusal
into a successful claim.

What may not be re-derived is a Task under a live Identity Lease: the run is
already acting as what it leased, and moving the answer beneath it would leave a
hold on something the Task no longer names.

The projection body is `rk2_project_task_identities(tasks)` and the trigger calls
it, so the backfill over the Tasks that predate the file runs the same code
rather than a second copy of it. The walk from a Task to the Identities its runs
hold is `task_held_identities(uuid)` for the same reason: the trigger's guard
asks whether there is any, and the check's arm (b) asks whether a particular one
is among them, and both should be asking about the same set.

### How far criterion 2 is proved

`IdentityClampTest.arrange_legacy` flips `roles.clamp_to_identity_leases` on
`recon` and reads `claimable_for`, and it does that inside a transaction it
throws away -- `roles` is the corpus's roster rather than a per-Program row, so a
committed flip would be an edit to every other case in this file. What that
proves directly is the predicate: `clamped_without_identity` before the flip is
absent and after it is the answer.

The step from the predicate to the refusal is `claim_task` lines 502-509, which
raise `check_violation` on any non-NULL `claimable_for` result without looking at
which one it is, and `SlateClaimTest` already reads that raise back for two other
arms ("is no longer claimable: unaffordable", "is no longer claimable:
identity_held"). So the arm does not need a third claim of its own to be a
refusal rather than a leaseless start; it needs to be a non-NULL reason, which is
what is measured.

### Criterion 3 bounds `headroom`, not `max_slots`

The How offers `max_slots` and that is the wrong column. `max_slots` is the
roster's `max_concurrent` by definition and no Program may move it, and 023's
`check_scheduler_closure()` fails any lane whose `min_slots` exceeds it -- so a
Program with fewer Identities than its entitlement would have failed the closure
check rather than reported a smaller lane. `scheduler_lane_state.headroom` for a
clamped lane is now `least(free slots, unheld Identities)`, which does not
double-count: a running clamped Task takes one slot and holds one Identity, so it
is removed once from each side.

It is an upper bound and not a count of claimable Tasks. The free Identities are
the Program's, not the ones this lane's pending Tasks happen to act as, so a lane
can report headroom while every Task in it is refused `identity_held`. That is
the safe direction and not an accident of ordering: `claimable_for` asks
`identity_held` before it asks `lane_full`, so the coarse number can never refuse
a Task the exact one would have allowed.

### What keeps it

`check_identity_clamp()`, three arms, this ticket's own check rather than arms
bolted onto 024's -- 026's rule, which 074 and 075 also took. Arm (a) is a
clamped run in flight acting as nothing. Arm (b) is criterion 1's "every", which
024's arm (i) cannot ask: that arm is satisfied by one Lease however many the
Task names. Arm (c) is criterion 3 as a standing question, because a column in a
capacity view that nothing reads is exactly the state this ticket found.

A fourth arm was written and taken out: a run holding a Lease its Task does not
name. It asks nothing the schema leaves open -- `claim_task` is the only writer
of `identity_leases` and writes them from `task_identities` alone -- and asked
globally it is false. A lane the roster does not clamp derives no
`task_identities` at all, so the arm made every Identity Lease a recon or
analyze run holds into a violation, which is a rule no criterion asks for and
the corpus contradicts. What stops a Lease from becoming a request under the
wrong session is the request side: `rk2_replay_plan` refuses a run replaying
under a slot it does not lease, and `enforce_allowed_receipt_capability` refuses
a Receipt naming an Identity the run has no live Lease on.

024's arm (i) is withdrawn rather than repaired. It asked whether the role
clamps, whether the Hypothesis names an Identity, and whether the run holds one;
the middle condition was the defect written down, since it excused every
unauthenticated hunt from the arm. Take it out and what remains -- a clamped Task
in flight that names Identities and holds no Lease at all -- is a subset of arm
(b) above, which asks per Identity. Every row the repaired arm could return is a
row arm (b) returns, so keeping both would report one defect twice under two
names. `lease_liveness` keeps the eight arms that are about a Lease's own
liveness.

Three controls, one per arm, each measured to trip only the arm it names.
