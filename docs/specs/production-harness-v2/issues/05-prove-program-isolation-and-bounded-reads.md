# 05 — Prove Program isolation and bounded reads

**What to build:** Allow compact state inspection by stable labels while proving that one Program cannot name, infer or mutate another Program's rows.

**Blocked by:** 04 — Create or resume a Program with the same command.

**Status:** resolved

- [x] Two Programs may contain colliding short labels without either Program resolving the other's rows.
- [x] Program identity is bound by runtime database context and is absent from every model-facing argument schema.
- [x] Compact reads return stable labels, revisions, digests, counts and omission markers under configured size limits.
- [x] Full records are retrievable by a stable label previously exposed to the same Program.
- [x] Unknown and cross-Program labels return indistinguishable absence without leaking foreign existence.
- [x] Repeating every read leaves database bytes and Lease state unchanged.

## Comments

Implemented on branch `implementation/startup-assertion` in commit `dcb2fdb` on
2026-08-10.

`src/redkraken/state.py` is the operation; `rk state --config <path>` is the
adapter over it, and `20260810T094500Z__bounded_state_reads.sql` is what makes
the read possible at all. `rk2_state` had never opened a session: the role the
whole isolation design exists for held no CONNECT privilege, so the boundary
every other file describes had never once been crossed.

Crossing it turned up the defect behind it. 020 granted `rk2_state` SELECT on
`programs`, which is a `program_global_table` and so has no row level security
of its own — the agent connection could enumerate every Program on the
installation by slug, name and scope policy, which is exactly the second
question criterion 5 has to leave unaskable. The registry leaves the read
surface here, and `check_state_isolation()` fails the gate if anything puts it
back at table or at column granularity.

`v_records` is what replaces it: one relation over the eight labelled record
kinds, answering with a label, a revision, a digest and the record. The revision
is `max(events.seq)` for the row through `rk2_revision()`; the digest is sha256
over the record's own jsonb text, computed once, so the digest in a compact read
and the digest of the record fetched by that label are the same number. Both
functions are invoker-rights, which is the whole of their isolation.

### What is asserted, and by what

`tests/test_state.py` is 17 offline tests over the two pure seams. `bound()`
decides what a caller is not told, so its tests are about the subtraction: what
was dropped, from which kind, and that the reported size is never over the
ceiling that produced it — including the ceilings nothing fits under, where an
empty answer costs nothing rather than the two bytes an empty array is written
in. `ArgumentTest` asserts criterion 2 where it can be asserted rather than
described: no read verb has a parameter naming a Program, and the SQL those
verbs send contains no such word.

`tests/test_cli.py::StateCommandTest` is 6 tests over the adapter — two
connection strings, both named when neither is set, neither echoed back, and a
refused configuration that reaches no database.

`tests/test_database.py::StateReadTest` is 15 live tests and the second class in
that module that commits. Two Programs, both holding `TEC1`, because colliding
short labels are the ordinary case and isolation has to hold through the
collision rather than around it. Criterion 2 is asserted over the wire: every
statement the read sends is recorded, the Program's identifier is a parameter of
exactly one of them — `set_config('rk2.program_id', $1, true)` — and none of the
three read statements names a Program. Criterion 5 compares two whole serialized
reports with only the label text substituted, so nothing, exit code included,
distinguishes a label nobody holds from a label the other Program holds.

Criterion 6 is measured against a snapshot taken before any read in the class
has run, so a read that changed something once and then never again still fails
it, and the snapshot is anchored — the Lease this case wrote is asserted to be
there — so it cannot pass as two equal descriptions of nothing. The reads
themselves run in a read-only transaction, and a separate test shows the agent
connection cannot write what it can read.

Run on 2026-08-10 against `pgvector/pgvector:pg18` — PostgreSQL 18.4 with
pgvector 0.8.6, the pairing tickets 03 and 04 were verified on. The whole suite
with the server present is 310 tests, green, no skips, in 132s; without one it
is 246 with 10 skipped. `tools/check_baseline.py` reports `classifications=10
regressions=7 artifacts=223`. There is no typechecker configured in this
repository — no `[tool.mypy]` or `[tool.pyright]` in `pyproject.toml`, and
neither is installed — so what ran in its place is `python3 -m compileall -q src
tests`, clean.

The new standing check has four negative controls in `CONTROLS`: the registry
granted back as a table, granted back as a column, and each of the two bridge
functions turned into `SECURITY DEFINER`.

### Decisions worth naming

The command takes two connection strings because the read is about two roles.
The Program is resolved on the runtime connection, which can read `programs`,
and the records are read on the agent's, which cannot. One URL doing both would
be one role doing both, and the isolation the report describes would not have
been in force while it read. `state.py` refuses a connection that is not
`rk2_state`, and refuses one that can read any column of the registry, rather
than trusting the URL it was handed.

The agent connection cannot read its own Program's slug, name or scope policy
either. That is the cost of the privilege being the boundary instead of a WHERE
clause, and it is the right cost: policy is what an operator wrote and what the
runtime compiles into a Mission packet.

`entities.program_id` stays readable — 0030 seeded the column registry from what
the role could already read — and it stays because row level security scopes it
to the session's own rows. What it yields is the identifier the session is
already bound to and could read back out of the setting. What no query on that
connection yields is a *second* identifier, and a test asserts exactly that.

The byte ceiling is over the record index, which is the part that grows with the
Program. A full record asked for by `--label` is returned whole: the caller has
already sized it by naming it, and §11 of the spec is explicit that a large
payload is fetched by stable identifier rather than embedded. Free-form jsonb —
`tests.spec`, `tool_runs.args`, `entities.metadata` — is not in the projection
at all; their hashes are.

Revisions come from the log, which ADR-0001 governs. The record itself is read
from the rows and is never rebuilt from the log; what the log answers is only
"has this row changed since you last looked". It does make log completeness
load-bearing for a number an agent compares — pruning the log would walk
revisions backwards — which is the same invariant the replay test already
exists to hold.

`v_surface` was rewritten to call `rk2_descriptor()`. Repeating 020's coalesce
inside `v_records` would have put two answers to "what is this row called" in
front of the same model, free to drift the day a subtype is added. The function
is keyed by the row's id and not by its label, because labels collide across
Programs by design and a shared definition reached by label would be the one
join in the file where a foreign row could answer.

`assert_standing_checks()` is deliberately not called by this migration. It is
the last file in the corpus, so it runs before the finalizers rather than
between two migrations, and three registered checks describe invariants those
finalizers establish. What the file asserts on its own is its own rule.

### Raised by review and deliberately not built here

- Who holds the session is not this role's boundary. `rk2_state` can set
  `rk2.program_id` again — a custom GUC is `PGC_USERSET` and has no ACL to
  revoke — so what stops a rebind is that nothing reachable from that
  connection names another Program. Making the process that owns the session
  the boundary, so that the model gets tool calls rather than SQL, is ticket
  19.
- `SELECT kind, count(*) FROM v_records GROUP BY kind` builds every record's
  jsonb and digest, because a `UNION ALL` subquery's target list is evaluated
  whether or not the outer query reads it. That is a cost at scale, not a
  correctness defect, and a cheaper count belongs to whoever meets the scale.
- The six agent-facing `v_*` views 020 built — `v_surface`, `v_hypotheses`,
  `v_evidence`, `v_receipts`, `v_artifacts`, `v_validation_packet` — still have
  no reader anywhere in the harness. `v_records` is the first projection
  anything reads. Whether the artifact ones survive is ticket 06's question and
  whether the rest do is ticket 19's; nothing here removed one, because a view
  nobody reads is cheaper than a view removed from under a ticket that wanted
  it.
- `rk state` reports `program_id` as a fact. It is an operator's command, run
  by someone who already holds both connection strings and the configuration
  file; the model-facing surface criterion 2 is about has no such field, and no
  such surface exists yet to have one.
