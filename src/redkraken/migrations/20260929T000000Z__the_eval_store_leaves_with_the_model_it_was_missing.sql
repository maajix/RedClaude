-- ---------------------------------------------------------------------------
-- 20260929T000000Z__the_eval_store_leaves_with_the_model_it_was_missing.sql
--                                                                  (ticket 126)
--
-- WHAT WAS BUILT. `0033_eval_store.sql` declared an A/B measurement harness for
-- the hunter: `eval_runs` (`0033:37`), `eval_pair_scores` (`:60`),
-- `eval_fn_attribution` (`:150`) and `eval_family_coverage` (`:198`) -- forty-
-- five columns and twenty-nine CHECK constraints, counted from the file rather
-- than from ticket 126, which transposed the second number onto the first --
-- read by five functions: `eval_recall_by_kind` (`:244`), `eval_precision` (`:260`),
-- `eval_family_coverage_of` (`:286`), `eval_key_diff` (`:296`) and
-- `eval_comparable` (`:307`). The design's distinguishing value is the last
-- two: `run_key` is "the sha256 of everything that must be equal for two runs
-- to be repeats of the same measurement" and `key_components` keeps the
-- pre-image, so two runs that differ can be told WHERE they differ rather than
-- only THAT they differ (`0033:31-36`).
--
-- WHY IT CANNOT BE REACHED. Both ends are open, and the open end that matters
-- is the writer's. Measured over `src/` and `tools/`: `INSERT INTO` against all
-- four tables, zero; callers of the five readers outside `0033` itself, zero
-- each. That is the symptom. The cause is that the pre-image the key is taken
-- over names things this repository does not contain:
--
--   * `run_key` digests "catalogue, fixture app, ground truth, grading.py,
--     metrics.py, playbook set, sut, config" (`0033:31-36`).
--     `find . -name grading.py -o -name metrics.py` returns nothing. Two of the
--     eight components are files that do not exist, so the key cannot be
--     computed -- and `eval_key_diff` and `eval_comparable`, the whole of the
--     design's distinguishing value, are functions over it.
--   * `sut` occurred three times in the whole tree before this file: the
--     comment at `0033:33`, the column at `0033:43`, and one row of a wiring
--     report. There is no system-under-test identifier in this harness, so the
--     column could only ever have been filled with a literal.
--   * `gt_declared` and `gt_recallable` have no producer. The nearest artefact
--     a fixture carries is a `bb:classes` list, and a list of classes is not an
--     enumeration of ground-truth entries.
--   * `gt_id` has no producer and no such identifier exists anywhere, so
--     `UNIQUE (pair_score_id, gt_id)` has nothing to key on.
--   * `eval_gt_accounting` (`0033:104-106`) requires `tp + fn_not_found +
--     fn_unproven + fn_suppressed + fn_near_miss = gt_recallable`: every
--     recallable ground-truth entry classified into exactly one of five
--     buckets. That is a per-entry labelling model, not a number a counter
--     produces.
--
-- So this is not one INSERT short of working. It is fourteen missing values,
-- and together they are a scoring model -- a larger piece of work than the one
-- that would wire it.
--
-- WHY THE GRADING PATH IS NOT MISSING WITH IT. The corpus already grades
-- Playbooks, at both ends, and does it with different tables. `rk playbook
-- evaluate` runs a fixture pair and `record_playbook_test_run`
-- (`20260824T000000Z__a_playbook_earns_stable_against_fixtures_it_did_not_pick.sql:535-540`)
-- derives every number in SQL; `evaluation.py:32-34` says so out loud -- "The
-- counting is not here." A measured run files `playbook_test_runs` rows
-- carrying claims, ungrounded, fired-in-scope, out-of-scope, false positives,
-- discriminating true positives, admitted-secure, tool runs, route and a
-- `run_key` of its own, and the command reads its answer back out of
-- `playbook_test_verdict`. The eval store is not the missing half of a
-- measurement that exists; it is a second, richer measurement design that was
-- written down and then overtaken by a simpler one that shipped.
--
-- WHAT WOULD HAVE TO EXIST BEFORE IT COULD BE REBUILT. This is the part that
-- does not come back for free, and it is why this file is an argument and not a
-- `DROP`. "Deferred" is a word the next audit reads exactly as this one did; the
-- five conditions below are the record instead. With them, the four tables come
-- back as they were and the writer is small. Without any one of them, the
-- writer cannot be written at all:
--
--   1. a ground-truth entry identifier (`gt_id`) that the fixture corpus
--      carries PER ENTRY, not per class;
--   2. `gt_declared` and `gt_recallable` per fixture -- an enumeration rather
--      than a list, so the two denominators are countable and can differ;
--   3. a per-entry verdict assigning each recallable entry to exactly one of
--      `tp`, `fn_not_found`, `fn_unproven`, `fn_suppressed`, `fn_near_miss`,
--      which is what `eval_gt_accounting` asserts and no counter can supply;
--   4. a `sut` identifier for the system under test;
--   5. a `run_key` pre-image every one of whose components exists in this
--      repository.
--
-- THE COLLISION TO WATCH, which is not one today. `playbook_test_runs.run_key`
-- is a digest over playbook, fixture, fixture source, ground truth and skills --
-- a different key over a different pre-image from `eval_runs.run_key`. The two
-- do not overlap because one scores a run against a fixture catalogue and the
-- other counts what one Playbook did against one fixture on one side of a pair.
-- If `playbook_test_runs` ever grows a per-fixture recall or precision column,
-- they collide and one has to go. That is the trigger for revisiting this file.
--
-- WHAT IS NOT RE-DECIDED. `0033:17-20` stands whichever way this went: "an eval
-- score is a measurement of the hunter, and letting the hunter read it is the
-- one thing that would make the measurement worthless." Nothing here is added
-- to `state_read_surface`, and section 4 asserts the same rule for the
-- measurement that survives: `playbook_test_runs` is the table the grade lands
-- in and `playbook_test_verdict` is the function that reads it back, and the
-- hunter reaches neither.
-- ---------------------------------------------------------------------------


SET client_min_messages = notice;


-- ===========================================================================
-- 1. The five readers
-- ===========================================================================

-- Dropped before the tables they read, so that a reader surviving its own
-- subject is impossible rather than merely unlikely: `eval_precision` is
-- plpgsql and would parse fine against tables that no longer exist, and would
-- then fail at its first call instead of here.
--
-- `eval_comparable` calls `eval_key_diff`, so the caller goes first.

DROP FUNCTION eval_comparable(uuid, uuid, text[]);
DROP FUNCTION eval_key_diff(uuid, uuid);
DROP FUNCTION eval_family_coverage_of(uuid);
DROP FUNCTION eval_precision(uuid, text);
DROP FUNCTION eval_recall_by_kind(uuid, text);


-- ===========================================================================
-- 2. The four tables
-- ===========================================================================

-- Children before parents, so each drop is a plain `DROP TABLE` and no CASCADE
-- is written. A CASCADE here would be a statement whose blast radius the next
-- reader has to reconstruct from the catalogue; four drops in dependency order
-- state it in the file. The three `derive_program_id` triggers (`0033:218-228`)
-- and the RLS policies `apply_state_rls()` gave each table go with them,
-- because both are owned by the table.

DROP TABLE eval_fn_attribution;
DROP TABLE eval_family_coverage;
DROP TABLE eval_pair_scores;
DROP TABLE eval_runs;

-- The sibling key 0033 added to a table it did not own. `0033:134-148` states
-- its own reason: "Nothing referenced `hypothesis_near_matches` before this
-- file, so it does not have one yet", and 017's rule is that a citation between
-- two program-scoped rows carries the program on both sides. The citation was
-- `eval_fn_attribution.near_match_id`; it is gone, and nothing else in the
-- corpus references `hypothesis_near_matches` at all. So the constraint is an
-- orphan this file created, and it is removed by the file that created it
-- rather than left for the next reader to work out who wanted it.
ALTER TABLE hypothesis_near_matches
    DROP CONSTRAINT hypothesis_near_matches_id_program_key;


-- ===========================================================================
-- 3. The registry rows, all three registers
-- ===========================================================================

-- A dropped table that keeps its register rows is worse than one that never had
-- them. `check_event_coverage()` answers with `exempt_row_missing_table` and
-- `check_runtime_privileges()` with a row naming the missing object, so what
-- follows is not tidying: it is the difference between this migration applying
-- and the standing checks failing at the end of the run that applied it.
--
-- Every count is asserted for 114's reason: a name that matched nothing would
-- delete nothing and let this file declare itself finished.

DO $$
DECLARE n integer;
BEGIN
    -- (a) emission. `0033:336-340` classified all four `bookkeeping`, on the
    -- argument that an `eval.scored` event would put the grader's opinion of a
    -- run inside the log the grader is grading. The argument was right and the
    -- tables it was about are gone.
    DELETE FROM event_table_exempt
     WHERE table_name IN ('eval_runs', 'eval_pair_scores',
                          'eval_fn_attribution', 'eval_family_coverage');
    GET DIAGNOSTICS n = ROW_COUNT;
    IF n <> 4 THEN
        RAISE EXCEPTION 'ticket 126: deleted % event_table_exempt row(s), expected 4', n;
    END IF;

    -- (b) the purge graph. Four edges from `0033:230-233` and the fifth from
    -- `0033:345-347` -- the one that cited ticket 08's row, which is the edge
    -- 028 had missed and 033 added back. `check_purge_travel()` arm (a) joins
    -- the register to `pg_class` and so cannot see a row for a table that no
    -- longer exists, which is exactly why it is deleted here by hand: a stale
    -- row would be invisible to the check that is supposed to keep the register
    -- honest.
    DELETE FROM purge_cascade_edges
     WHERE table_name IN ('eval_runs', 'eval_pair_scores',
                          'eval_fn_attribution', 'eval_family_coverage');
    GET DIAGNOSTICS n = ROW_COUNT;
    IF n <> 5 THEN
        RAISE EXCEPTION 'ticket 126: deleted % purge_cascade_edges row(s), expected 5', n;
    END IF;

    -- (c) the runtime's table surface. Sixteen rows, four privileges on each of
    -- four tables, all stamped `66-seed`: 033 sorts after 029, so the four
    -- tables arrived granted by 029's default privileges, and 066's seed
    -- (`20260909T000000Z__the_runtime_holds_what_the_surface_declares.sql:166-167`)
    -- recorded what the catalogue already held. The runtime never called any of
    -- it: the grant was inherited, not asked for.
    DELETE FROM runtime_table_surface
     WHERE table_name IN ('eval_runs', 'eval_pair_scores',
                          'eval_fn_attribution', 'eval_family_coverage');
    GET DIAGNOSTICS n = ROW_COUNT;
    IF n <> 16 THEN
        RAISE EXCEPTION 'ticket 126: deleted % runtime_table_surface row(s), expected 16', n;
    END IF;
END $$;

-- No `runtime_verb_surface` row is deleted, and the absence is the point: the
-- five readers were never granted to `rk2_runtime`. `0033:17-20` says why there
-- are no grants in that file at all -- "an eval score is a measurement of the
-- hunter" -- and 029's default privileges cover tables, not functions closed to
-- PUBLIC. So the house rule that a REVOKE deletes a matching row has nothing to
-- match here, because there was no GRANT.


-- ===========================================================================
-- 4. What this migration claims, asserted
-- ===========================================================================

-- The claim is not "four tables were dropped" -- `DROP TABLE` already raises if
-- the table is absent. It is that the eval store leaves NOTHING behind: no
-- relation under that name, no function, and no row in any of the five
-- registers that could later be read as a hole where a subsystem used to be.
-- The last arm asks the question the other way round, about the measurement
-- that survives rather than the one that goes: `playbook_test_runs` is the
-- Playbook grade this harness really keeps, and 0033's rule about who may read
-- a score has to hold for it or the rule left with the tables.

DO $$
DECLARE
    v_left text;
    v_n    integer;
BEGIN
    SELECT string_agg(c.relname, ', ' ORDER BY c.relname) INTO v_left
      FROM pg_class c
      JOIN pg_namespace ns ON ns.oid = c.relnamespace AND ns.nspname = 'public'
     WHERE c.relname LIKE 'eval\_%';
    IF v_left IS NOT NULL THEN
        RAISE EXCEPTION 'ticket 126: relations named eval_* survive the retirement: %', v_left;
    END IF;

    SELECT string_agg(p.proname, ', ' ORDER BY p.proname) INTO v_left
      FROM pg_proc p
      JOIN pg_namespace ns ON ns.oid = p.pronamespace AND ns.nspname = 'public'
     WHERE p.proname LIKE 'eval\_%';
    IF v_left IS NOT NULL THEN
        RAISE EXCEPTION 'ticket 126: functions named eval_* survive the retirement: %', v_left;
    END IF;

    SELECT count(*) INTO v_n FROM (
        SELECT table_name FROM event_table_exempt
        UNION ALL SELECT table_name FROM purge_cascade_edges
        UNION ALL SELECT table_name FROM runtime_table_surface
        UNION ALL SELECT table_name FROM state_read_surface
        UNION ALL SELECT table_name FROM program_global_tables
    ) r WHERE r.table_name LIKE 'eval\_%';
    IF v_n <> 0 THEN
        RAISE EXCEPTION 'ticket 126: % register row(s) still name an eval_* table', v_n;
    END IF;

    -- The one thing 0033 was right about, asserted rather than trusted: the
    -- table that took its place must not be readable by the model either. A
    -- retirement that quietly widened the hunter's read surface would have
    -- given up the only rule this ticket said it was keeping.
    SELECT count(*) INTO v_n
      FROM pg_attribute a
     WHERE a.attrelid = 'playbook_test_runs'::regclass
       AND a.attnum > 0 AND NOT a.attisdropped
       AND (has_column_privilege('rk2_state', a.attrelid, a.attnum, 'SELECT')
            OR EXISTS (SELECT 1 FROM state_read_surface s
                        WHERE s.table_name = 'playbook_test_runs'
                          AND s.column_name = a.attname));
    IF v_n <> 0 THEN
        RAISE EXCEPTION
            'ticket 126: rk2_state reaches % column(s) of playbook_test_runs; that is '
            'the measurement this harness actually has, and 0033:17-20 forbids the '
            'hunter reading its own score', v_n;
    END IF;
END $$;
