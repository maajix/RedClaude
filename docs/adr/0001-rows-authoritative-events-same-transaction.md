# Rows are authoritative; the event row is appended in the same transaction

The system keeps an append-only event log, which normally signals event sourcing
— so the natural assumption is that state is projected from that log and rebuilt
by replay. It is not. The Postgres tables are the write model and the source of
truth. Every managed table is classified by the database as either an event
emitter or an explicit exemption; every state-changing write to an emitter
appends exactly one event row inside the same transaction. The event log is the
completeness proof and audit trail for the event-bearing state — never the
reconstruction path.

Decided because the system's hot paths are recursive CTE traversal over the
attack-surface graph, `FOR UPDATE SKIP LOCKED` on the task queue, and pgvector
similarity search. All three need materialised rows. A replay-only model would
mean writing and maintaining a projector per table, and paying rebuild cost, in
exchange for time travel that nothing in the design asks for.

## Consequences

- **Recovery reads current rows.** Rate limit, crash, kill and operator stop are
  one case, and none of them replays anything. The scheduler recomputes its
  ranking from rows on resume, because the surface may have changed while it was
  down.
- **Time travel is gone.** "What did the database look like at 04:00" is no
  longer answerable by replaying to that point. What survives is the provenance
  chain — for any finding, the hypotheses, observations, receipts and artifacts
  behind it are still fully reconstructible.
- **`checkpoints` does not exist.** It was a replay-model artefact and would only
  have described a snapshot nothing consumes.
- **The invariant needs a test, not a convention.** Log completeness is the whole
  value of the event table under this decision, so a test asserts that replaying
  the log reproduces the row set. Without it, a single write path that forgets its
  event row degrades the log silently.
  *Amended by historical ticket 07, decision 1:
  "replaying the log reproduces the row set" would require after-images on every
  write, which makes the log a reconstruction path in all but name and
  contradicts this ADR. The test asserts **completeness** instead — no emitting
  row without exactly one creation event, no emitting mutation without one
  mutation event, no event without its subject row — as a reconciliation query,
  `check_event_log_integrity()`.
  Ticket 07 decision 9 also removes the "a write path forgets its event row"
  failure mode structurally: events are written by triggers, so the only way to
  lose one is to drop a trigger, which the same query detects.*
- **Exceptions are data, not silent omissions.** `event_table_exempt` classifies
  each non-emitter with a reason. A `covered` row is written in the same
  transaction as an emitting row that names it; an `audit` row is itself the
  append-only record. Reference, bookkeeping, derived and log rows are outside
  the per-row event claim. `check_event_coverage()` fails when a managed table is
  unclassified or classified twice.
- **This supersedes the original wording of charting decision Q29**
  ("resume by recompiling from the event log"), which described the rejected
  option. The requirement Q29 was actually expressing — no in-memory scheduler
  state survives a crash — is unaffected.

Settled in historical ticket 06, decision 3.
Event-table columns and how events reference rows are ticket 07.
Amended by migration 0030 (historical ticket 33), which replaced the earlier
absolute per-table claim with the checked emitter/exemption registry.
