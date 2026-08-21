# 127 — The embedding half of dedup has no producer

**What to build:** A decision about semantic deduplication: either something
computes embeddings and the `penalised` near-match action becomes reachable, or
the two embedding tables, their HNSW indexes and the stage-2 columns are
retired.

**Blocked by:** nothing.

**Status:** needs-triage

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
