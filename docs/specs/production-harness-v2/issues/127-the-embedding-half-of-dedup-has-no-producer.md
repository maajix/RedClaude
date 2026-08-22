# 127 — The embedding half of dedup has no producer

**What to build:** A decision about semantic deduplication: either something
computes embeddings and the `penalised` near-match action becomes reachable, or
the two embedding tables, their HNSW indexes and the stage-2 columns are
retired.

**Blocked by:** nothing.

**Status:** ready-for-agent

- [ ] The producer that does not exist is named. `hypothesis_embeddings`
      (`0010_embeddings.sql:7-13`) and `observation_embeddings` (`:15-21`) each
      hold a `vector(1536)` keyed by model, each carries an HNSW index
      (`:23-26`), and neither has an `INSERT` anywhere. Nothing in the harness
      computes an embedding.
- [ ] The consequence on the dedup side is stated. `hypothesis_near_matches`
      (`0012_scheduler.sql:69-79`) declares three actions after
      `0018_vocabularies.sql:429-436`: `suppressed`, `penalised` and
      `key_collision`. Its only writer
      (`20260814T070000Z__a_proposal_becomes_a_canonical_hypothesis.sql:796-800`)
      writes `key_collision` and nothing else, so `similarity` and
      `embedding_model` -- which `hypothesis_near_matches_stage2_cols` requires
      to be NOT NULL for the other two actions -- are never written, and the two
      similarity-based actions are unreachable. The CHECK is satisfiable only on
      its `key_collision` arm.
- [ ] `candidate_hypothesis_id` is understood rather than lumped in. It was
      added by `0023_scheduler_ranking.sql:165-166` so that from the Hypothesis
      a candidate became there is a way back to the row, and `0023:161-164` says
      the `penalised` action exists for exactly that lookup and that
      `key_collision` "has no candidate row either". It is NULL today because
      the only action written is the one that correctly has no candidate, not
      because a writer forgot it.
- [ ] `hnsw_headroom` (`0027_migration_baseline.sql:364-376`) is decided with
      the rest. It counts rows in the two embedding tables against
      `maintenance_work_mem` to say whether the next index build spills to disk,
      and `check_server_baseline` asserts on it. It is a live check over two
      permanently empty tables: the answer is always "infinite headroom", and it
      will stop being true on the first day anything writes a vector.
- [ ] Whichever way it goes, `0018_vocabularies.sql:414-421` keeps its point:
      the design's own words are that what can be fixed is "the *silence*" --
      a suppressed hypothesis leaves a trace. If embeddings are deferred, the
      trace is `key_collision` only, and the migration that says so also says
      what the harness gives up.

## Why

`docs/research/wiring/23-database-wiring.md` sections 1.3(g) and 3.1: "the
semantic-dedup design has no producer". Two tables, two HNSW indexes, three
always-NULL columns on the agent's read surface, one CHECK constraint with an
unreachable arm and a baseline check computing headroom for rows that never
arrive -- all of it one absent capability.

`needs-triage` because adding an embedding producer means choosing a model, a
place to run it and a cost, which is a product decision; and because the
alternative -- retiring pgvector from the schema -- is equally large and equally
not an agent's call.

## The decision, taken 2026-08-22

**Retire the embedding half: the two tables, the two HNSW indexes, the
`hnsw_headroom` view and its baseline check, and the two similarity-based arms of
`hypothesis_near_matches`. `key_collision` stays and is the whole of the trace.
pgvector comes out of the provision path with them.**

The sentence that decides it is the design's own, written when the near-match
vocabulary was closed (`0018_vocabularies.sql:414-418`): "What can be fixed is the
*silence*: ticket 08 built `hypothesis_near_matches` so a suppressed hypothesis
leaves a trace, and **a hard key collision is the same event arriving through the
index instead of through pgvector.**" The trace is what the design says it wanted,
and the trace ships. The embedding half would widen *recall* -- catch near
duplicates the dedup key spells differently -- and the same paragraph says why
that is a losing chase: "The residual collision rate is 11/165 and cannot be
driven to zero by adding leaves -- three genuinely different SAML defects share
`authentication.federation_trust`." A vocabulary too coarse to separate three real
defects is not made finer by a cosine distance over their prose; a semantic
matcher would suppress or penalise the second SAML finding on the strength of it
resembling the first.

**What keeping it costs, which is not nothing and is not local.**

* `vector` is not a trusted extension. `rk db provision` installs it as
  superuser work (`src/redkraken/migrate.py:381-386`, and `:305` and `:862` on why
  that step needs a superuser at all), and the backup path carries a special case
  for it because "the restore connection is deliberately not a superuser"
  (`src/redkraken/backup.py:75-79`). So an empty pgvector installation is a
  superuser requirement on provision and an exclusion rule on every archive.
* `hnsw_headroom` (`0027_migration_baseline.sql:364-376`) is a live view that
  `check_server_baseline` asserts on, computing index-build headroom against
  `maintenance_work_mem` for two tables that have never held a row -- so it
  answers "infinite" forever and would begin failing on the first day anything
  wrote a vector, which is the worst possible moment for a baseline check to
  start speaking.
* Three always-NULL columns sit on the agent's read surface.

**And building the producer is not a column, it is a new egress path.** The model
calls in this harness all happen inside the child process -- `claude_agent_sdk`
is imported by `src/redkraken/_launch.py` and `src/redkraken/_startup.py` and
nowhere else -- and the runtime that holds the `rk2_runtime` connection makes
none. An embedding producer would put a model call in the runtime, on the
promotion path, for every Hypothesis and every Observation, with a model
identifier that has to stay stable across a campaign or the side tables stop
being comparable. `0010_embeddings.sql:5-6` already anticipates that cost --
"switching models inserts rows instead of rewriting the hot tables, and two models
coexist during a migration" -- which is a migration story for a capability nobody
has needed yet.

**Rejected: building an embedding producer.** It buys recall on a dedup question
the corpus says is bounded by vocabulary, at the price of a per-promotion model
call from the process that holds the database connection.

**Rejected: keeping the schema and deferring.** Deferral is what has already
happened, and it costs a superuser step, an archive exclusion and a baseline check
that is wrong in exactly the way that makes it useless. If semantic dedup is
wanted later, `0010` is thirty lines and the two arms of the CHECK are five; what
would not come back for free is the reasoning, which is why the retiring migration
carries it.

**What the harness gives up, said out loud in the migration that removes it** --
which is this ticket's fifth criterion, and it stands: a Hypothesis that is a
near-duplicate of an existing one in meaning but not in key is promoted as new,
and nothing records the resemblance. The trace that remains is
`key_collision` -- the same event arriving through the index -- and it names the
row it collided with. `candidate_hypothesis_id` stays as it is: `0023_scheduler_ranking.sql:161-166`
says the `penalised` action exists for exactly that lookup and that
`key_collision` "has no candidate row either", so the column is correctly NULL for
the one action that survives, and it goes with the arm that is removed.

## What was measured

`grep -rn "embedding" src/redkraken/*.py` returns **nothing** -- no Python in this
harness computes, stores or reads one. There is no `INSERT` into either embedding
table anywhere in the corpus. `hypothesis_near_matches` has exactly one writer
(`20260814T070000Z__a_proposal_becomes_a_canonical_hypothesis.sql:796-800`) and it
writes `key_collision`, so `hypothesis_near_matches_stage2_cols`
(`0018_vocabularies.sql:429-436`) is satisfied only on its first arm.
`claude_agent_sdk` is imported in two files, both of them the child.
