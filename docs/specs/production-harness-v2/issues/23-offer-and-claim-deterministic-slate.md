# 23 — Offer and claim a deterministic Slate

**What to build:** Offer the orchestrator a bounded set of ready Tasks and let the runtime transactionally claim only a still-eligible member.

**Blocked by:** 18 — Compile and enforce the six-role roster; 20 — Run one Task to a canonical Observation.

**Status:** resolved

- [x] A Ranking pass over fixed rows and a fixed weights version returns the same ordered eligible Tasks without reading the wall clock for rank values.
- [x] The offered Slate contains at most five ready, role-compatible, Lane-legal, affordable and identity-available Tasks with an expiry and factor breakdown.
- [x] Claim rechecks every eligibility condition inside one transaction rather than trusting the offered snapshot.
- [x] Off-Slate, expired, stale, cross-Program and no-longer-ready choices are refused without partially claiming work.
- [x] Choosing nothing falls back deterministically to the first still-valid entry.
- [x] Concurrent claim attempts produce at most one winner and complete Events for the resulting row mutations.

## Comments

Implemented on 2026-08-13. One migration,
`20260813T170000Z__a_slate_is_offered_and_one_task_is_claimed.sql`, one live
test case, `SlateClaimTest`, and the runtime half in `execution.py`, which now
carries the whole offered slate into its facts instead of a count.

### 023 said the eligibility rule twice, and this ticket is every place it disagreed with itself

The scheduler's ranking half has existed since 023. What did not exist is one
statement of what makes a Task claimable: `rank_candidates` decided what may be
offered with a WHERE clause, and `claim_task` decided whether it may still be
taken with an IF/ELSIF chain that restated most of it. Every criterion here is
about a place the two spellings differed.

The slate never asked whether an Identity the Task needs is held, so a Task
scoring confidence 0 for exactly that reason was ranked last and then offered.
The claim never asked whether the Task was still affordable, whether the
Identity was still free, or whether the slate had expired -- the three things
most likely to have moved since the offer, because they are the three another
run changes. And choosing nothing took the first slate row without asking
anything about it, so a runtime that chose nothing got a refusal where the
ticket asks for the first still-valid entry.

`claimable_for(t tasks, w scheduler_weights) RETURNS text` is the rule, said
once: NULL when the Task may be claimed right now, else the name of the
condition that refuses it -- `not_pending`, a cancel reason, a ready reason,
`not_ranked`, `unaffordable`, `identity_held`, `lane_full`,
`global_subagent_cap`. `rank_candidates` filters on it being NULL and
`claim_task` re-asks it under `FOR UPDATE`. Criterion 3 says "rechecks every
eligibility condition", and that is only checkable against a list of conditions
that exists somewhere.

`not_ranked` is new and is not a tightening in disguise. 023 spelled
affordability as arithmetic, and `tokens_left >= estimated_cost *
cost_reference_tokens` is NULL when the cost is -- so an unranked Task was
already unoffered, silently, and only when the budget was bounded. A Program
with an unbounded budget offered unranked Tasks and sorted them by a NULL
priority.

### The clock is in one place, and it is not on the ranking path

Decision 12 makes determinism a property of the function text, and arm (g) of
`check_scheduler_closure()` has checked the three factor functions for a clock
read since 023. The same textual rule now extends to every function the
eligibility rule is made of, which is what keeps criterion 1 true as the rule
grows.

The one clock this file adds is `claim_task`'s expiry check, which is not on
that path: an offer has an expiry, and asking whether it has passed is the whole
of what an expiry is. `offer_slate` has returned `offered_at + slate_ttl` since
023 and nothing ever compared it to anything, so an orchestrator that thought
about a slate for an hour claimed off it.

The test asserts determinism as two passes over fixed rows agreeing on order,
priority and factors, and asserts that the only thing the second pass moved is
the expiry -- which it then checks is exactly `offered_at + slate_ttl` from the
row rather than merely a timestamp that looks five minutes out.

### The choice is a row, because the two halves are two processes

CONTEXT.md's **Slate**: "the runtime decides what may be chosen; the
orchestrator decides which; the runtime commits the claim." The model runs
inside an Agent boundary and cannot call `claim_task`, which is a runtime verb,
so the middle step has to survive as state between them. That state is
`task_picks`, one live row per Program, written by `pick_task(text)`.

It is not a column on `tasks`. A column there would be the model writing a
canonical row, and every refusal below would be a canonical row it had to be
walked back out of. The row carries `slate_id`, so the claim can tell a live
choice from one that outlived the list it was made against, and `pick_task`
refuses an off-slate label at pick time as well -- there, the model is still
running and can be told.

`mcp__rk2__pick_task` has been in the roster since 18 with
`writes=("task_picks",)`, naming a table that did not exist until now. The
served handler is still deferred: nothing in this repository runs an
orchestrator yet, and the ticket that starts one is where a tool call reaches
this verb. What this ticket did fix is 18's comment on that contract, which
described the claim as falling through to the next entry when a choice went
stale. It refuses. Falling through is what the runtime does when nobody chose
at all, and those are different criteria on this same ticket.

### What the claim refuses, and what it leaves behind

Five refusals, each with its own message and none of them partial:

- off-slate: `task % is not on the current slate`, from `claim_task` and
  `pick_task` alike;
- cross-Program: the same message, because labels are per-Program counters and
  `T6` names a live Task of another Program and nothing at all here. A claim
  that read labels without their Program would have found one, so the test
  asserts both counts before asserting the refusal;
- expired: `the slate offered at % expired after %`, asked of the whole
  outstanding slate rather than per row;
- stale: `the choice recorded for this program is no longer on the slate`;
- no longer ready: `task % is no longer claimable: %`, where the tail is
  whatever `claimable_for` returned.

After all of them the Program has no Task off `pending` and no Agent run, which
is criterion 4's second half and the only part of it a message cannot show.

### The fallback is the walk, and the walk is inside the claim

Choosing nothing walks the slate by ordinal and takes the first entry
`claimable_for` still passes, inside the claim's own transaction. That moved a
decision out of `execution.py`: `_claim` used to describe a refusal as
something worth retrying at the next entry, and there is no next entry to try
from out there any more. A NULL now means every entry was rechecked and every
one had gone; a raise means the pass itself is unusable, which retrying would
not mend.

### The stale-pick fixture stands in for a race that cannot be driven from outside

`task_picks` references `tasks` on the Program's own key, so recording a pick
holds a KEY SHARE lock on the Task row and a concurrent `claim_task` blocks on
it at `FOR UPDATE`. The two transactions cannot interleave into the state where
a pick names an entry that has left the slate -- from outside. The state itself
is reachable, because a claim commits its consumption of the slate before the
next transaction reads the pick. So the test consumes the entry as the owner and
says so: what stands in for the race is the state the race would leave.

### One winner, and the Events to prove it

Four connections through a `threading.Barrier` claim off one slate at once.
`pg_advisory_xact_lock(program)` serialises the counting window, because
`SKIP LOCKED` stops two transactions taking the same row and does nothing about
four transactions each counting the same headroom and each concluding there is
room. One run, one claimed Task, three that came back empty -- empty rather than
refused, because an empty slate is what a Program with a full Lane has and
asking for nothing off one is not an error. `check_event_log_integrity` accounts
for every row the race moved.

### The standing check

`slate_claim`, eight arms, registered in `standing_checks` and therefore run at
the end of every `rk db migrate` by `assert_standing_checks()`. It is the
structural half of what the test case asserts behaviourally: that no function
the eligibility rule is made of reads the clock, that both halves still read
that one rule, that the claim enforces the expiry the offer advertises, that an
offer is bounded and a Program has one of them, that a Task which is running is
not still on offer, and that a recorded choice names a pair some slate actually
carried.
