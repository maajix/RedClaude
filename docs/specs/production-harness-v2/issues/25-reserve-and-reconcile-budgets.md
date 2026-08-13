# 25 — Reserve and reconcile campaign budgets

**What to build:** Prevent concurrent Tasks from overspending token, request and Lane ceilings by reserving capacity before admission and reconciling actual use on every terminal path.

**Blocked by:** 13 — Enforce Halt and aggregate request budget at egress; 23 — Offer and claim a deterministic Slate.

**Status:** resolved

- [x] Program configuration supplies total, per-Agent-run and per-Lane token/request ceilings plus concurrency limits.
- [x] Claim admission reserves worst-case capacity transactionally before a Task becomes running.
- [x] Concurrent claims cannot collectively reserve past any shared ceiling.
- [x] Actual SDK usage, proxy exchanges and Tool usage reconcile reservations on success, abort, refusal, timeout and crash recovery.
- [x] Exhausted capacity makes Tasks ineligible with a typed reason and never relies on a prompt instruction.
- [x] Rate-limit and retry timing is durable, bounded and does not spin inside an Agent session.

## Comments

Implemented on 2026-08-13, in one migration --
`20260813T230000Z__reserve_the_worst_case_and_reconcile_it.sql` -- and the five
Python modules a ceiling has to travel through to reach the model.

The shape is one table. `budget_reservations` holds what a claim promised on
behalf of the run it opened; `program_capacity` and `lane_budget` are what is
left once the open ones are subtracted; `budget_refusal_for(tasks)` turns that
into a name, which `claimable_for` returns as one more arm; and a trigger on
`agent_runs.finished_at` settles the promise against what the run turned out to
cost. `claim_task` writes the row, `finish_task_attempt` carries the usage that
settles it, and `reserve_egress_slot` holds the same run to the request half of
what it reserved.

### Why the promise is a row and not a subtraction

`program_budget.tokens_left` already existed and already refused an
unaffordable Task. What it cannot see is a claim that has been made and has not
spent anything yet: four claims in the same second all read the same
`tokens_left`, all find the estimate affordable, and all four are admitted. The
row is what makes the second claim's arithmetic include the first claim's
intent.

That means the two sums must never overlap. `tokens_spent` comes from
`agent_runs`, `tokens_reserved` from the open reservations, and settlement
happens in the same statement that writes the run's tokens -- so a run is in
exactly one of the two at any instant, and the view can add them without
double counting.

The request side does not have that property and had to be given it. A run's
tokens are written once, at the close; its contacts are counted by the door the
moment it makes them, while the promise covering them is still open. So
`requests_reserved` is the promise minus what the run has already sent --
`greatest(br.requests - run_contacts(br.agent_run_id), 0)` -- and without that
subtraction every request in flight was charged twice and the pool refused
claims against capacity nobody held. `run_contacts(uuid)` is one function
because the same count is what the settlement writes and what the door compares
its ceiling to; it was three copies of one join before.

### One lock, and it was already there

`claim_task` has taken `pg_advisory_xact_lock(hashtextextended(p::text, 0))`
since 023 and calls it the counting window. The `INSERT` goes inside it, after
the eligibility recheck and beside the run it belongs to, so criterion 3 needed
no new lock at all: concurrent claims on one Program serialise where they
already serialised. A second lock would also have introduced an order to get
wrong against `program_egress_spend`, which the door takes for the same
Program.

### One transition, not five endings

Success, refusal, park, abort, lease expiry and crash recovery are six code
paths and one fact: `finished_at` stops being NULL. `settle_budget_reservation`
fires there rather than in each of them, which is what makes "reconciled on
every terminal path" a property of the schema instead of a list somebody has to
remember to extend -- including the paths this ticket has not been written yet
to know about. `resume_program` reconciles a crashed run without knowing this
ticket exists.

A run whose tokens were never written is charged what it promised. Settling it
at zero was the first draft and it is wrong twice over: it gives back capacity
the model consumed -- a child killed at its timeout spent its tokens, the model
is not a process this system can interrupt mid-token -- and it leaves
`program_budget.tokens_spent` where it was, so a Program that loses every child
is a Program that never runs out. `charge_unmeasured_run` fires `BEFORE` the
settlement on exactly that shape: `stop_reason = 'aborted'`, which is the word
both `resume_program` and the lease sweep already write, with neither token
column measured. It writes the reservation to `input_tokens` and a zero beside
it, because `program_budget` sums `input + output` per run and NULL plus a
number is NULL -- a charge in one column alone is a charge the Program's budget
never sees. A reported zero is a measurement and stands; a refusal and a harness
error are still charged nothing, because both had a caller behind them that
could say what they cost.

The runtime had to close a lost child that way for the trigger to see it.
`execution._run` caught only the two startup shapes, so a child killed mid-run
raised past them and closed as `error` with no tokens -- the one ending that
looked like a harness fault and cost nothing. It now closes as `aborted`, which
is what it is.

`finish_task_attempt` gained two defaulted parameters rather than a second
statement, because the trigger reads the row it settles from: tokens written
after `finished_at` would settle against a run that had not been counted yet.
`coalesce(p_input_tokens, input_tokens)` keeps a caller with nothing to report
from overwriting a measurement with the absence of one.

### What the model is told, and what it is not

The per-run ceiling reaches the child as a number the launcher enforces:
`execution.STARTED` reads the open reservation in the claim's own transaction,
it lands on `Claimed.token_cap`, goes out on `AgentRunRequest.token_cap` and
the job document, and `_launch.run` sums each `AssistantMessage.usage` as it
arrives and breaks the loop when the total passes it, with `stop_reason
"budget"` -- which `execution.ACCEPTED_STOPS` already contained. Nothing is
said to the model about its budget, because a prompt instruction is not an
enforcement and criterion 5 says so.

The usage comes back the same way: `AgentRunResult.input_tokens` and
`output_tokens` ride the child's result dict into `Claimed.facts`, and `_finish`
passes them to `finish_task_attempt`, so the number that settles is the SDK's
own. A `ResultMessage` carrying usage replaces the running sum rather than
adding to it -- it is the whole session's total, not the last turn's -- and
until one arrives the sum is per turn, because a turn's usage is that turn's own
request, prefix and all, which is what the Program is charged for making it.

A usage block this process cannot read raises, for the reason an unreadable
`token_cap` raises: both are the ceiling, and a quiet zero on either side is a
session running unbounded. That is the one place where failing the run is
cheaper than continuing it.

### The door's one arm

Only the per-run request ceiling is enforced at the door. The Program and lane
request ceilings are already bounded by admission -- every claim in flight has
reserved its worst case out of both -- so a run held to its own reserved number
cannot collectively pass either. A run with no reservation, which is what
`rk proxy send` opens, is bounded by the Program's total as it was before.

Its refusal carries `retry_at := NULL` deliberately. Exhaustion is not a wait:
a time here would be the door promising the run gets more, and a caller reading
one would come back around a loop it can never leave. The rate-limit arm beside
it still answers with the instant the refusal stops being true, which is the
durable, bounded half of criterion 6 -- a row the caller reads once, not a
sleep inside an Agent session.

### Two views with nearly one name

`lane_budget` is not `lane_capacity`. 0019 already had the latter, and it
answers a different question: how many Tasks of a kind may run at once, against
how much they may cost. A lane can be at neither, either or both, and the first
draft of this migration was refused by the database for trying to create the
name twice.

Both are the scheduler's lane, spelled lowercase. `CONTEXT.md` reserves capital
Lane for which party caused a request -- `agent`, `replay`, `proxy_internal` --
and RK-REG-007 is the regression that came of widening that word. The first
draft of this migration capitalised it twenty-three times.

### The check, and the arm that is deliberately absent

`check_budget_reservations()` has three structural arms: capacity still held
for a run that has finished, a reservation settled while its run is open, and a
settled row whose numbers do not match the run it settled against. Structural
rather than textual, unlike 71's and 73's, because this invariant is about rows.

Two more arms are textual, and they guard the function this ticket's admission
rule lives in. `budget_refusal_for` reads `now()` through the views under it,
so it must stay `STABLE` and not `IMMUTABLE`; and it is a scheduler function,
which 23 says the agent's roles may not execute. Both are `check_slate_claim`'s
questions asked of two more names rather than a hundred-odd lines of it copied
into a second file.

### Ceilings that cannot all be true at once

`check_program_configuration` gained a fifth arm. A per-run ceiling above the
lane's or above the campaign's total is a Program where every claim promises
more than there is, so `budget_refusal_for` refuses every Task from the first
one and reports it as an exhausted budget -- the true answer to the wrong
question. The configuration is what is wrong, and it now says so where the
operator is already looking.

Only the per-run ceiling is compared upwards. A lane or campaign ceiling nobody
can reach is slack, not a contradiction: the tighter number binds first and the
looser one simply never does. Flagging those would have made half the fixtures
in this repository into problems and taught the operator to skip the check.

Not an arm: a Program whose committed tokens exceed its total. A run that
spends past its ceiling produces exactly that, the schema permits it because
the model is not a process this system can interrupt mid-token, and a check
that fires on data the system permits is one that gets ignored. What is checked
is the bookkeeping; that concurrent claims cannot collectively promise past a
ceiling is proved by the test that runs four claims at once.

An arm that was written and then dropped: an in-flight run with no reservation.
It is true of every `agent_runs` row this suite inserts by hand, so it would
have failed unrelated cases through `assert_standing_checks` -- a check on
provenance, in a place where provenance is not what the rows mean.

### The test, and why its race is hunts

`BudgetReservationTest` is seven Programs, one per disturbance, in the shape
`SlateClaimTest` established: everything commits, the refusals only mean
anything against the state the claims before them left, and the Programs are
purged at the end. The two cases now share `SchedulerFixture`, which holds the
moves that were never about either ticket -- seeding a Program, ranking it,
offering the slate, claiming off it, and the barrier the racers meet at.

The race Program's Tasks are hunts because the hunt lane admits two at once and
the recon lane admits one. Four contenders against a recon lane would resolve
by concurrency and prove nothing about capacity; against a hunt lane with
headroom left over, the three that come back empty were refused for what they
would have promised, and the test asserts the headroom to say so.

The door scenario runs as `rk2_proxy` on a connection of its own, because
ticket 13 revoked `reserve_egress_slot` from the runtime and a test that asked
as the runtime would have been testing a grant that no longer exists.

The metered Program was a Program that could never claim anything: five
requests in the engagement against a per-run ceiling of ten. It proved the arm
fired, and after the fifth check arm above it would also have been reported as
misconfigured, which is the honest reading of it. It is now ten against ten --
one run may spend the whole engagement, which is a policy and not a
contradiction -- and the second Task is refused for requests the first run has
promised and not yet sent.

The Control the criterion-1 assertion needed is beside it: a Program written
with a run ceiling over its total, read back through the check, and rolled back.
Without it, "no Program here disagrees with its document" passes just as well
against a check that never reports anything.

### What the review raised and this did not change

- The two token columns travel together everywhere and are a type wanting to be
  born. They are the two columns `agent_runs` has and the two parameters
  `finish_task_attempt` takes; a pair type would be one more shape between the
  SDK's numbers and the row, converted at both ends.
- `_token_cap` is a one-line conversion and reads like a Middle Man. It is the
  place the docstring above lives, and the reason an unreadable cap fails the
  run rather than degrading is a decision that needs somewhere to be written
  down.
- The door's ceiling check is on the hot path of every request, which ADR 0003
  warns about. It is one function call inside a statement that already takes two
  row locks, and 0023 puts the same shape in the same place.
