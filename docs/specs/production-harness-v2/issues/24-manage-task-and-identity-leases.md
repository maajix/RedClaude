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
in-flight Tasks by `t.lease_expires_at IS NOT NULL AND t.lease_expires_at >
now()` in one pass, and reports `tasks_left_to_live_owners` as a first-class
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

`check_lease_liveness()` has eight arms. Four are state: an Identity Lease
outliving its Task Lease, an Identity Lease held by a finished run, an in-flight
Task with no lease, a Task Lease outliving its flight. Two are access: a lease
verb that declares no actor, a lease function executable by `PUBLIC`. One is
reachability, above. The eighth reads the source of `claim_task` and
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
third of it. `Heartbeat` is a context manager wrapped around the child, not
around the whole attempt, for two reasons stated where it is used: the beating
stops before anything else in the transaction sequence resumes, which is what
makes sharing the connection safe, and it stops before the closing releases the
Lease, which is the one thing a late beat could contradict. A beat that cannot
reach the database, or that comes back `beat: false`, stops the thread and fails
one assertion named `heartbeat` -- the run keeps going, because the Lease is
already gone and killing the child would not bring it back, but the Ledger says
so. A `lease_ttl` the runtime cannot read yields an interval of zero and no
thread at all, reported the same way.
