-- ---------------------------------------------------------------------------
-- a_task_the_scheduler_will_never_call_ready_ends.sql   (ticket 158)
--
-- 143's second criterion said "and it does not stay pending either", and 143
-- did not pay it. What shipped was the runtime half: a Task the dispatch slice
-- cannot serve is retired by `retire_task` instead of refusing the pass. The
-- scheduler half -- a Task the READINESS predicate will never clear -- was left
-- open, and `rk2hunt16` measured it exactly:
--
--     T3  hunt  pending  ready_for -> hunt.no_address  cancel_reason_for -> none
--
-- Zero attempts, five laps, never offered, never ended. 157 un-stuck that
-- particular Task by giving a Domain an address. This file stops the next one,
-- whatever its predicate turns out to be.
--
-- The rule is not "unready for a while". Most predicates are about a queue or
-- about a row that has not arrived yet -- `hunt.hypothesis_not_testable`
-- clears when the pass grades the claim, `report.no_validated_finding` clears
-- when a Finding is validated -- and ending those would end work that was
-- merely early. The rule is about the predicates that are facts about the
-- Task's own row: it names no subject, no claim, no Test, no Finding. Nothing
-- a later pass does changes any of those, because a Task's own columns are
-- written once and this schema has no verb that rewrites them.
--
-- `no_address` is deliberately NOT in that list, and 157 is why. A subject has
-- an address when this Program holds an Application on its name, and recon
-- promotes Applications -- so a Domain that carries none today can carry one
-- next pass, and the predicate is a fact about `applications` rather than about
-- the Task. `ChainUnlockTest` holds the case: two hunt Tasks on `technology`
-- subjects read `hunt.no_address` for five passes and are still the Tasks the
-- chain arithmetic is about. A permanently addressless subject is a real
-- problem and it is 159's -- nothing proposes the Host or the Application --
-- not something to be paid for by ending work that may become runnable.
--
-- Counted rather than timed, and counted on the row rather than in a new table:
-- the pass already touches every pending Task in step (2), so the counter costs
-- one more UPDATE over rows already being read. A timer would have made the
-- rule depend on how often an operator ran the pass.
--
-- Ended through `retire_task` rather than through `cancel_reason_for`. That
-- deviates from the plan and the reason is the schema's: `abandoned_reason` is
-- a closed vocabulary of eleven words, `cancel_reason_for` returns one of them,
-- and `recon.no_address` is not a word in it. 143 already minted the word for
-- exactly this state -- `undispatchable`, "the Task is well-formed and this
-- runtime cannot serve it" -- and `retire_task` already writes the sentence
-- that says which one into a `task.retired` event. Growing the vocabulary by
-- one word per predicate would have been the same fact said twice, and losing
-- the predicate would have been the fact said badly.
-- ---------------------------------------------------------------------------

-- ===========================================================================
-- 1. The counter
-- ===========================================================================

ALTER TABLE tasks
    ADD COLUMN unready_passes integer NOT NULL DEFAULT 0
        CHECK (unready_passes >= 0);

COMMENT ON COLUMN tasks.unready_passes IS
  'How many consecutive ranking passes have found this Task unready. Reset to 0 by the pass that finds it ready, so it counts a standing condition rather than a total. Written only by rank_pass, and read only by the retirement in the same step.';


-- ===========================================================================
-- 2. Which predicates are facts about the Task rather than about the queue
-- ===========================================================================
--
-- Written as a function rather than inline, because `rank_pass` is not the only
-- place that will want to ask it and because the list is the whole of the rule:
-- an operator reading "why did this Task end" is reading this list.
--
-- The four are the `ready_for` arms that read a column of `tasks` and find it
-- NULL. Every other arm reads a row somewhere else -- a claim's status, an
-- Artifact's visibility, a Finding's status, whether an Application stands on
-- the subject's name -- and every one of those can change with no change to
-- the Task at all.
--
-- Split on the dot rather than matched with LIKE: the predicate is
-- `<kind>.<reason>` by construction, and `LIKE '%no_address'` would also match
-- a kind that happened to end in those letters.

CREATE FUNCTION rk2_terminal_predicate(p_predicate text) RETURNS boolean
LANGUAGE sql IMMUTABLE AS $fn$
    SELECT p_predicate IS NOT NULL
       AND split_part(p_predicate, '.', 2) IN
           ('no_subject', 'no_hypothesis', 'no_test', 'no_finding')
$fn$;

COMMENT ON FUNCTION rk2_terminal_predicate(text) IS
    'Whether a ready_for answer is a fact about the Task''s own row rather than '
    'about the rows around it. A Task naming no subject, no claim, no Test or no '
    'Finding is unready for a reason no later pass can clear -- which is what '
    'makes it safe to end. no_address is not one of them: an Application on the '
    'subject''s name is something recon can still promote.';

REVOKE ALL ON FUNCTION rk2_terminal_predicate(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rk2_terminal_predicate(text) TO rk2_runtime;


-- ===========================================================================
-- 3. The pass counts, and then ends what it will never call ready
-- ===========================================================================

CREATE OR REPLACE FUNCTION rank_pass(p_trigger text DEFAULT 'timer') RETURNS jsonb
LANGUAGE plpgsql AS $rank$

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
    conclusions  jsonb;
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
        'finding_claims', conclusions,
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
                              'conclusions_derived', conclusions -> 'derived',
                              'conclusions_deferred', conclusions -> 'deferred');
END
 $rank$;


-- ===========================================================================
-- 4. The verb the runtime gained
-- ===========================================================================

INSERT INTO runtime_verb_surface (verb, added_by, note) VALUES
  ('rk2_terminal_predicate(text)', '158',
   'whether a ready_for answer is a fact about the Task''s own row; read by rank_pass and by nothing else');
