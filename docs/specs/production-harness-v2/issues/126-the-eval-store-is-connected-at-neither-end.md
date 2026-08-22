# 126 — The eval store is connected at neither end

**What to build:** A decision about `0033_eval_store.sql`: either the grading
run writes its scores into it and something reads them back, or the four tables
and their five read functions are retired.

**Blocked by:** nothing.

**Status:** resolved

- [x] The state is recorded first. `eval_runs` (`0033_eval_store.sql:37`),
      `eval_pair_scores` (`:60`), `eval_fn_attribution` (`:150`) and
      `eval_family_coverage` (`:198`) have no `INSERT` anywhere -- not in a
      function, not in Python, not even a seed row in their own migration. The
      five functions that read them -- `eval_recall_by_kind` (`:244`),
      `eval_precision` (`:260`), `eval_family_coverage_of` (`:286`),
      `eval_key_diff` (`:296`) and `eval_comparable` (`:307`) -- have no caller.
      Twenty-nine columns and twenty-seven CHECK constraints sit between two
      ends that are both open.
- [x] The evaluation that does exist is distinguished from the one that is
      declared. `src/redkraken/evaluation.py` writes `evaluation_programs`
      (`evaluation.py:140`) and is reached by `rk playbook evaluate` and
      `rk playbook cost`. That is a fixture-program registry, not a score: it
      says which Playbook is being measured against which fixture, and nothing
      records how it did.
- [x] The question the ticket answers is whether a run is meant to be
      measurable from the database at all. `run_key` is "the sha256 of
      everything that must be equal for two runs to be repeats of the same
      measurement" and `key_components` keeps the pre-image so two runs that
      differ can be told where (`0033:31-36`); `eval_comparable` exists to
      answer whether two runs may be compared at all. That is a considered
      design for A/B measurement of the hunter, and either it is due or it is
      not.
- [x] The one thing that is not re-decided is the exclusion from the agent's
      read surface. `0033:17-20` gives the reason and it stands: "an eval score
      is a measurement of the hunter, and letting the hunter read it is the one
      thing that would make the measurement worthless."
- [x] If the answer is "later", it is written into the migration corpus rather
      than left as an absence, so the next audit does not re-report four empty
      tables as a hole.

## Why

`docs/research/wiring/23-database-wiring.md` section 3.1: "a whole subsystem
declared with neither end connected". It is the largest single block of
unreachable schema in the database and the only one where every table, every
constraint and every function on both sides is unreached.

`needs-triage` because there is no defect to fix here in the ordinary sense.
Nothing is broken by the eval store being empty; what is wrong is that the
repo's own standard -- a declared thing with no producer is either wired or
documented as deferred -- is unmet for a subsystem this size.

## The decision, taken 2026-08-22

**Retire the four tables and the five readers -- and neither of the two options
as the ticket words them is what gets built. The first is not one insert away
from working, and the second is not a deletion: the migration that removes 033
has to carry the scoring model 033 was missing, or the next design re-derives it
from nothing.**

### Why A is not available

The ticket's first option reads as "the grading run writes its scores into it".
There is no grading run whose scores fit. What a writer would have to supply,
asked of the database rather than of the prose, is:

```
eval_runs:            run_key text, key_components jsonb, sut text
eval_pair_scores:     fixture_id, fixture_kind, gt_declared int, gt_recallable int
eval_fn_attribution:  gt_id text, bucket text, owner text
eval_family_coverage: family_id text
```

Of those, `evaluation.py` already has `fixture_id` and `fixture_kind` --
`fixture.Fixture.kind` even uses the two words the CHECK admits. **Everything
that carries the measurement has no producer anywhere in the repository:**

* `run_key` is defined at `0033_eval_store.sql:31-36` as a digest over
  "catalogue, fixture app, ground truth, **grading.py, metrics.py**, playbook
  set, sut, config". `find . -name grading.py -o -name metrics.py` returns
  nothing. Two of the eight components of the key are files that do not exist,
  so the key cannot be computed, and `eval_key_diff` and `eval_comparable` --
  the two functions that are the design's whole distinguishing value -- are
  functions over it.
* `sut` occurs three times in the entire tree: the comment at `0033:33`, the
  column at `0033:43`, and one row of a wiring report. There is no system-under-
  test identifier in this harness.
* `gt_declared` and `gt_recallable` have no producer. The nearest artefact a
  fixture carries is a `bb:classes` list, and a list of classes is not an
  enumeration of ground-truth entries.
* `gt_id` has no producer and no such identifier exists anywhere, so
  `UNIQUE (pair_score_id, gt_id)` has nothing to key on.
* `eval_gt_accounting` (`0033:102-106`) requires `tp + fn_not_found +
  fn_unproven + fn_suppressed + fn_near_miss = gt_recallable`: **every
  recallable ground-truth entry classified into exactly one of five buckets.**
  That is a per-entry labelling model, not a number a counter produces.

That is fourteen missing values, not one, and together they are a scoring model
-- a ticket several times the size of the one that would wire it.

### Why the grading path is not missing

The corpus already grades Playbooks, at both ends, and it does it with different
tables. `rk playbook evaluate` runs a fixture pair, and
`record_playbook_test_run`
(`20260824T000000Z__a_playbook_earns_stable_against_fixtures_it_did_not_pick.sql:535-540`)
derives the numbers in SQL -- `evaluation.py:32-34` says so out loud: "The
counting is not here. `record_playbook_test_run` derives every number from the
rows the two Programs produced." A measured run filed three `playbook_test_runs`
rows carrying claims, ungrounded, fired-in-scope, out-of-scope, false positives,
discriminating true positives, admitted-secure, tool runs, route and a `run_key`
of its own; and the command read its answer back out of `playbook_test_verdict`
into its own report. **The eval store is not the missing half of a measurement
that exists. It is a second, richer measurement design that was written down and
then overtaken by a simpler one that shipped.**

Note the collision that is not one today: `playbook_test_runs.run_key` is a
digest over playbook, fixture, fixture source, ground truth and skills -- a
different key over a different pre-image from `eval_runs.run_key`. The two
designs do not overlap because one scores a run against a fixture catalogue and
the other counts what one Playbook did against one fixture on one side of a pair.
If `playbook_test_runs` ever grows a per-fixture recall or precision column, they
collide and one has to go; that is the trigger to watch, not a reason to keep
both now.

### Why the second option, as worded, is also not what gets built

"The four tables and their five read functions are retired" describes a
deletion. A deletion is not enough, because the reason they are being removed is
the valuable part: the design's distinguishing value is A/B comparability, and
that value cannot be recovered incrementally, because the pre-image `0033:31-36`
describes is a pre-image of files that do not exist. **The retiring migration's
body is the scoring model**, written as what would have to exist first:

1. a ground-truth entry identifier (`gt_id`) that the fixture corpus carries per
   entry, not per class;
2. `gt_declared` and `gt_recallable` per fixture, i.e. an enumeration rather
   than a list;
3. a per-entry verdict assigning each recallable entry to one of `tp`,
   `fn_not_found`, `fn_unproven`, `fn_suppressed`, `fn_near_miss`;
4. a `sut` identifier for the system under test;
5. a `run_key` pre-image every one of whose components exists in this
   repository.

With those five, the four tables come back as they were and the writer is small.
Without them, "deferred" is a word the next audit will read exactly as this one
did.

**Rejected: a deferral note that says "later".** The ticket's fifth criterion
asks for the deferral to be recorded rather than left as an absence, and that is
right -- but a note that says "pending" about a design whose own key names two
absent modules is not a record, it is a re-report. The five conditions above are
the record; the tables do not need to stay empty in the schema to hold them.

### What is not re-decided

`0033:17-20` stands whichever way this goes: "an eval score is a measurement of
the hunter, and letting the hunter read it is the one thing that would make the
measurement worthless." The same rule applies to `playbook_test_verdict`, which
is the measurement this harness actually has.

## What was measured

`grep` for `INSERT INTO` against all four tables across `src/` and `tools/`:
**zero**. Callers of the five readers outside `0033_eval_store.sql` itself:
**zero each**. `find . -name grading.py -o -name metrics.py`: **nothing**.
`grep -rn "\bsut\b" src/ tools/ docs/research/wiring/`: **three** hits, two of
them the column and its own comment. An actual `rk playbook evaluate` run moved
eleven tables -- including `playbook_test_runs` from 0 to 3 and
`evaluation_programs` from 0 to 6 -- and left all four eval tables at zero rows.

## Correction: `evaluation.py` reaches two writes, not one

The ticket's second criterion says `evaluation.py` "writes `evaluation_programs`
(`evaluation.py:140`)" and that "nothing records how it did". The first half is
right about its own SQL -- the single Python `INSERT` is at `evaluation.py:139-142`
-- but the module also reaches two writes inside SQL functions it calls,
`open_fixture_address` (`evaluation.py:539`) and `record_playbook_test_run`
(`evaluation.py:869`), **and the second of those is where the grade goes**. So
"nothing records how it did" is not true: `playbook_test_runs` records exactly
that, and `playbook_test_verdict` reads it back. The eval store's emptiness is
not evidence that the harness cannot grade a Playbook.

## What was built

`src/redkraken/migrations/20260929T000000Z__the_eval_store_leaves_with_the_model_it_was_missing.sql`,
and nothing else. No Python changed, because the decision was to retire and
because `evaluation.py` was never a writer for these tables in the first place.

**The four tables and the five readers are gone**, readers first. The functions
are dropped before their subjects so that a reader outliving what it reads is
impossible rather than merely unlikely -- `eval_precision` is plpgsql and would
have parsed against absent tables and failed at its first call instead of at
apply time -- and `eval_comparable` goes before `eval_key_diff` because it calls
it. The tables then drop children-first, four plain statements in dependency
order, so no `CASCADE` is written and the blast radius is in the file rather
than in the catalogue. The three `derive_program_id` triggers (`0033:218-228`)
and the row-level-security policies `apply_state_rls()` had given each table go
with their tables.

**The migration's body is the scoring model**, which is the part of the decision
that is not a deletion. The header states what was built, what a writer would
have had to supply, which of those fourteen values has no producer anywhere in
this repository, and then the five conditions -- a per-entry `gt_id`, an
enumerated `gt_declared`/`gt_recallable`, a per-entry verdict into the five
buckets `eval_gt_accounting` partitions, a `sut` identifier, and a `run_key`
pre-image whose every component exists here -- that would have to exist before
the design could be rebuilt. It also records the trigger to watch: if
`playbook_test_runs` ever grows a per-fixture recall or precision column, the
two run-key designs collide and one has to go.

**Three registers were emptied of it, and all three had to be.**
`event_table_exempt` (four rows) because `check_event_coverage()` reports
`exempt_row_missing_table`; `runtime_table_surface` (sixteen rows, four
privileges on each table, every one stamped `66-seed`) because
`check_runtime_privileges()` reports `runtime_table_surface_names_missing_object`;
`purge_cascade_edges` (five rows -- the four from `0033:230-233` plus the fifth
that cited ticket 08's row, `0033:345-347`) because `check_purge_travel()` arm
(a) joins the register to `pg_class` and therefore *cannot* see a stale row for
a table that no longer exists. That last one is the reason the deletion is
written by hand: the check that keeps the register honest goes blind at exactly
the moment the row becomes wrong. Every count is asserted, so a name that
matched nothing fails the migration instead of letting it declare itself
finished.

No `runtime_verb_surface` row was deleted, and the absence is the point: the
five readers were never granted to `rk2_runtime`. `0033:17-20` gives the reason
there are no grants in that file at all, and 029's default privileges cover
tables, not functions closed to `PUBLIC`. The house rule that a `REVOKE` deletes
a matching row has nothing to match, because there was no `GRANT`.

**One constraint the eval store had added to somebody else's table** goes with
it. `hypothesis_near_matches_id_program_key` (`0033:134-148`) exists only
because `eval_fn_attribution.near_match_id` cited that row across the program
boundary. Measured on a migrated database:
`eval_fn_attribution_near_match_id_program_id_fkey` was the only foreign key in
the corpus referencing `hypothesis_near_matches` at all. With it gone the unique
key is an orphan this ticket created, so this ticket removes it.

**What the apply-time assertion claims** is not "four tables were dropped" --
`DROP TABLE` already raises on an absent table. It is that nothing named
`eval_*` survives as a relation or a function, that no row in any of the five
registers still names one, and then the question asked the other way round:
`rk2_state` reaches no column of `playbook_test_runs`. That last arm is
criterion 4 made falsifiable. The rule being kept is about the measurement that
*survives*, not the one that goes, and a retirement that quietly widened the
hunter's read surface would have given up the only thing this ticket said it was
not re-deciding.

**The register rows the wiring gate booked to this ticket are removed**, and the
gate was made to say so both ways before they were: with the four rows still in
`OWED_GAPS`, `tools/check_wiring.py` reports `W6 eval_family_coverage names
owed:126 and this tree has no such gap; remove the row` and the same for the
other three; with them removed it reports neither those nor any new gap.

### Where this ticket was wrong

**"Twenty-nine columns and twenty-seven CHECK constraints" is neither number.**
Counted from `0033_eval_store.sql`: `eval_runs` 10 columns / 1 CHECK,
`eval_pair_scores` 21 / 21, `eval_fn_attribution` 8 / 4, `eval_family_coverage`
6 / 3 -- **45 columns and 29 CHECK constraints**. The 29 is the CHECK count
written onto the column line, and 27 is not the count of anything in the file.
It does not change the argument; it is the one measurement in criterion 1 that
was not taken.

**Everything else criterion 1 states is exact, and was re-measured.**
`INSERT INTO` against the four tables across `src/`, `tools/` and `tests/`:
zero. Callers of the five readers outside `0033` itself: zero each. The four
`CREATE TABLE` line numbers (`:37`, `:60`, `:150`, `:198`) and the five
`CREATE FUNCTION` line numbers (`:244`, `:260`, `:286`, `:296`, `:307`) are all
correct. `find . -name grading.py -o -name metrics.py`: nothing.
`grep -rn "\bsut\b" src/ tools/ docs/research/wiring/`: three hits, exactly the
three the decision names.

**The Correction section's `evaluation.py:539` is four lines late.** The
`open_fixture_address` call is `connection.execute(` at `evaluation.py:534` with
`OPEN_FIXTURE_ADDRESS` at `:535`; `:539` is `origin(subject.fixture),` inside
the argument tuple. The `record_playbook_test_run` citation (`:869`) and the
`INSERT INTO evaluation_programs` citation (`:140`) are both exact. The
substance of the correction -- that the module reaches two writes inside SQL
functions and that the second of them is where the grade goes -- holds, and it
is why the migration can say the grading path is not missing.

**One thing the ticket did not ask about and this file had to answer.** Ticket
126 lists four tables and five functions. It does not mention
`hypothesis_near_matches_id_program_key`, which `0033` added to a table it did
not own, for the sole benefit of a foreign key that is now gone. A retirement
that removed only what the ticket enumerated would have left it behind.
