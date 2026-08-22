-- ---------------------------------------------------------------------------
-- an_authored_test_is_performed_by_a_task.sql   (ticket 152)
--
-- A hunt authors a Test and nothing performs it. `rk2hunt11` and `rk2hunt12`
-- both reached four Tests with `test_replays = 0` and `findings = 0`: every
-- claim stayed `testable`, so no Finding could rest on one, so no `validate`
-- Task could be minted from one, and the whole tail of the pipeline sat behind
-- a step nobody took.
--
-- `replay.run` is the performer and has been since ticket 35. What it lacked
-- was a caller: its one entry is `rk test replay`, and an operator cannot use
-- it after the fact, because a replay is attributed to an Agent run that has
-- not ended and every run this harness opens has ended by the time a person
-- could type the command.
--
-- So the Task is the caller. `perform` is a kind like the other five: the
-- scheduler derives it, ranks it, offers it, and the claim opens the Agent run
-- the replay is attributed to. Its role is a renderer -- the second one, after
-- `reporter` -- because a replay walks a specification somebody else authored
-- and there is nothing in it for a model to decide.
-- ---------------------------------------------------------------------------

-- ===========================================================================
-- 1. The role and the kind
-- ===========================================================================
--
-- Three rows, in the order the foreign keys need them. `role_task_kinds` is
-- UNIQUE on kind, so this is also the statement that says `perform` is the
-- performer's and nobody else's.
--
-- A renderer, and the schema's own two rules for one say what that costs:
-- `roles_renderer_runs_no_model` requires 'none'/'none' and
-- `agent_runs_renderer_spends_nothing` refuses a run of it that reports a
-- token. Both are correct here and neither is a workaround -- a replay makes
-- HTTP requests through the door and never reaches an API.

INSERT INTO roles (role, runs_as, invocable_by, executes_tasks, max_concurrent,
                   clamp_to_identity_leases, model, effort, loads_skills) VALUES
    ('performer', 'renderer', ARRAY['runtime']::text[], true, 1, false,
     'none', 'none', false);

COMMENT ON TABLE roles IS
  'The seven roles of ticket 11''s roster, compiled from roles.yaml, plus ticket 152''s performer. Global: one roster for the harness, so a program cannot grant a role something another program forbids.';

INSERT INTO task_kinds (kind) VALUES ('perform');

INSERT INTO role_task_kinds (role, kind) VALUES
    ('performer', 'perform');

-- The lane, which is the third thing a kind needs to exist. `lane_capacity` is
-- a view over `scheduler_lanes` joined to the mapping above, so a kind with no
-- lane row has no capacity at all and `check_role_kind_mapping` says so. One
-- slot and no floor: a replay is not work the scheduler should insist on
-- starting, it is work that becomes available when a hunt has authored
-- something to perform.

--
-- The seed goes in with the trigger off and the trigger goes back on ALWAYS,
-- which is 016's required state and the shape 20260815 already used for the
-- same reason. 037 froze this table against the write it was worried about --
-- an unversioned quota move by a runtime -- and a new kind's default lane is
-- neither: it is the schema growing, in a migration, once.

ALTER TABLE scheduler_lanes DISABLE TRIGGER scheduler_lanes_no_unversioned_write;

INSERT INTO scheduler_lanes (program_id, kind, min_slots) VALUES
    (NULL, 'perform', 0);

ALTER TABLE scheduler_lanes
    ENABLE ALWAYS TRIGGER scheduler_lanes_no_unversioned_write;

-- And the fourth: the ranking priors. `check_scheduler_closure` refuses a kind
-- missing from `cost_prior` by name, and it is right to -- `cost_for` reads the
-- kind out of that document, and a NULL cost fails the affordability comparison
-- silently, so the Task would be ranked and never offered.
--
-- The two numbers are the lowest in the table, and the reason is what a
-- performer is: a renderer that spends no token and walks between 3 and 32
-- requests somebody else wrote down. It is the cheapest work this scheduler
-- has, and the estimate should say so.

--
-- A version is immutable, so the trigger comes off and goes back on ALWAYS,
-- the same shape the lane seed above uses. Not `version_scheduler_weights`,
-- which is the right verb for a policy move and the wrong one for this: every
-- existing version was written before this kind existed, so none of them
-- states a policy about it, and cutting a new version would say an operator
-- had changed their mind about weights they never had the chance to set.
-- Completing the document is what makes the old versions replayable at all.

ALTER TABLE scheduler_weights
    DISABLE TRIGGER scheduler_weights_versions_are_immutable;

UPDATE scheduler_weights
   SET cost_prior = cost_prior || '{"perform": 0.10}'::jsonb,
       time_prior = time_prior || '{"perform": 0.20}'::jsonb;

ALTER TABLE scheduler_weights
    ENABLE ALWAYS TRIGGER scheduler_weights_versions_are_immutable;

-- ===========================================================================
-- 2. A Task names the Test it performs
-- ===========================================================================
--
-- The same shape ticket 08 D13 gave `validate`: a kind that acts on one row
-- has to be able to name it, and the dedup key has to grow with the column or
-- two `perform` Tasks for two different Tests of one claim collide on
-- (program, kind, NULL subject, hypothesis, NULL finding).

-- The composite key and NO ACTION, both of them the schema's own rules rather
-- than a preference: 017 refuses a cross-table foreign key that does not carry
-- `program_id`, because a bare `id` reference is a row in one Program pointing
-- at a row in another; and 016 refuses an unregistered `ON DELETE CASCADE`,
-- because a purge that travels an edge nobody wrote down is a purge nobody can
-- predict. A Task dies with its Program through `tasks_program_id_fkey`, which
-- is the edge that is registered.

ALTER TABLE tasks ADD COLUMN test_id uuid;
ALTER TABLE tasks ADD CONSTRAINT tasks_test_fk
    FOREIGN KEY (test_id, program_id) REFERENCES tests(id, program_id);

COMMENT ON COLUMN tasks.test_id IS
  'The Test a `perform` Task performs. NULL for every other kind: a Task acts on a subject, a claim, a Finding or a Test, and which of the four is what its kind means.';

DROP INDEX tasks_live_dedup_idx;
CREATE UNIQUE INDEX tasks_live_dedup_idx
    ON tasks (program_id, kind, subject_entity_id, hypothesis_id, finding_id, test_id)
       NULLS NOT DISTINCT
 WHERE status IN ('pending','claimed','running','parked');

-- The lane quota profiles, which are the last thing a kind needs: 037 refuses a
-- profile that does not name every kind, because a lane missing from one
-- silently reverts to the default and that is a quota move nobody wrote down.
--
-- No floor in any of the three, and the same reason each time. An entitlement
-- is a slot held open for work that should always be able to start; a
-- performance can only exist once a hunt has authored something to perform, so
-- a floor would be holding a slot for work that is not there yet.

INSERT INTO lane_quota_profile_slots (profile, kind, min_slots) VALUES
    ('breadth',  'perform', 0),
    ('balanced', 'perform', 0),
    ('depth',    'perform', 0);

-- ===========================================================================
-- 3. When one is ready
-- ===========================================================================
--
-- Re-stated whole rather than patched, because `ready_for` is one CASE over
-- the kind vocabulary and a kind with no arm falls through to
-- `unknown_kind` -- which is not a refusal an operator can act on, it is the
-- scheduler saying this kind was never taught to it.
--
-- Three conditions, and the third is the one that closes ticket 152's loop:
-- a Test that has been performed is not ready to be performed again, so the
-- derivation below cannot mint a second Task for it and a Task that somehow
-- outlived its replay stops being offered.

CREATE OR REPLACE FUNCTION ready_for(t tasks) RETURNS text
LANGUAGE plpgsql STABLE AS $fn$
DECLARE ok boolean;
BEGIN
    IF t.subject_entity_id IS NOT NULL THEN
        SELECT e.in_scope INTO ok FROM entities e WHERE e.id = t.subject_entity_id;
        IF NOT coalesce(ok, false) THEN RETURN t.kind || '.subject_not_in_scope'; END IF;
    END IF;

    IF t.kind = 'recon' THEN
        IF t.subject_entity_id IS NULL THEN RETURN 'recon.no_subject'; END IF;
        RETURN NULL;

    ELSIF t.kind = 'hunt' THEN
        IF t.hypothesis_id IS NULL THEN RETURN 'hunt.no_hypothesis'; END IF;
        IF NOT EXISTS (SELECT 1 FROM hypotheses h
                        WHERE h.id = t.hypothesis_id AND h.status = 'testable') THEN
            RETURN 'hunt.hypothesis_not_testable';
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
        IF NOT EXISTS (SELECT 1 FROM tests ts
                         JOIN hypotheses h ON h.id = ts.hypothesis_id
                        WHERE ts.id = t.test_id AND h.status = 'testable') THEN
            RETURN 'perform.claim_not_testable';
        END IF;
        IF EXISTS (SELECT 1 FROM test_replays tp WHERE tp.test_id = t.test_id) THEN
            RETURN 'perform.already_performed';
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
END $fn$;

-- ===========================================================================
-- 4. What the runtime accepts as this Task's result
-- ===========================================================================
--
-- `finish_task_attempt` closes a Task as `done` only where a structured result
-- of it has been accepted, and `enforce_task_completion` refuses any other
-- `done`. A `perform` Task promotes no proposal and answers no validation, so
-- without this arm every one of them would go back to the queue with an
-- attempt spent and be abandoned as `attempts_exhausted` after the third --
-- having performed its Test three times.
--
-- The Test run is the result. It is written by `close_test_replay` inside the
-- transaction that settles the claim, so it exists exactly where the replay
-- reached a verdict and nowhere else: a replay that opened and died leaves a
-- `tool_runs` row and no `test_runs` row, which is the Task correctly not done.

CREATE OR REPLACE FUNCTION task_result_accepted(p_task uuid) RETURNS boolean
LANGUAGE sql STABLE AS $fn$
    SELECT EXISTS (SELECT 1 FROM proposals pr
                    WHERE pr.task_id = p_task AND pr.status = 'promoted')
        OR EXISTS (SELECT 1 FROM validation_attempts va
                     JOIN agent_runs ar ON ar.id = va.agent_run_id
                    WHERE ar.task_id = p_task
                      AND va.outcome IN ('answered', 'stale'))
        OR EXISTS (SELECT 1 FROM test_runs tr
                     JOIN agent_runs ar ON ar.id = tr.agent_run_id
                    WHERE ar.task_id = p_task AND tr.lane = 'replay')
$fn$;

COMMENT ON FUNCTION task_result_accepted(uuid) IS
    'Whether the runtime has accepted a structured result of this Task: a '
    'promoted proposal, an answered validation, or a Test run off the replay '
    'lane. The one place 012''s completion question is asked.';

-- ===========================================================================
-- 5. The frontier and the derivation
-- ===========================================================================
--
-- A ceiling of its own, and not the hunts' one. The two numbers cap opposite
-- ends of the same loop -- how much new work a pass may open, and how much
-- authored work it may spend -- and an operator throttling one has no reason
-- to be throttling the other.

ALTER TABLE scheduler_weights
    ADD COLUMN max_performances_derived_per_pass smallint NOT NULL DEFAULT 3
        CHECK (max_performances_derived_per_pass >= 0);

COMMENT ON COLUMN scheduler_weights.max_performances_derived_per_pass IS
  'How many `perform` Tasks one ranking pass may open. 0 stops the derivation without stopping the pass, which is how an operator holds authored Tests on file while they read them.';

CREATE FUNCTION rk2_test_performance_frontier(p_program_id uuid)
RETURNS TABLE (test_id uuid, hypothesis_id uuid, subject_entity_id uuid,
               created_at timestamptz)
LANGUAGE sql STABLE AS $fn$
    SELECT ts.id, ts.hypothesis_id, h.subject_entity_id, ts.created_at
      FROM tests ts
      JOIN hypotheses h ON h.id = ts.hypothesis_id AND h.program_id = ts.program_id
      JOIN entities e ON e.id = h.subject_entity_id AND e.program_id = h.program_id
     WHERE ts.program_id = p_program_id
       AND ts.impact_class IS NULL
       AND h.status = 'testable'
       AND h.superseded_by IS NULL
       AND e.in_scope
       AND NOT EXISTS (SELECT 1 FROM tests later
                        WHERE later.supersedes_test_id = ts.id)
       AND NOT EXISTS (SELECT 1 FROM test_replays tp WHERE tp.test_id = ts.id)
       AND NOT EXISTS (SELECT 1 FROM tasks k
                        WHERE k.program_id = ts.program_id
                          AND k.kind = 'perform'
                          AND k.test_id = ts.id);
$fn$;

COMMENT ON FUNCTION rk2_test_performance_frontier(uuid) IS
  'The Tests of a Program that state no impact, settle a live testable claim about an in-scope Entity, have never been replayed, are not superseded, and that no `perform` Task names in any status. Any status rather than a live one, for the reason the hunt frontier gives: a Task that ran and finished is an answer, and deriving it again is a loop.';

REVOKE ALL ON FUNCTION rk2_test_performance_frontier(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rk2_test_performance_frontier(uuid) TO rk2_runtime;

CREATE FUNCTION derive_test_performances() RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p        uuid := rk2_program_required();
    ceiling  smallint;
    n_wanted bigint := 0;
    n_tasks  bigint := 0;
BEGIN
    SELECT w.max_performances_derived_per_pass INTO ceiling
      FROM scheduler_weights w WHERE w.active;
    IF NOT FOUND THEN RAISE EXCEPTION 'no active scheduler_weights row'; END IF;

    SELECT count(*) INTO n_wanted FROM rk2_test_performance_frontier(p);

    -- Oldest Test first, for the reason the hunt derivation orders by the
    -- claim's age: these Tasks do not exist yet, so there is no ranking to
    -- prefer one by, and arrival order is the one deterministic answer -- which
    -- is what makes the ceiling reproducible.
    WITH wanted AS (
        SELECT fr.test_id, fr.hypothesis_id, fr.subject_entity_id
          FROM rk2_test_performance_frontier(p) fr
         ORDER BY fr.created_at, fr.test_id
         LIMIT ceiling
    ), made AS (
        INSERT INTO tasks (program_id, kind, test_id, hypothesis_id,
                           subject_entity_id)
        -- The subject rides along, and it is the claim's own. Every other kind
        -- names one, `ready_for` checks it is in scope before it looks at the
        -- kind at all, and a Task with none would be the only row in this table
        -- whose report could not say what it was about.
        SELECT p, 'perform', w.test_id, w.hypothesis_id, w.subject_entity_id
          FROM wanted w
        RETURNING 1 AS one
    )
    SELECT count(*) INTO n_tasks FROM made;

    RETURN jsonb_build_object('candidates', n_wanted,
                              'derived', n_tasks,
                              'deferred', greatest(n_wanted - n_tasks, 0),
                              'ceiling', ceiling);
END $fn$;

COMMENT ON FUNCTION derive_test_performances() IS
  'Opens up to max_performances_derived_per_pass `perform` Tasks against Tests nothing has performed. The exit from the loop between recon and a Finding, as derive_hypothesis_hunts is the entrance.';

REVOKE ALL ON FUNCTION derive_test_performances() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION derive_test_performances() TO rk2_runtime;

-- ===========================================================================
-- 6. The pass calls it
-- ===========================================================================

CREATE OR REPLACE FUNCTION rank_pass(p_trigger text DEFAULT 'timer') RETURNS jsonb
LANGUAGE plpgsql AS $rank$

DECLARE
    p            uuid := rk2_program_required();
    w            scheduler_weights%ROWTYPE;
    n_cancelled  bigint := 0;
    n_ranked     bigint := 0;
    n_fired      bigint := 0;
    v_retests    jsonb;
    edges        jsonb;
    unlocks      jsonb;
    hunts        jsonb;
    performances jsonb;
    by_reason    jsonb;
    top          jsonb;
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
        'dependency_edges', edges,
        'chain_unlocks', unlocks,
        'hypothesis_hunts', hunts,
        'test_performances', performances,
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
                              'edges_derived', edges -> 'derived',
                              'edges_withdrawn', edges -> 'withdrawn',
                              'unlock_candidates', unlocks -> 'candidates',
                              'unlocks_derived', unlocks -> 'derived',
                              'unlocks_withdrawn', unlocks -> 'withdrawn',
                              'claims_graded', hunts -> 'graded',
                              'hunts_derived', hunts -> 'derived',
                              'hunts_deferred', hunts -> 'deferred',
                              'performances_derived', performances -> 'derived',
                              'performances_deferred', performances -> 'deferred');
END 
 $rank$;

-- ===========================================================================
-- 7. The two verbs the runtime gained
-- ===========================================================================
--
-- 029's rule: a function the runtime may execute is a verb somebody declared,
-- and one it may execute without a row is a surface that grew by accident.

INSERT INTO runtime_verb_surface (verb, added_by, note) VALUES
  ('rk2_test_performance_frontier(uuid)', '152',
   'the Tests nothing has performed and no perform Task names, which is what the derivation opens Tasks against'),
  ('derive_test_performances()', '152',
   'opens the Tasks that perform them; called by rank_pass and by nothing else');
