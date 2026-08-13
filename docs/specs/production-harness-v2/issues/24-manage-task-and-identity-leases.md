# 24 — Manage Task and Identity Leases through crashes

**What to build:** Hold a Task and all selected Identities exclusively for one Agent run, then release or recover them idempotently after success, refusal, timeout or process death.

**Blocked by:** 12 — Use an Identity without exposing credentials; 23 — Offer and claim a deterministic Slate.

**Status:** resolved

- [x] One claim transaction creates the Task Lease, required Identity Leases and Agent-run binding against database time.
- [x] Task and Identity Leases for one Agent run share one heartbeat and cannot disagree on liveness.
- [x] A competing claim cannot acquire the Task or any already-leased Identity.
- [x] Heartbeat, ordinary release and repeated release are idempotent and actor-attributed.
- [x] Explicit crash reconciliation distinguishes a still-live owner from an expired one and never runs as a side effect of status reads.
- [x] Recovery returns recoverable work to pending without fabricating attempts, while terminal work remains terminal.

## Comments

Implemented on 2026-08-13. One migration,
`20260813T190000Z__one_lease_one_clock_one_heartbeat.sql`, one live test case,
`LeaseTest`, one standing check, `lease_liveness`, and the runtime half in
`execution.py`, which now beats while its child runs.

### The claim already wrote both Leases; nothing kept them agreeing afterwards

Ticket 23 left `claim_task` writing a Task Lease and, for a clamping role with a
Hypothesis that names Identities, the Identity Leases beside it, both from one
`now()` -- so criterion 1 was true the moment the transaction committed and
false a minute later. `expires_at` on an Identity Lease and `lease_expires_at`
on the Task were two independently ageing numbers that started equal. Every
criterion here is about a place they could stop being one hold.

`heartbeat_leases(uuid)` is the answer to criterion 2, and its shape is the
whole of it: one `now()` read, one `v_until`, and the Task update goes first.
If that update touched no row -- the lease lapsed, or the run never held one --
it returns `beat: false` with a reason and *does not touch the Identity
Leases*. A heartbeat that renewed the Identities after the Task had gone is
exactly the disagreement the criterion forbids, so the function cannot express
it. `release_leases(uuid)` is the mirror: the Task's `lease_expires_at` is
nulled only `WHERE ... IS NOT NULL`, which is what makes the second call return
`task_lease_released: false` rather than reporting work it did not do.
`finish_task_attempt` now calls it instead of carrying its own inline UPDATE, so
there is one release verb and closing a run and releasing by hand take the same
path.

### `sweep_expired_leases` was a status read with side effects, and it could not run twice

Criterion 5 asks for two things the old sweep failed at once. It created a
`TEMP TABLE ... ON COMMIT DROP` and so raised `42P07` when called twice in one
transaction, and it treated every in-flight Task as dead: it never asked
whether the lease was still live. `reconcile_leases()` replaces it, splits
in-flight Tasks by `lease_live_for(t)` in one pass, and reports `tasks_left_to_live_owners` as a first-class
number, because "the owner is still alive, so I did nothing" is the answer the
criterion is about. It is a named verb granted to `rk2_runtime` and called from
no read path; arm (f) of the standing check enforces that by refusing a
`reconcile_leases` that is reachable from another function.

`resume_program` was narrowed the same way, and that was the one real decision
in this ticket. It used to dissolve every lease in the Program and let the
restarting process claim -- which is criterion 3's competing claim arriving
through the front door, since `rk run` calls it on startup. It now unclaims only
dead Tasks, aborts only runs with no live Task lease, and returns Hypotheses to
`testable` only where no live owner remains. The cost is that a genuinely
crashed run's work waits out the remaining TTL before another process can take
it; the heartbeat is what makes that a bounded wait rather than a guess.

Criterion 6 is one line of the recovery: nothing in `reconcile_leases` touches
`attempts`. A Task at `attempts >= max_attempts` is retired
`abandoned/attempts_exhausted`; anything else goes back to `pending` with the
count it already had, and the Hypothesis it was testing gets a
`testing -> testable` transition with rationale `task lease expired`.

### The failure a Lease cannot survive is a second clock

`check_lease_liveness()` has ten arms. Five are state: an Identity Lease
outliving its Task Lease, an Identity Lease held by a finished run, an in-flight
Task with no lease, a Task Lease outliving its flight, and a clamped run whose
Identity half has gone. Two are access: a lease verb that declares no actor, a
lease function executable by `PUBLIC`. Two are reachability, above -- one over
function bodies and one over view definitions. The last reads the source of `claim_task` and
`heartbeat_leases` with comments stripped and refuses `clock_timestamp()`,
because `now()` is the transaction timestamp and that is the entire mechanism by
which two updates in one transaction produce one expiry. The negative control
for the check redefines `heartbeat_leases` to return `clock_timestamp()`, which
is the smallest way to say what the check is for.

`identity_leases.expires_at` joined `ignored_columns` in `event_table_config`,
so a heartbeat renewing a hold does not write an Event per beat -- the emitter
records a `suppressed_writes` row instead, which is what keeps
`check_event_log_integrity`'s `row_last_write_unaccounted` arm quiet without
lying about the write. The migration re-attaches the emit triggers and asserts
`check_lease_liveness()` and `check_scheduler_closure()`, but deliberately not
`check_event_log_integrity()`: half of what that check asks is whether every
enforcement trigger is `ENABLE ALWAYS`, and the sweep that makes them so is a
`migrate.py` finalizer, so no migration can see its own triggers in that state.

### The runtime half is a thread that stops before the closing

`Slice._heartbeat` reads `lease_ttl` from the active weights and beats at a
third of it (`BEATS_PER_TTL`). `Heartbeat` is a context manager wrapped around
the child, not around the whole attempt, for two reasons stated where it is used: the beating
stops before anything else in the transaction sequence resumes, which is what
makes sharing the connection safe, and it stops before the closing releases the
Lease, which is the one thing a late beat could contradict. A beat that cannot
reach the database, or that comes back `beat: false`, stops the thread and fails
one assertion named `heartbeat` -- the run keeps going, because the Lease is
already gone and killing the child would not bring it back, but the Ledger says
so. A `lease_ttl` the runtime cannot read yields an interval of zero and no
thread at all, reported the same way.

### The two-axis review: twelve findings, ten applied

**A shared verb that declared its own actor.** `release_leases` called
`set_actor('runtime')` and `set_cause(run, task)` unconditionally. Both are
transaction-local and both outlive the call, so the version of `reconcile_leases`
that looped over dead runs left the cause pointing at whichever run the loop
ended on -- and every Task it settled afterwards, plus the `hypothesis_transitions`
row, was recorded as caused by that one. The verb now asks whether the
transaction has already declared an actor and stays quiet if it has:

```sql
IF current_setting('app.actor_xact', true)
   IS DISTINCT FROM pg_current_xact_id()::text THEN
```

Called on its own it is still self-sufficient; called from inside the closing it
leaves the closing's `rk run` and the closing's cause alone. Both directions are
tested: `test_the_release_keeps_the_cause_its_caller_declared` and
`test_reconciliation_attributes_nothing_to_the_run_it_ended`.

**A lease column the reconciler did not clear.** `release_leases` reaches the
Task through the run holding it; a dead Task whose `agent_runs` row is gone has
no such path, and would settle to `pending` still carrying an expiry -- arm (d)'s
own `task_lease_outlives_its_flight`. Both settling statements now null it.

**The exception a dead connection raises.** `pg.ConnectionError_` is a sibling of
`pg.DatabaseError`, not a subclass. The beat thread caught only the second, so a
broken stream would have killed the thread with its exception unread and left the
closing reporting a Lease that was held through nothing.

**Two assertions under one name.** An unreadable TTL failed `heartbeat` in
`_heartbeat` and then `__exit__` recorded a passing hold saying the Leases were
held through zero beats. `_report` now says nothing when no thread ever started,
and a TTL of zero is failed rather than accepted, so exactly one assertion is
written either way.

**The join, answered rather than applied.** The review asked for a bounded
`join()`, since the connection carries no timeout and a hung server would block
`__exit__` forever. Bounding it would trade the wait for two threads on one
stream, which is the one thing the class exists to rule out. `BEAT_TIMEOUT` --
`SET LOCAL statement_timeout = '20s'` inside the beat's own transaction -- bounds
the statement instead, so a beat that cannot finish fails like any other and the
thread stops on its own. Every other statement in this slice would hang on the
same server, and none of them is made safer by giving up on a stream mid-answer.

**Said once.** The live/dead split appeared six times across the reconciler, the
restart sweep and two check arms. It is now `lease_live_for(tasks)`, in the shape
023 says `ready_for(tasks)` and `identity_held_for(tasks)`.

**Reconciliation that nothing called.** The spec axis was right that
`reconcile_leases()` existed and never ran: `resume_program` is the only recovery
the product performed, and it answers the question only for what was in flight
when the process started. A sibling that dies mid-run is nobody's restart, so the
runtime now calls the verb once per pass, before it offers anything -- the offer
being the first reader that would otherwise walk past a crashed run's Tasks. A
failure there is reported and does not stop the pass: recovering somebody else's
work and doing this run's own are two things.

**Half of criterion 3 that an empty slate cannot show.** Every fixture Program
held one Task, so the competing claim proved only that a claimed Task cannot be
claimed twice. `alive` now carries a second Task, about a second endpoint and the
same Hypothesis, and `claimable_for` refuses it `identity_held` while the first
run holds the Identity.

**The glossary's other direction.** Arm (a) compares two expiries, and an Identity
Lease released out from under a live Task Lease leaves nothing to compare. Arm (i)
asks the three things `claim_task` asks before it writes the pair -- the role
clamps, the Hypothesis names an Identity, the Task is held -- and refuses a
clamped run holding a live Task Lease and no Identity Lease. The runtime watches
the same thing from the other side: a beat that renews the Task and comes back
with fewer Identity Leases than the last one stops the beating and reports it.
Arm (f) also scans `pg_views.definition` now, because a VOLATILE function can be
selected from a view and then reconciling and reading are one statement.

**Answered, not applied.** Ignoring `identity_leases.expires_at` also strips it
from the `identity_lease.created` payload -- 016 removes ignored keys on INSERT
too. That is the same trade 014 made for `tasks.lease_expires_at`, for the same
column and the same reason: a value the heartbeat rewrites every few minutes is
not a fact the log can hold. The row holds it; the log holds when the hold began
and when it ended. Two smells were left as well: the `scheduler_weights` preamble
that three functions share is the corpus's idiom, not this ticket's duplication,
and the `attempts >= max_attempts` cascade reads differently in the closing
(where an attempt just ended) than in the reconciler (where one was abandoned).

**Two new facts the determinism test had to be told about.** `DECIDED` in
`tests/test_database.py` names, section by section, which fields two identically
seeded Programs must agree on, and a section it does not name is a `KeyError`
rather than a silent pass -- which is the point. `reconciliation` is kept whole:
every field is a count, and a count that differed would mean one of the two
Programs had a lapsed Lease the other did not. `heartbeat` is narrowed to
`every`, `lapsed` and `failure`; `beats` and the `identities` its last beat saw
are the child's duration divided by the interval, which is this machine's load.

**A refund the client could read past.** `_serve` releases the slot in a
`finally`, after the response is written, so two `ExchangeTest` cases were
sampling `fence.released` in a race they usually won and lost under the full
suite's load. `refunds()` waits for the count with a bound, which asserts on the
door rather than on the scheduler. Pre-existing, surfaced here, fixed here.
