# Row events are emitted by database triggers, with actor context passed through session GUCs

Every state-changing write to an event-emitting table appends exactly one event
row (ADR 0001), and that event row is written by an `AFTER INSERT OR UPDATE`
trigger on the table, not by the application code performing the write. Managed
tables that do not emit are explicitly classified in `event_table_exempt`; they
are not an application call-site exception to this rule. The context a trigger
cannot see — `actor_kind`, `agent_run_id`, `task_id`, `caused_by_event_id`,
`trace_id` — arrives through `SET LOCAL` session settings that the runtime's
connection helper sets before any write. The trigger raises when
`app.actor_kind` is unset.

Decided because the alternative makes log completeness a code convention: an
event written at each call site is an event that a future call site can forget,
and the log's entire value under ADR 0001 is that it is complete. The same
argument already settled two other mechanisms in this schema — state transitions
are rows validated by a trigger rather than checked in Python, and `status` is a
trigger-maintained cache that raises on direct write. Emission is the third
instance of the same rule: if an invariant matters, the database enforces it.

The cost is real and accepted: the trigger cannot know who is acting, so a
session-scoped side channel is unavoidable, and every write path in the runtime
must go through one helper that populates it.

## Consequences

- **One helper is the only way to write.** It is also the single place an actor
  can be misattributed. That place is runtime code, never model output, which is
  what keeps "LLM proposes, runtime commits" true of the audit trail as well as
  of state.
- **Forgetting is loud, not silent.** A write on a connection without
  `app.actor_kind` fails outright. This is deliberately stricter than recording
  an unattributed event: an event whose actor is unknown cannot answer the
  question the log exists to answer.
- **Occurrence events are the exception.** A refusal, a resume, a rate limit have
  no row, so no trigger can fire for them and the runtime inserts them directly.
  They are the one class of event whose completeness *is* a code convention, and
  the `event_types.family` column marks them as such.
- **Emission policy is data.** Which tables emit, which columns are too noisy to
  record, and which must be redacted live in `event_table_config` rows, driving
  the trigger, the trigger-attachment migration, and the integrity check from one
  source. A second inlined copy is how a redaction list eventually leaks a secret.
- **Non-emitters are policy too.** The exemption registry records whether a row
  is covered by another row's event, is itself an audit record, or is reference,
  bookkeeping, derived or log data. A new table with neither an emitter config
  nor an exemption fails the coverage check.
- **Dropping a trigger is the failure mode to watch.** A migration that rewrites
  a table can silently detach it. `check_event_log_integrity()` therefore checks
  `pg_trigger` against the config, not only rows against events.

Settled in historical ticket 07, decisions 9, 11 and 17.
Amended by migration 0030 (historical ticket 33) to record the checked
non-emitter classifications.
