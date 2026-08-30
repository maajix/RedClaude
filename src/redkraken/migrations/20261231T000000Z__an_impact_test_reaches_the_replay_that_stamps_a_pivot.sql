-- An impact Test reaches the replay that stamps a pivot          (ticket 226)
--
-- The kill chain corpus is 34 functions, 4 tables and a 7-armed standing check,
-- and on 2026-08-30 every table under it held zero rows on a Program that had
-- run 197 laps. `check_kill_chains()` returned nothing, which reads as green
-- and is not: all seven of its arms are `FROM chains`, so an empty table passes
-- every one of them.
--
-- Ticket 226 measured three walls. This file takes the second, which is the one
-- underneath: `replay.IMPACT` -- the only `_Verbs` set that calls
-- `issue_pivot_stamp` and `build_kill_chain` (`replay.py:110-124`) -- is
-- selected in exactly one place, `cli.py:2904`, behind `rk test replay
-- --impact`. That is an operator command. The two callers the harness actually
-- runs, `execution.py::_replay` and `validation.py`, pass no `verbs=` and take
-- the `DETECTION` default, so a pivot has never been stamped by a hunt.
--
-- Making the runtime choose that path is a Python change and it is in the same
-- commit. What is in this file is the Task that would carry it, because there
-- is not one today:
--
--   * `open_impact_task` writes a `tests` row with an `impact_class` and a
--     `hunt` Task naming the Finding (`20260816T000000Z...:1265`). That Task
--     carries no `test_id`, so nothing connects it to the Test it was opened
--     for.
--   * `rk2_test_performance_frontier` excludes `impact_class IS NOT NULL`
--     (`20261014T000000Z...`), so the lane that does perform Tests never sees
--     one.
--
-- So the Test is written and no Task ever performs it. This file adds the
-- frontier and the derivation that do, and widens the one arm of `ready_for`
-- that would refuse the result.
--
-- Scope: the lane and nothing else. Wall 1 of that ticket -- no objective ever
-- asks a child to call `propose_impact_task`, so no impact Test is ever written
-- in the first place -- is the next commit. This one is what makes that one
-- worth making: a Test written into a lane that cannot run it is a row nobody
-- reads.

-- ===========================================================================
-- 1. The frontier, and the derivation that spends it
-- ===========================================================================

CREATE FUNCTION rk2_impact_performance_frontier(p_program_id uuid)
RETURNS TABLE (test_id uuid, hypothesis_id uuid, subject_entity_id uuid,
               finding_id uuid, created_at timestamptz)
LANGUAGE sql STABLE AS $fn$
    SELECT ts.id, ts.hypothesis_id, h.subject_entity_id, k.finding_id, ts.created_at
      FROM tests ts
      JOIN hypotheses h ON h.id = ts.hypothesis_id AND h.program_id = ts.program_id
      JOIN entities e ON e.id = h.subject_entity_id AND e.program_id = h.program_id
      -- The Finding comes off the Task `open_impact_task` opened beside the
      -- Test, because that is the only row that says which Finding this Test is
      -- proving impact on. `tests` carries a hypothesis and a class and no
      -- Finding, and a Finding guessed from the hypothesis would be a guess:
      -- one claim can carry several.
      JOIN LATERAL (
             SELECT x.finding_id FROM tasks x
              WHERE x.program_id = ts.program_id
                AND x.kind = 'hunt'
                AND x.hypothesis_id = ts.hypothesis_id
                AND x.finding_id IS NOT NULL
              ORDER BY x.created_at, x.id LIMIT 1
           ) k ON true
     WHERE ts.program_id = p_program_id
       AND ts.impact_class IS NOT NULL
       AND e.in_scope
       -- `supported` and not `testable`, which is the whole reason this is a
       -- second frontier: the claim settled before the Finding was opened, and
       -- an impact Test is written after that. It is asked for anyway, because
       -- a claim that has since been retracted is one whose impact nobody
       -- should go and prove.
       AND h.status = 'supported'
       AND h.superseded_by IS NULL
       AND EXISTS (SELECT 1 FROM findings f
                    WHERE f.id = k.finding_id AND f.status IN ('validated', 'reported'))
       AND NOT EXISTS (SELECT 1 FROM tests later
                        WHERE later.supersedes_test_id = ts.id)
       -- `test_replays` and not `impact_replays`: `open_impact_replay` reaches
       -- `rk2_open_replay` (`20260816T000000Z...:96`), which writes the
       -- `test_replays` row, so one replay of either kind is one row here. It
       -- is also what `ready_for` refuses on, so the two agree by construction.
       AND NOT EXISTS (SELECT 1 FROM test_replays tp WHERE tp.test_id = ts.id)
       AND NOT EXISTS (SELECT 1 FROM tasks k2
                        WHERE k2.program_id = ts.program_id
                          AND k2.kind = 'perform'
                          AND k2.test_id = ts.id);
$fn$;

COMMENT ON FUNCTION rk2_impact_performance_frontier(uuid) IS
  'Ticket 226. The impact Tests of a Program that no `perform` Task names and no replay has walked, whose claim is still supported and whose Finding is validated. The sibling of `rk2_test_performance_frontier`, which excludes exactly these rows because their claim is settled and can never read `testable` again.';

REVOKE ALL ON FUNCTION rk2_impact_performance_frontier(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rk2_impact_performance_frontier(uuid) TO rk2_runtime;


CREATE FUNCTION derive_impact_performances() RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p        uuid := rk2_program_required();
    ceiling  smallint;
    n_wanted bigint := 0;
    n_tasks  bigint := 0;
BEGIN
    -- The same ceiling as `derive_test_performances`, and deliberately not a
    -- second column, for `derive_finding_bands`'s reason: both open `perform`
    -- Tasks, so one bound over both is the honest reading of "how many
    -- performances may a pass derive". A pass that spends it all on detection
    -- Tests derives no impact runs and the next pass derives them, which is the
    -- deferral the return value already reports.
    SELECT w.max_performances_derived_per_pass INTO ceiling
      FROM scheduler_weights w WHERE w.active;
    IF NOT FOUND THEN RAISE EXCEPTION 'no active scheduler_weights row'; END IF;

    SELECT count(*) INTO n_wanted FROM rk2_impact_performance_frontier(p);

    WITH wanted AS (
        SELECT fr.test_id, fr.hypothesis_id, fr.subject_entity_id, fr.finding_id
          FROM rk2_impact_performance_frontier(p) fr
         ORDER BY fr.created_at, fr.test_id
         LIMIT ceiling
    ), made AS (
        INSERT INTO tasks (program_id, kind, test_id, hypothesis_id,
                           subject_entity_id, finding_id)
        -- `finding_id` is the column that makes this row work at all:
        -- `open_impact_replay` refuses a run whose Task names no Finding
        -- (`20260816T000000Z...:37`), and 008's live-dedup index already keys
        -- on it, so this Task and a detection `perform` Task on the same Test
        -- are two rows without a new index.
        SELECT p, 'perform', w.test_id, w.hypothesis_id, w.subject_entity_id,
               w.finding_id
          FROM wanted w
        RETURNING 1 AS one
    )
    SELECT count(*) INTO n_tasks FROM made;

    RETURN jsonb_build_object('candidates', n_wanted,
                              'derived', n_tasks,
                              'deferred', greatest(n_wanted - n_tasks, 0),
                              'ceiling', ceiling);
END $fn$;

COMMENT ON FUNCTION derive_impact_performances() IS
  'Ticket 226. Opens one `perform` Task per impact Test nobody has performed, carrying `finding_id` -- which `open_impact_replay` requires and which tells this shape from the detection performance in `ready_for`. Bounded by `max_performances_derived_per_pass`, shared with `derive_test_performances` because both open the same kind.';

REVOKE ALL ON FUNCTION derive_impact_performances() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION derive_impact_performances() TO rk2_runtime;


-- ===========================================================================
-- 2. The arm that would otherwise refuse the Task on the pass that derived it
-- ===========================================================================
-- Replaced whole, because that is how this corpus edits a function. Without
-- this, `ready_for` answers `perform.claim_not_testable` for every impact Task:
-- the arm asks the Test's claim to be `testable`, and an impact Test is written
-- after that claim settled. `novelty_for` needs no change -- its `perform` arm
-- reads `test_replays` and nothing about the claim.

CREATE OR REPLACE FUNCTION public.ready_for(t tasks)
 RETURNS text
 LANGUAGE plpgsql
 STABLE
AS $function$
DECLARE ok boolean;
BEGIN
    IF t.subject_entity_id IS NOT NULL THEN
        SELECT e.in_scope INTO ok FROM entities e WHERE e.id = t.subject_entity_id;
        IF NOT coalesce(ok, false) THEN RETURN t.kind || '.subject_not_in_scope'; END IF;
    END IF;

    IF t.kind = 'recon' THEN
        IF t.subject_entity_id IS NULL THEN RETURN 'recon.no_subject'; END IF;
        IF rk2_subject_addressable(t.subject_entity_id) IS NOT TRUE THEN
            RETURN 'recon.no_address';
        END IF;
        RETURN NULL;

    ELSIF t.kind = 'hunt' THEN
        IF t.hypothesis_id IS NULL THEN RETURN 'hunt.no_hypothesis'; END IF;
        IF NOT EXISTS (SELECT 1 FROM hypotheses h
                        WHERE h.id = t.hypothesis_id AND h.status = 'testable') THEN
            RETURN 'hunt.hypothesis_not_testable';
        END IF;
        -- Asked only where there is a subject to ask it about. A hunt Task
        -- with none is undispatchable too, but it is not this predicate's
        -- sentence to say so: `derive_chain_unlocks` takes the subject off the
        -- frontier and a NULL there is the runtime's case, ended by
        -- `retire_task` at the point the URL comes back missing.
        IF t.subject_entity_id IS NOT NULL
           AND rk2_subject_addressable(t.subject_entity_id) IS NOT TRUE THEN
            RETURN 'hunt.no_address';
        END IF;
        RETURN NULL;

    ELSIF t.kind = 'analyze' THEN
        -- "at least one agent-visible artifact reachable from an observation on
        -- the subject". Reachability is ticket 12's `artifact_refs` bridge:
        -- `artifacts` is content-addressed and program-global, so a bare hash
        -- lookup would cross programs.
        IF NOT EXISTS (
             SELECT 1
               FROM observations o
               JOIN receipts r     ON r.id = o.receipt_id
               JOIN artifact_refs x ON x.ref_label = r.label
                                   AND x.program_id = o.program_id
               JOIN artifacts a    ON a.sha256 = x.sha256
              WHERE o.subject_entity_id = t.subject_entity_id
                AND a.visibility = 'agent_visible'
                AND NOT a.encrypted AND a.purged_at IS NULL) THEN
            RETURN 'analyze.no_agent_visible_artifact';
        END IF;
        RETURN NULL;

    ELSIF t.kind = 'perform' THEN
        IF t.test_id IS NULL THEN RETURN 'perform.no_test'; END IF;
        -- Ticket 226. Two shapes under one kind, told apart by
        -- `tests.impact_class` -- the column `rk2_test_performance_frontier`
        -- already excludes on and `open_impact_replay` already refuses a Test
        -- without.
        --
        -- A detection Test settles a claim, so the claim must still be
        -- `testable`. An impact Test is written after the claim settled and
        -- after the Finding on it was validated, so its claim is `supported`
        -- and will never be `testable` again: asking for `testable` here would
        -- refuse every impact Task the moment it was derived. What replaces it
        -- is the condition `open_impact_replay` itself checks, asked before the
        -- run rather than after it.
        IF EXISTS (SELECT 1 FROM tests ts
                    WHERE ts.id = t.test_id AND ts.impact_class IS NOT NULL) THEN
            IF t.finding_id IS NULL THEN RETURN 'perform.no_finding'; END IF;
            IF NOT EXISTS (SELECT 1 FROM findings f
                            WHERE f.id = t.finding_id
                              AND f.status IN ('validated', 'reported')) THEN
                RETURN 'perform.finding_not_validated';
            END IF;
        ELSIF NOT EXISTS (SELECT 1 FROM tests ts
                            JOIN hypotheses h ON h.id = ts.hypothesis_id
                           WHERE ts.id = t.test_id AND h.status = 'testable') THEN
            RETURN 'perform.claim_not_testable';
        END IF;
        IF EXISTS (SELECT 1 FROM test_replays tp WHERE tp.test_id = t.test_id) THEN
            RETURN 'perform.already_performed';
        END IF;
        RETURN NULL;

    ELSIF t.kind = 'conclude' THEN
        IF t.hypothesis_id IS NULL THEN RETURN 'conclude.no_hypothesis'; END IF;
        IF NOT EXISTS (SELECT 1 FROM hypotheses h
                        WHERE h.id = t.hypothesis_id AND h.status = 'supported') THEN
            RETURN 'conclude.claim_not_supported';
        END IF;
        -- Ticket 221. Two shapes under one kind, told apart by `finding_id` --
        -- the column `validate` already uses for exactly this question. A Task
        -- carrying none is 156's: name the Finding this settled claim is one
        -- of, and an edge in `finding_hypotheses` means that work is done. A
        -- Task carrying one is this ticket's: state the band of a Finding a
        -- validation confirmed, and the same edge is its precondition rather
        -- than its refusal.
        IF t.finding_id IS NULL THEN
            IF EXISTS (SELECT 1 FROM finding_hypotheses fh
                        WHERE fh.hypothesis_id = t.hypothesis_id) THEN
                RETURN 'conclude.already_found';
            END IF;
        ELSIF NOT EXISTS (SELECT 1 FROM findings f
                           WHERE f.id = t.finding_id
                             AND f.status IN ('validated', 'reported')) THEN
            -- Not terminal, and `rk2_terminal_predicate` says so without a row:
            -- a candidate Finding is one a validation can still confirm, so a
            -- band Task that arrives early waits rather than ends.
            RETURN 'conclude.finding_not_validated';
        END IF;
        IF t.subject_entity_id IS NOT NULL
           AND rk2_subject_addressable(t.subject_entity_id) IS NOT TRUE THEN
            RETURN 'conclude.no_address';
        END IF;
        RETURN NULL;

    ELSIF t.kind = 'validate' THEN
        IF t.finding_id IS NULL THEN RETURN 'validate.no_finding'; END IF;
        IF NOT EXISTS (SELECT 1 FROM findings f
                        WHERE f.id = t.finding_id AND f.status = 'candidate') THEN
            RETURN 'validate.finding_not_candidate';
        END IF;
        IF NOT EXISTS (SELECT 1 FROM tests ts
                         JOIN finding_hypotheses fh ON fh.hypothesis_id = ts.hypothesis_id
                        WHERE fh.finding_id = t.finding_id) THEN
            RETURN 'validate.no_test_spec';
        END IF;
        RETURN NULL;

    ELSIF t.kind = 'report' THEN
        IF NOT EXISTS (SELECT 1 FROM findings f
                        WHERE f.program_id = t.program_id AND f.status = 'validated') THEN
            RETURN 'report.no_validated_finding';
        END IF;
        RETURN NULL;
    END IF;
    RETURN t.kind || '.unknown_kind';
END $function$;


-- ===========================================================================
-- 2b. And the rule that would end it on the pass after that
-- ===========================================================================
-- `ready_for` calling a Task ready while `cancel_reason_for` abandons it is the
-- pair ticket 152 shipped for `perform` and ticket 156 nearly shipped again,
-- and this ticket walked into it a third time: the arm above makes the Task
-- ready, and this one read the claim as `supported` and answered it.
--
-- 156 already carved one exception out of that rule and wrote down why -- "a
-- settled claim answers the work that was asking whether it holds, and
-- `conclude` is not that work". An impact `perform` is not that work either.
-- The exception is written as what it is rather than as a kind list, which is
-- how 156 wrote its own.

CREATE OR REPLACE FUNCTION cancel_reason_for(t tasks, w scheduler_weights) RETURNS text
LANGUAGE plpgsql STABLE AS $fn$
DECLARE ok boolean; st text; fired boolean; left_ bigint;
BEGIN
    IF EXISTS (SELECT 1 FROM programs p
                WHERE p.id = t.program_id AND p.closed_at IS NOT NULL) THEN
        RETURN 'program_closed';
    END IF;

    SELECT b.tokens_left INTO left_ FROM program_budget b WHERE b.program_id = t.program_id;
    IF left_ IS NOT NULL AND left_ <= 0 THEN RETURN 'budget_exhausted'; END IF;

    -- Ticket 218, and before the attempt counter on purpose. The pair this
    -- compares is the pair `execution.py:2802` compares: the digest and the
    -- projection version the selection froze, against what the catalogue
    -- carries now. Both, because that line refuses on either, and a version
    -- that moved with the digest unchanged is the same document under a
    -- projection the model would read differently.
    IF EXISTS (
        SELECT 1
          FROM playbook_selections s
          JOIN playbooks pb ON pb.id = s.playbook_id
         WHERE s.task_id = t.id
           AND s.dropped_because IS NULL
           AND (pb.source_sha256 IS DISTINCT FROM s.playbook_sha256
                OR pb.version IS DISTINCT FROM s.playbook_version)
    ) THEN
        RETURN 'corpus_moved';
    END IF;

    IF t.attempts >= w.max_attempts THEN RETURN 'attempts_exhausted'; END IF;

    IF t.subject_entity_id IS NOT NULL THEN
        SELECT e.in_scope INTO ok FROM entities e WHERE e.id = t.subject_entity_id;
        IF NOT coalesce(ok, false) THEN RETURN 'out_of_scope'; END IF;
    END IF;

    IF t.hypothesis_id IS NOT NULL THEN
        SELECT h.status, h.superseded_by IS NOT NULL INTO st, ok
          FROM hypotheses h WHERE h.id = t.hypothesis_id;
        IF ok THEN RETURN 'superseded'; END IF;
        -- 034: a refutation suppresses equivalent work only while it is still
        -- current AND something on file settles it. An imported negative is
        -- neither, and `refresh_negative_knowledge` reopens the claim in step
        -- (1) of the same pass that reaches this check in step (2), so the
        -- suppression it would otherwise inherit never survives a pass.
        IF st = 'refuted'
           AND rk2_negative_standing(rk2_current_negative(t.hypothesis_id)) = 'settled' THEN
            RETURN 'settled_negative';
        END IF;
        SELECT EXISTS (SELECT 1 FROM hypothesis_retest_triggers x
                        WHERE x.hypothesis_id = t.hypothesis_id
                          AND x.fired_at IS NOT NULL) INTO fired;
        -- Ticket 156's one exception, written as what it is rather than as a
        -- kind list: a settled claim answers the work that was asking whether
        -- it holds, and `conclude` is not that work -- it is the work that
        -- writes down what the answer was. Only `supported`, because a refuted
        -- claim answers a conclusion too.
        -- Ticket 226's exception, and it is 156's sentence a second time. A
        -- `perform` Task on an impact Test is not the work that was asking
        -- whether the claim holds either -- that work finished, and its
        -- finishing is why there is a validated Finding to prove impact on.
        -- Only `supported`, for the reason above: a refuted claim answers an
        -- impact demonstration too, and more plainly than it answers a
        -- conclusion.
        IF st IN ('supported','refuted') AND NOT fired
           AND NOT (t.kind = 'conclude' AND st = 'supported')
           AND NOT (t.kind = 'perform' AND st = 'supported'
                    AND EXISTS (SELECT 1 FROM tests ts
                                 WHERE ts.id = t.test_id
                                   AND ts.impact_class IS NOT NULL)) THEN
            RETURN 'answered';
        END IF;
        -- a candidate that stage 2 suppressed leaves the hypothesis gone
        IF st IS NULL THEN RETURN 'near_duplicate'; END IF;
    END IF;

    IF t.kind = 'validate' AND EXISTS (
         SELECT 1 FROM findings f WHERE f.id = t.finding_id
           AND f.status IN ('validated','reported','rejected')) THEN
        RETURN 'answered';
    END IF;

    -- The general rule, last: nothing left to learn is nothing worth running.
    --
    -- Except for `report`, and the exception is not a special case -- it is the
    -- one kind whose novelty is a function of rows that have not arrived yet.
    -- `novelty_for('report')` is 1 exactly when an unreported validated finding
    -- exists, so a report task in a young program scores 0, and without this
    -- guard `rank_pass` would abandon it as `answered` on the first pass and
    -- the program would validate findings with no report task left alive. The
    -- admission matrix found this: the fixture happened to validate FG20 before
    -- the first pass, which hid it. Nothing to report yet is unready, not
    -- answered, and `ready_for` already says so.
    IF t.kind <> 'report' AND novelty_for(t) = 0 THEN RETURN 'answered'; END IF;
    RETURN NULL;
END $fn$;

-- ===========================================================================
-- 3. The pass that spends the new frontier
-- ===========================================================================

CREATE OR REPLACE FUNCTION public.rank_pass(p_trigger text DEFAULT 'timer'::text)
 RETURNS jsonb
 LANGUAGE plpgsql
AS $function$

DECLARE
    p            uuid := rk2_program_required();
    w            scheduler_weights%ROWTYPE;
    n_cancelled  bigint := 0;
    n_retired    bigint := 0;
    n_ranked     bigint := 0;
    n_fired      bigint := 0;
    v_retests    jsonb;
    edges        jsonb;
    unlocks      jsonb;
    hunts        jsonb;
    performances jsonb;
    impact_runs  jsonb;
    conclusions  jsonb;
    bands        jsonb;
    by_reason    jsonb;
    top          jsonb;
    doomed       record;
    t0           timestamptz := clock_timestamp();
BEGIN
    SELECT * INTO w FROM scheduler_weights WHERE active;
    IF NOT FOUND THEN RAISE EXCEPTION 'no active scheduler_weights row'; END IF;

    -- (1) Retest re-entry. Decision 11: the pass owns it, because it is the
    -- only runtime step that reads the whole program. 034 moved the body out
    -- into `refresh_negative_knowledge`, which is where the kept refutations
    -- are and where 022's per-Application fingerprint comparison had to go; the
    -- pass keeps the decision about WHEN, which is what decision 11 was about.
    --
    -- It stays first, and that ordering is load-bearing twice over. A claim
    -- whose refutation stopped being current has to be out of `refuted` before
    -- step (2) reads its status, or the Task asking the question again is
    -- abandoned in the same pass that reopened it. And an imported refutation
    -- -- one nothing on file settles -- is reopened here before step (2) could
    -- ever read it as suppression.
    v_retests := refresh_negative_knowledge();
    n_fired   := (v_retests ->> 'reopened')::bigint;

    -- (2) Cancellation, before ranking: a task that should not run must not be
    -- ranked into a slate this pass.
    WITH c AS (
        SELECT t.id, cancel_reason_for(t, w) AS reason
          FROM tasks t WHERE t.program_id = p AND t.status = 'pending'
    ), u AS (
        UPDATE tasks t SET status = 'abandoned', abandoned_reason = c.reason,
                           finished_at = now(), priority = NULL
          FROM c WHERE t.id = c.id AND c.reason IS NOT NULL
        RETURNING t.abandoned_reason AS reason
    )
    SELECT count(*), coalesce(jsonb_object_agg(reason, n), '{}'::jsonb)
      INTO n_cancelled, by_reason
      FROM (SELECT reason, count(*) AS n FROM u GROUP BY reason) g;

    -- (2b) The unreadiness counter, over what step (2) left standing. After
    -- the cancellation rather than before it, because a Task that should not
    -- run at all has already ended and counting it would be counting a row
    -- nobody will read again.
    --
    -- Reset to 0 by the pass that finds it ready, so what the column holds is
    -- the length of the CURRENT run of unready passes and not a lifetime total.
    -- A Task that was blocked for two passes and then ran and then blocked
    -- again has not been blocked for three.
    UPDATE tasks t
       SET unready_passes = CASE WHEN ready_for(t.*) IS NULL THEN 0
                                 ELSE t.unready_passes + 1 END
     WHERE t.program_id = p AND t.status = 'pending';

    -- (2c) Ticket 158, and the whole of it. A Task with no attempts whose
    -- predicate has named the same kind of fact about its own row for
    -- `max_attempts` consecutive passes is a Task the scheduler will never call
    -- ready. It ends the way 143 ends the same state seen from the other side:
    -- `undispatchable`, with the predicate as the sentence on the event.
    --
    -- `attempts = 0` is not decoration. A Task that ran and came back is
    -- `attempts_exhausted`'s case, which step (2) has already answered; this
    -- one is about work that never started and never could.
    --
    -- The same ceiling as the attempts, deliberately. It is the number an
    -- operator already sets to say how many times this scheduler tries
    -- something before giving up on it, and a second knob would be a second
    -- answer to one question.
    -- A loop rather than a count over a subquery that calls it. `retire_task`
    -- is what this step DOES, not a value it reads, and a planner is entitled
    -- to drop an unreferenced target-list column -- which would make the whole
    -- step a no-op that reported the right number of nothings.
    FOR doomed IN
        SELECT t.id, ready_for(t.*) AS predicate
          FROM tasks t
         WHERE t.program_id = p
           AND t.status = 'pending'
           AND t.attempts = 0
           AND t.unready_passes >= w.max_attempts
           AND rk2_terminal_predicate(ready_for(t.*))
    LOOP
        PERFORM retire_task(doomed.id, doomed.predicate);
        n_retired := n_retired + 1;
    END LOOP;

    -- (3) Dependency edges, after cancellation and before ranking, for the
    -- same reason in both directions: a Task abandoned above must stop
    -- unlocking anything, and an edge derived below must be visible to the
    -- ranking in this pass rather than the next one.
    edges := derive_task_dependencies();

    -- (3b) Chain unlocks, after the edges for the first of those two reasons
    -- and before the ranking for the second. Not folded into (3): that function
    -- is 026's two rules over `ready_for` and this one creates Tasks, and a
    -- derivation that both restates a readiness predicate and mints rows would
    -- be two jobs sharing a name and a transaction-local licence.
    --
    -- The Tasks it creates are not put through (2). They cannot need it: the
    -- frontier will not name a subject off the Surface or a superseded
    -- hypothesis, and the other cancellation reasons are about a history a Task
    -- created moments ago does not have. The pass after this one asks anyway.
    unlocks := derive_chain_unlocks();

    -- (3c) Claims into work, after the chain unlocks and before the ranking,
    -- for the second of the two reasons above: a Task derived from a claim must
    -- be ranked in the pass that derived it or it waits a whole pass to be
    -- looked at. It runs after (3b) rather than before it because a chain
    -- unlock is a Task the corpus already knew how to want, and where both
    -- would name the same hypothesis the guard in either one sees the other's
    -- row and does not duplicate it -- whichever ran first.
    --
    -- Like (3b)'s Tasks, these are not put through (2). They cannot need it:
    -- the frontier will not name a subject off the Surface or a superseded
    -- claim, and the other cancellation reasons are about a history a Task
    -- created moments ago does not have. The pass after this one asks anyway.
    hunts := derive_hypothesis_hunts();

    -- (3d) The performances, after the hunts and before the ranking, for the
    -- third time in this function and the same two reasons. A Test authored by
    -- a hunt in the pass before this one is on file with nothing to perform it;
    -- this is what opens the Task that does. Not folded into (3c): that
    -- function grades claims and opens the work that produces a Test, and this
    -- one opens the work that spends one, which is the other end of the same
    -- loop and a different question about a different row.
    --
    -- Like (3b)'s and (3c)'s, these are not put through (2), and for the reason
    -- (3c) gives: a Task created moments ago has no history for a cancellation
    -- rule to read.
    performances := derive_test_performances();

    -- (3d2) The impact performances, immediately after the detection ones and
    -- for the same reason they come after the hunts: a Task derived here can be
    -- ranked in this pass rather than in the next one. Its own step and not a
    -- widening of (3d), because `rk2_test_performance_frontier` excludes
    -- `impact_class IS NOT NULL` deliberately -- an impact Test hangs off a
    -- claim that settled, so it can never satisfy that frontier's
    -- `h.status = 'testable'`, and a frontier told to ignore its own ordering
    -- rule is two frontiers wearing one name.
    impact_runs := derive_impact_performances();

    -- (3e) The conclusions, last of the four and for the same two reasons a
    -- fourth time. This one is the end of the loop rather than a step inside
    -- it: (3c) turns a claim into a question, (3d) spends the answer, and this
    -- opens the work that writes down what the answer was. Ticket 156 -- until
    -- it, a claim reached `supported` and the campaign stopped there, because
    -- `propose_finding` had no Task that would ever put a role holding it in
    -- front of a settled claim.
    --
    -- Not put through (2) either, and here that is not merely unnecessary but
    -- would be wrong: step (2) reads a `supported` claim as an answered
    -- question, and 156's exception is what stops it reading these Tasks that
    -- way at all. Nor through (2b) and (2c): a Task created moments ago has no
    -- run of unready passes behind it, and its counter starts at 0 where the
    -- column's default put it.
    conclusions := derive_finding_claims();

    -- (3f) The bands, after the conclusions and for the reason (3e) comes after
    -- (3d): this is the other end of the same loop. (3e) opens the work that
    -- names what a settled claim is a Finding of; this opens the work that says
    -- what that Finding is worth, once a validation has confirmed it. Ticket
    -- 221 -- until it, a Finding reached `validated` and stopped there, because
    -- `state_severity` had no Task that would ever put a role holding it in
    -- front of a validated Finding.
    --
    -- Not put through (2), (2b) or (2c), for the three reasons (3e) gives: a
    -- Task created moments ago has no history, no unready passes and no
    -- suppression behind it.
    bands := derive_finding_bands();

    -- (4) The ranking. One statement, eight components, no clock in it.
    WITH r AS (
        SELECT t.id,
               novelty_for(t)         AS novelty,
               cost_for(t, w)         AS estimated_cost,
               time_for(t, w)         AS estimated_time,
               safety_for(t, w)       AS safety_cost,
               confidence_for(t, w)   AS confidence,
               value_for(t, w)        AS direct_value,
               unlock_for(t, w)       AS direct_unlock,
               chain_unlock_for(t)    AS chain_unlock
          FROM tasks t
         WHERE t.program_id = p AND t.status = 'pending'
    ), u AS (
        UPDATE tasks t
           SET novelty = r.novelty,
               estimated_cost = r.estimated_cost,
               estimated_time = r.estimated_time,
               safety_cost = r.safety_cost,
               confidence_of_execution = r.confidence,
               direct_value = r.direct_value,
               chain_unlock_value = r.chain_unlock,
               unlock_value = least(r.direct_unlock + r.chain_unlock, 1.0),
               ranked_weights_version = w.version,
               -- NULL, not 0: an unestimated task must sink via NULLS LAST, and
               -- a task scored 0 is a different statement from one never scored
               priority = CASE
                   WHEN r.direct_value IS NULL THEN NULL
                   ELSE r.novelty * r.confidence
                        * (r.direct_value
                           + w.w_unlock * least(r.direct_unlock + r.chain_unlock, 1.0))
                        / greatest(w.w_tokens * r.estimated_cost
                                 + w.w_time   * r.estimated_time
                                 + w.w_safety * r.safety_cost, w.cost_floor)
               END
          FROM r WHERE t.id = r.id
        RETURNING t.id
    )
    SELECT count(*) INTO n_ranked FROM u;

    SELECT coalesce(jsonb_agg(j ORDER BY ord), '[]'::jsonb) INTO top
      FROM (
        SELECT row_number() OVER (ORDER BY t.priority DESC NULLS LAST,
                                           t.created_at, t.id) AS ord,
               jsonb_build_object(
                 'task', t.label, 'kind', t.kind,
                 'priority', round(t.priority, 6),
                 'factors', task_rank_factors(t)) AS j
          FROM tasks t WHERE t.program_id = p AND t.status = 'pending'
          ORDER BY t.priority DESC NULLS LAST, t.created_at, t.id
          LIMIT 10) s;

    INSERT INTO events (program_id, type, actor_kind, payload)
    VALUES (p, 'scheduler.ranked', 'runtime', jsonb_build_object(
        'trigger', p_trigger,
        'weights_version', w.version,
        'candidates', n_ranked,
        'retests', v_retests,
        'abandoned_by_reason', by_reason,
        'retired_unready', n_retired,
        'dependency_edges', edges,
        'chain_unlocks', unlocks,
        'hypothesis_hunts', hunts,
        'test_performances', performances,
        'impact_performances', impact_runs,
        'finding_claims', conclusions,
        'finding_bands', bands,
        'lane_slots', (SELECT coalesce(jsonb_object_agg(kind, live_slots), '{}'::jsonb)
                         FROM scheduler_lane_state WHERE program_id = p),
        'top', top,
        'further_omitted', greatest(n_ranked - 10, 0),
        'duration_ms', round(extract(epoch FROM clock_timestamp() - t0) * 1000)));

    RETURN jsonb_build_object('ranked', n_ranked, 'abandoned', n_cancelled,
                              -- `retests_fired` is 023's key and stays what it
                              -- was: how many claims re-entered. `retests` is
                              -- the breakdown behind it, so a caller can tell a
                              -- pass that reopened nothing because nothing moved
                              -- from one that reopened nothing because it found
                              -- nothing to reopen.
                              'retests_fired', n_fired,
                              'retests', v_retests,
                              -- Beside `abandoned` and not folded into it: one
                              -- is work the engagement answered and the other is
                              -- work this installation could never start, and an
                              -- operator reading a lap needs to tell them apart.
                              'retired_unready', n_retired,
                              'edges_derived', edges -> 'derived',
                              'edges_withdrawn', edges -> 'withdrawn',
                              'unlock_candidates', unlocks -> 'candidates',
                              'unlocks_derived', unlocks -> 'derived',
                              'unlocks_withdrawn', unlocks -> 'withdrawn',
                              'claims_graded', hunts -> 'graded',
                              'hunts_derived', hunts -> 'derived',
                              'hunts_deferred', hunts -> 'deferred',
                              'performances_derived', performances -> 'derived',
                              'performances_deferred', performances -> 'deferred',
                              'impact_runs_derived', impact_runs -> 'derived',
                              'impact_runs_deferred', impact_runs -> 'deferred',
                              'conclusions_derived', conclusions -> 'derived',
                              'conclusions_deferred', conclusions -> 'deferred',
                              'bands_derived', bands -> 'derived',
                              'bands_deferred', bands -> 'deferred');
END
 $function$;


-- ===========================================================================
-- 4. The register
-- ===========================================================================
-- Ticket 66's rule: a verb the runtime may execute has one row in
-- `runtime_verb_surface`, and a grant with no row is a grant nobody declared.
-- The two replaced functions keep the rows they have -- a replacement is the
-- same verb.

INSERT INTO runtime_verb_surface (verb, added_by, note) VALUES
    ('rk2_impact_performance_frontier(uuid)', '226',
     'the impact Tests a perform Task would be opened about: unperformed, unnamed '
     'by any perform Task, resting on a supported claim whose Finding is validated'),
    ('derive_impact_performances()', '226',
     'opens the perform Task that reaches open_impact_replay, carrying finding_id '
     'because that verb refuses a run whose Task names no Finding')
ON CONFLICT (verb) DO NOTHING;
