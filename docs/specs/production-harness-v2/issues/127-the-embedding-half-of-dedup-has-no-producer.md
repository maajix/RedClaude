# 127 — The embedding half of dedup has no producer

**What to build:** A decision about semantic deduplication: either something
computes embeddings and the `penalised` near-match action becomes reachable, or
the two embedding tables, their HNSW indexes and the stage-2 columns are
retired.

**Blocked by:** nothing.

**Status:** resolved

- [x] The producer that does not exist is named. `hypothesis_embeddings`
      (`0010_embeddings.sql:7-13`) and `observation_embeddings` (`:15-21`) each
      hold a `vector(1536)` keyed by model, each carries an HNSW index
      (`:23-26`), and neither has an `INSERT` anywhere. Nothing in the harness
      computes an embedding.
- [x] The consequence on the dedup side is stated. `hypothesis_near_matches`
      (`0012_scheduler.sql:69-79`) declares three actions after
      `0018_vocabularies.sql:429-436`: `suppressed`, `penalised` and
      `key_collision`. Its only writer
      (`20260814T070000Z__a_proposal_becomes_a_canonical_hypothesis.sql:796-800`)
      writes `key_collision` and nothing else, so `similarity` and
      `embedding_model` -- which `hypothesis_near_matches_stage2_cols` requires
      to be NOT NULL for the other two actions -- are never written, and the two
      similarity-based actions are unreachable. The CHECK is satisfiable only on
      its `key_collision` arm.
- [x] `candidate_hypothesis_id` is understood rather than lumped in. It was
      added by `0023_scheduler_ranking.sql:165-166` so that from the Hypothesis
      a candidate became there is a way back to the row, and `0023:161-164` says
      the `penalised` action exists for exactly that lookup and that
      `key_collision` "has no candidate row either". It is NULL today because
      the only action written is the one that correctly has no candidate, not
      because a writer forgot it.
- [x] `hnsw_headroom` (`0027_migration_baseline.sql:364-376`) is decided with
      the rest. It counts rows in the two embedding tables against
      `maintenance_work_mem` to say whether the next index build spills to disk,
      and `check_server_baseline` asserts on it. It is a live check over two
      permanently empty tables: the answer is always "infinite headroom", and it
      will stop being true on the first day anything writes a vector.
- [x] Whichever way it goes, `0018_vocabularies.sql:414-421` keeps its point:
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

## The blast radius, measured 2026-08-22 before anything was written

Kept because it is the reading the retirement was planned from, and because one
line of it turned out to be wrong in a way worth leaving visible (the
`runtime_table_surface` count below says eight; it is twelve -- `hnsw_headroom`
is a relation and carries four rows of its own). The decision above was not
re-opened.

### The headline element cannot be done by a migration at all

"pgvector comes out of the provision path with them" is not a `DROP EXTENSION`
in a `.sql` file. Measured on a freshly provisioned and fully migrated database:

```
vector owner                                  postgres, pgvector 0.8.6
rk2_migrate rolsuper                          false
pg_has_role('rk2_migrate','postgres','USAGE') false
[as rk2_migrate] DROP EXTENSION vector        42501: must be owner of extension vector
```

The extension is created by the superuser step (`src/redkraken/migrate.py:381`),
so only that step can uncreate it. There is no arrangement of migration SQL that
removes it, which means this element is `src/redkraken/migrate.py` and nothing
else.

Two other facts from the same measurement, both confirming the decision's own
reading:

```
[as rk2_migrate] DROP TABLE observation_embeddings
    2BP01: cannot drop table observation_embeddings because other objects
           depend on it | view hnsw_headroom depends on table observation_embeddings
[as rk2_migrate] ALTER TABLE hypothesis_near_matches DROP COLUMN similarity
    SUCCEEDED
```

So the two tables and `hnsw_headroom` are one unit that has to move together --
the view cannot be left standing over a dropped table -- and the near-match
columns are the one part a migration can do unaided.

### Every part of the decision reaches `tests/test_database.py`

Each of the four parts was checked against the suite as it stands. All four
subjects currently pass; the four tests below were run and reported `ok`, so
nothing here is a pre-existing failure.

| Part of the decision | Test it removes the subject of |
| --- | --- |
| drop `hypothesis_embeddings` / `observation_embeddings` | `tests/test_database.py:2697-2714`, `NegativeControlTest.test_an_index_the_server_cannot_build_fails_the_headroom_check` -- it arranges the failure by `INSERT INTO hypothesis_embeddings` at `:2708-2712` and asserts `"baseline:hnsw_headroom" in failed` at `:2714` |
| drop `hnsw_headroom` and its baseline arm | `tests/test_database.py:2918`, inside `NegativeControlTest.test_every_check_the_gate_runs_has_a_control`: `covered` is seeded with `"baseline:hnsw_headroom"` and `:2922` asserts `covered - ran` is empty, so a gate that stops running the check fails there |
| drop the two similarity arms of `hypothesis_near_matches` | `tests/test_database.py:13713-13726`, `HypothesisPromotionTest.test_the_statement_that_converged_is_kept_as_a_key_collision`, which selects `nm.similarity, nm.embedding_model` at `:13715-13716` and asserts both are NULL at `:13724-13725`; without the columns the query raises 42703 |
| pgvector out | `tests/test_database.py:2552-2553` (`RUNTIME_CONTROLS` rows `baseline:pgvector_version` and `baseline:hnsw_cosine_opclass`, exercised at `:2686-2696`, which asserts each named check is the *only* failing row of `evaluate_server_runtime`), `:1028-1029` (`CONTROLS` rows `baseline:hnsw_iterative_scan` and `baseline:hnsw_max_scan_tuples`), and `:519-520` (`CleanCreationTest` asserts both settings are green) |

### The files a complete change has to write, with lines

* `tests/test_database.py` -- `:519-520`, `:1028-1029`, `:2552-2553`,
  `:2697-2714`, `:2918`, `:13713-13726`. Six sites, five test methods.
* `src/redkraken/migrate.py` -- `:381` (`CREATE EXTENSION IF NOT EXISTS
  vector`), `:383-386` (the `extversion` read and `ledger.hold("extension:vector",
  ...)`), `:302-306` (the `provision()` docstring, which names the extension as
  the third of the three things a database owner cannot do for itself), and
  `:862-863` (`_assert_superuser`'s failure text, "roles, databases and the
  vector extension cannot be created without one").
* `src/redkraken/backup.py` -- `:76-82`, `PROVISIONED_EXTENSIONS = ("vector",)`
  and the paragraph above it. Once nothing provisions the extension, the archive
  exclusion names something that is not there.
* `tests/test_backup.py:282` -- `self.assertEqual(("vector",),
  backup.PROVISIONED_EXTENSIONS)`, which pins the tuple above.

### One coupling the decision does not mention

`apply_server_settings()` (`0028_server_settings.sql:44-135`) opens with
`PERFORM '[1]'::vector` at `:56` and then sets `hnsw.iterative_scan` (`:127`)
and `hnsw.max_scan_tuples` (`:133`). `0028:46-55` explains why that cast is
there and is not redundant: `CREATE EXTENSION` does not load the library, and until it is loaded
`hnsw.*` is an undefined custom GUC that only a superuser may define. It is a
**finalizer**, re-executed on every `rk db migrate` -- so the moment the
extension is gone, every subsequent migration run fails on that one line. The
three settings are live on the database today:

```
maintenance_work_mem=256MB  hnsw.iterative_scan=relaxed_order  hnsw.max_scan_tuples=40000
```

`maintenance_work_mem` stays -- it is not a pgvector setting and
`0028:59-93` argues it on its own terms with a measured sweep -- but the two `hnsw.*` values have to
be `RESET` on the database as well as removed from the function, or a
`pg_db_role_setting` row survives naming a GUC prefix no extension defines. That
is inside a migration and so is not a blocker; it is a fifth thing the change
has to carry, and it is not in the decision's list.

### What is still true and does not need re-measuring

* `grep -rn "embedding" src/redkraken/*.py` returns nothing.
* There is no `INSERT` into either embedding table anywhere in the corpus.
* `hypothesis_near_matches` has exactly one writer,
  `20260814T070000Z__a_proposal_becomes_a_canonical_hypothesis.sql:796-800`, and
  it writes `key_collision` with neither stage-2 column -- confirmed by reading
  the statement, which names only `program_id, candidate_statement,
  matched_hypothesis_id, action, agent_run_id`.
* All three of `similarity`, `embedding_model` and `candidate_hypothesis_id` are
  on `state_read_surface` today, which is the decision's "three always-NULL
  columns sit on the agent's read surface", confirmed against a migrated
  database.
* `runtime_table_surface` holds eight `66-seed` rows for the two embedding
  tables (four privileges each), `event_table_exempt` two (`derived`, owner
  ticket `06`, `0027_migration_baseline.sql:73-74`) and `purge_cascade_edges`
  two (`0016_event_log_corrections.sql:216-217`). All twelve have to go with the
  tables, for the reason ticket 126's migration gives: two of the three
  registers are policed by checks that report a row naming a missing table, and
  the third is policed by a check that joins to `pg_class` and therefore goes
  blind at exactly the moment the row becomes wrong.

## Built, 2026-08-22

`src/redkraken/migrations/20261003T000000Z__a_key_collision_is_the_whole_of_the_trace.sql`
carries the retirement and the reasoning. All five criteria are ticked: the
absent producer, the consequence on the dedup side, `candidate_hypothesis_id`,
`hnsw_headroom` and what the harness gives up are each stated in the migration
header, and each is the reason for a statement in the file rather than a note
beside one.

**What went.** The two embedding tables and their HNSW indexes; `hnsw_headroom`
and `hnsw_bytes_per_tuple`; the `hnsw_headroom` arm of `check_server_baseline`;
the `suppressed` and `penalised` actions of `hypothesis_near_matches`, its
`similarity`, `embedding_model` and `candidate_hypothesis_id` columns and the
three constraints and one index over them; and sixteen register rows -- two
`event_table_exempt`, two `purge_cascade_edges`, twelve `runtime_table_surface`
(the two tables and `hnsw_headroom`, four privileges each) -- plus three
`state_read_surface` rows.

**Two couplings the decision above did not name, both paid.** `novelty_for`
(`0023:325-329`) was the only reader of `similarity` in the corpus and
`check_scheduler_closure` arm (e) (`0023:1186-1189`) was the only reader of
`candidate_hypothesis_id`; both are string-bodied, so neither would have refused
the `ALTER TABLE` and both would have failed at their next call instead. They are
replaced in place -- `CREATE OR REPLACE`, so `novelty_for(tasks)` keeps the grant
its `runtime_verb_surface` row declares. `novelty_for('hunt')` returns the same
number it always did: `coalesce(1 - sim, 1)` was 1 on every row, because no
writer ever filled the column.

**A third, from the parent's brief, paid differently than expected.**
`apply_server_settings()` (`0028:56`) opens with `PERFORM '[1]'::vector` and is a
finalizer re-run on every `rk db migrate`, so it would break the moment the
extension went. The extension does not go (below), so it does not break -- but
the two `hnsw.*` values it sets tune an HNSW index scan and there is no HNSW
index left, so they are out of the finalizer and `ALTER DATABASE ... RESET` on
the database, with their two baseline arms. `maintenance_work_mem = 256MB` stays
and `0028:59-93` still argues it. The vector cast survives once, in this
migration, because the owner cannot reset a `hnsw.*` GUC until the library that
defines it is loaded.

**The one element of the decision that was not paid, and why.** "pgvector comes
out of the provision path with them" is not payable from `src/redkraken/migrate.py`,
which is where the previous reading placed it. The obstacle is
`src/redkraken/migrations/0001_extensions.sql:2` -- `CREATE EXTENSION IF NOT
EXISTS vector` -- which runs as `rk2_migrate` on every database this corpus is
applied to from empty. Measured on a fresh database with no `vector` in it:

```
[as rk2_migrate] CREATE EXTENSION IF NOT EXISTS vector
    ERROR:  permission denied to create extension "vector"
    HINT:   Must be superuser to create this extension.
```

It is a no-op today only because `provision()` (`migrate.py:381`) installed the
extension as a superuser first. Take the install out and `rk db migrate` cannot
reach migration two. So `migrate.py`, `backup.py` and `tests/test_backup.py` are
unchanged, `backup.PROVISIONED_EXTENSIONS` still names `vector`, and the
`pgvector_version` and `hnsw_cosine_opclass` baseline arms stay: all three are
still true statements about what applying this corpus requires. The line drawn
is between the PRESENCE of the extension, which the corpus still demands, and the
BEHAVIOUR of HNSW indexes, of which there are now none. Section 6(f) of the
migration asserts the extension is still there and names, in its failure text,
the four things that have to move in one change when `0001` can finally be
rewritten -- it is the only assertion in the file that is asking to be broken.

One consequence worth recording for whoever does it: after this migration nothing
in the schema uses the `vector` type, so `--exclude-extension=vector` no longer
excludes any table definition from an archive -- only the `COMMENT ON EXTENSION`
`pg_dump` emits, which is still superuser work the restore connection cannot do.

**Tests.** `tests/test_database.py`: the two `hnsw.*` settings assertions became
`assertNotIn`; the two `CONTROLS` rows for their baseline arms are gone;
`baseline:hnsw_headroom` is off the `covered` seed;
`test_an_index_the_server_cannot_build_fails_the_headroom_check` is replaced by
`test_no_vector_column_is_left_for_a_headroom_check_to_measure`, which asks the
catalogue for a `vector` column rather than the two table names; and
`test_the_statement_that_converged_is_kept_as_a_key_collision` no longer selects
the two dropped columns, with
`test_the_near_match_vocabulary_admits_no_action_but_the_collision` added beside
it so that `penalised` being refused is measured rather than assumed.
`tools/check_wiring.py` loses both `owed:127` rows: W6 no longer reports either
table, because the checker applies drops in corpus order.

## Finished and measured, 2026-08-22

The section above was written before the change had been run. What follows is
the same change after it was completed and executed, and it names the one thing
that was missing.

**What was missing: house rule G8.** The file moved the closed set on
`hypothesis_near_matches.action` from three spellings to one and re-issued
`COMMENT ON TABLE` only. G8 is about the column -- "a migration that moves a
constraint, a default or a closed set on a column must re-issue that column's
`COMMENT ON` in the same file" -- and it is the rule ticket 115 was raised to
pay off by hand and ticket 130 will mechanise. `COMMENT ON COLUMN
hypothesis_near_matches.action` is now issued beside the `ALTER TABLE` that
moves the CHECK, in the shape `20260922T060000Z:105` set. The column had no
live comment before this file; a reader of `\d+ hypothesis_near_matches` who
saw a one-element CHECK would otherwise have had nothing on the relation
saying whether the other two actions were coming back.

**The corpus applies and the gate passes.** Measured against a `git archive
HEAD` tree carrying only this ticket's two files, so nothing another agent has
in the shared working tree is being credited or blamed:

```
tests.test_database.CleanCreationTest NegativeControlTest HypothesisPromotionTest
    ArchiveTest ProgramPurgeTest RuntimePrivilegeSurfaceTest
Ran 84 tests in 361.444s
OK
```

`CleanCreationTest` is the one that matters most here: it applies the corpus
from empty, so every assertion in section 6 of the migration -- no `vector`
column left, no `hnsw.*` row left in `pg_db_role_setting`, the action CHECK
closed on `key_collision` alone, the writer's five columns intact, sixteen
register rows gone and `maintenance_work_mem` still set -- is executed on a
real server as a condition of that run passing. `ArchiveTest`,
`ProgramPurgeTest` and `RuntimePrivilegeSurfaceTest` were added to the batch
because the change deletes rows from `purge_cascade_edges`,
`runtime_table_surface` and `event_table_exempt` and rewrites the
`apply_server_settings` finalizer; all three are green.

The same three primary classes were then run again in the shared working tree,
alongside four migrations four other tickets have in flight, to show this file
does not collide with any of them:

```
tests.test_database.CleanCreationTest NegativeControlTest HypothesisPromotionTest
Ran 56 tests in 319.513s
OK
```

**The four gates.**

```
PYTHONPATH=$PWD python3 -s tools/check_audit.py           rc=0
PYTHONPATH=$PWD python3 -s tools/check_wiring.py          rc=1
PYTHONPATH=$PWD python3 -s tools/check_baseline.py        rc=0
PYTHONPATH=$PWD/src:$PWD python3 -s tools/check_coverage.py rc=0
```

`check_wiring` in the isolated tree reports exactly two lines, both of them the
`OWED_GAPS` rows this change makes false and neither of them removable from here
-- `tools/check_wiring.py` is held by another agent this round:

```
register: W6 hypothesis_embeddings names owed:127 and this tree has no such gap; remove the row
register: W6 observation_embeddings names owed:127 and this tree has no such gap; remove the row
```

**The unpaid element, re-measured rather than restated.** The decision's
"pgvector comes out of the provision path with them" is still unpaid, and the
obstacle is now measured from the catalogue rather than from a single error
message:

```
SELECT rolname, rolsuper FROM pg_roles WHERE rolname = 'rk2_migrate'
    ('rk2_migrate', False)
SELECT DISTINCT name, version, trusted, superuser
  FROM pg_available_extension_versions WHERE name = 'vector'
    ('vector', '0.8.6', False, True)
```

`trusted = false` and `superuser = true` is the general form of the previous
reading's `permission denied to create extension "vector"`: no non-superuser
can install it, on any database, whatever the ownership. So
`0001_extensions.sql:2` -- `CREATE EXTENSION IF NOT EXISTS vector`, run as
`rk2_migrate` -- can only ever be the no-op it is today, and only because
`provision()` installed the extension first. `src/redkraken/migrate.py`,
`src/redkraken/backup.py` and `tests/test_backup.py:282` are therefore
unchanged, and section 6(f) of the migration is the assertion that will fail
when `0001` can finally be rewritten.

**One thing found outside this ticket's files and not written to.**
`docs/adr/0001-rows-authoritative-events-same-transaction.md:13` gives three
hot paths as the reason rows are authoritative: "recursive CTE traversal over
the attack-surface graph, `FOR UPDATE SKIP LOCKED` on the task queue, and
pgvector similarity search". The third no longer exists after this file. The
decision stands on the other two, so this is a stale sentence rather than a
withdrawn ADR, and it belongs to whoever holds `docs/adr/`.
