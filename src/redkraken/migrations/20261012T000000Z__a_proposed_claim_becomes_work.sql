-- A proposed claim becomes work.
--
-- Ticket 140. Two statements in the corpus create a Task of kind `hunt`:
-- `rk2_chain_unlock_frontier` (20260819), which needs a sound chain, a standing
-- pivot stamp and a Finding, and the impact path (20260816), which takes a
-- Finding. A Finding is opened from a Hypothesis at `supported`, a Hypothesis
-- reaches `supported` through a Test, and a Test is what a hunt Task runs.
-- Every entrance to the loop was inside it, so a Program that had never found
-- anything could never find anything.
--
-- Six live hunts against a real target on 2026-08-22 ended after the two recon
-- Tasks a Program opens for itself, every time. Nothing past the recon Task has
-- ever run in this tree: zero Tests, zero Findings, zero kill chains.
--
-- This file cuts the entrance. It is two steps, because the loop is broken in
-- two places one after the other.
--
-- Step one: nothing ever made a claim testable. `hypotheses.status` defaults to
-- `proposed` (0007) and `rk2_promote_hypotheses` never transitions it. Of the
-- nineteen statements in the corpus that write a `hypothesis_transitions` row,
-- not one names `proposed` as its `from_status`. The rule exists and is legal --
-- `transition_rules` carries `proposed -> testable` with
-- `required_actor_kind = 'runtime'`, no receipt and no evidence minimum -- and
-- 0007 wrote it as `llm` before a 20260814 migration narrowed it to `runtime`.
-- That narrowing settles the shape: this is a runtime judgement about a claim
-- the runtime has already promoted, not a verb a model asks for, so it belongs
-- in the ranking pass beside `derive_chain_unlocks` and not on the roster.
--
-- Step two: nothing turns a testable claim into work. `open_task` (20260831)
-- takes a kind and a subject and cannot set `hypothesis_id`, and `ready_for`
-- refuses a hunt Task that has none.
--
-- The 20260831 preamble states: *"Every production `INSERT INTO tasks` in this
-- schema is downstream of a Finding or a Hypothesis, and a Program that has
-- just been opened has neither."* Downstream of a Hypothesis is the case that
-- sentence names and the corpus never built. This file is the second half of it
-- being made true.


-- ===========================================================================
-- 1. The ceiling, and why it is a pass knob rather than a constant
-- ===========================================================================
--
-- A recon run proposing five claims would open five hunt Tasks, each of which
-- may propose more. `[budgets]` bounds requests, tokens and concurrency, and
-- `novelty_for` and the ranking already decide order; what was missing is a
-- ceiling on how many claims one pass may turn into work.
--
-- It bounds the Tasks and not the grading. `testable` is a statement about the
-- claim -- that a Test could settle it -- and not about the schedule. A ceiling
-- on grading would make a claim's status depend on how busy the pass was, and
-- the same claim would read `proposed` on Tuesday and `testable` on Wednesday
-- with nothing about the claim having changed. The queue is where breadth
-- belongs and the queue is Tasks.
--
-- It lives in `scheduler_weights` because that row already holds every number
-- the pass reads and is versioned the way a pass knob has to be: the row is
-- immutable -- *"scheduler weights version 2 may be activated or deactivated,
-- not rewritten"* -- so changing the ceiling inserts a version and activates it,
-- and every Task ranked under the old ceiling still carries the version it was
-- ranked under. A constant in the function body would need a migration to move
-- and would leave no record of what the ceiling was when a Task was derived.

ALTER TABLE scheduler_weights
    ADD COLUMN max_hunts_derived_per_pass smallint NOT NULL DEFAULT 3
        CHECK (max_hunts_derived_per_pass >= 0);

COMMENT ON COLUMN scheduler_weights.max_hunts_derived_per_pass IS
  'How many hunt Tasks one ranking pass may derive from testable claims. Bounds the burst a talkative recon run can create; the claims it does not reach stay testable and are derived by the next pass.';


-- ===========================================================================
-- 2. What makes a proposed claim testable
-- ===========================================================================
--
-- Five conditions, and each is a thing a Test needs rather than a thing that
-- happens to be true of the rows on hand.
--
-- The subject has to still be on the Surface, because a Test against an Entity
-- that left scope is a request the door refuses. The claim must not be
-- superseded, because the near-match stage 2 that superseded it already said
-- which claim carries the question now. The rationale has to answer all three
-- of `rk2_rationale_keys()` non-emptily: a claim with no falsifier is not a
-- claim a Test can settle, it is an opinion, and `hypotheses_rationale_shape`
-- constrains which keys may appear and not that any of them do. There has to be
-- at least one supporting Observation, because `testing -> supported` needs two
-- and one that starts from none has nothing to build on.
--
-- The fifth is `transport_makeability`. That table grades five transport
-- property classes by whether an Agent holding `net.request` can make the
-- condition at all: `transport.header_policy` is `agent_ok`,
-- `transport.certificate_trust` and `transport.tls_configuration` are
-- `probe_only`, and `transport.datagram_transport` and
-- `transport.request_framing` are `unmakeable`. Grading one of the last four
-- testable would dispatch a hunt run that cannot form the request, which is the
-- same defect as the `analyze` Task handed to a role holding no `net.request`
-- that abandoned a live run on 2026-08-22. A class the table says nothing about
-- is makeable; the table is the exception list, not the allow list.

CREATE FUNCTION rk2_gradable_claims(p_program_id uuid)
RETURNS TABLE (hypothesis_id uuid)
LANGUAGE sql STABLE AS $fn$
    SELECT h.id
      FROM hypotheses h
      JOIN entities e ON e.id = h.subject_entity_id AND e.program_id = h.program_id
     WHERE h.program_id = p_program_id
       AND h.status = 'proposed'
       AND h.superseded_by IS NULL
       AND e.in_scope
       AND NOT EXISTS (SELECT 1 FROM transport_makeability tm
                        WHERE tm.property_class = h.property_class
                          AND tm.makeability IN ('probe_only', 'unmakeable'))
       AND NOT EXISTS (SELECT 1 FROM unnest(rk2_rationale_keys()) AS k(key)
                        WHERE coalesce(h.rationale ->> k.key, '') = '')
       AND EXISTS (SELECT 1 FROM hypothesis_evidence ev
                    WHERE ev.hypothesis_id = h.id
                      AND ev.polarity = 'supports');
$fn$;

COMMENT ON FUNCTION rk2_gradable_claims(uuid) IS
  'The proposed claims of a Program that a Test could settle: on the Surface, not superseded, rationale complete, at least one supporting Observation, and not a transport class transport_makeability grades probe_only or unmakeable.';

REVOKE ALL ON FUNCTION rk2_gradable_claims(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rk2_gradable_claims(uuid) TO rk2_runtime;


-- ===========================================================================
-- 3. The frontier -- a testable claim no hunt Task names
-- ===========================================================================
--
-- Guarded on a hunt Task existing in ANY status, not merely a live one, for the
-- reason 20260819 wrote down beside the same guard: *"A Task that ran and
-- finished is an answer; deriving it again next pass because the answer was
-- disappointing is a loop with a database behind it."* If the claim is worth
-- asking again, 034's retest trigger is what says so, and it moves the claim
-- rather than minting a Task.

CREATE FUNCTION rk2_hypothesis_hunt_frontier(p_program_id uuid)
RETURNS TABLE (hypothesis_id uuid, subject_entity_id uuid, created_at timestamptz)
LANGUAGE sql STABLE AS $fn$
    SELECT h.id, h.subject_entity_id, h.created_at
      FROM hypotheses h
      JOIN entities e ON e.id = h.subject_entity_id AND e.program_id = h.program_id
     WHERE h.program_id = p_program_id
       AND h.status = 'testable'
       AND h.superseded_by IS NULL
       AND e.in_scope
       AND NOT EXISTS (SELECT 1 FROM tasks k
                        WHERE k.program_id = h.program_id
                          AND k.kind = 'hunt'
                          AND k.hypothesis_id = h.id);
$fn$;

COMMENT ON FUNCTION rk2_hypothesis_hunt_frontier(uuid) IS
  'The testable claims of a Program that no hunt Task names in any status. Any status rather than a live one: a Task that ran and finished is an answer, and deriving it again is a loop.';

REVOKE ALL ON FUNCTION rk2_hypothesis_hunt_frontier(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rk2_hypothesis_hunt_frontier(uuid) TO rk2_runtime;


-- ===========================================================================
-- 4. The derivation
-- ===========================================================================
--
-- One function and two statements, in the order the rows need them: a claim
-- cannot be on the hunt frontier until it is testable, so the grading runs
-- first and the Task derivation sees this pass's gradings rather than the next
-- pass's.
--
-- `actor_kind` is the literal `runtime` and not the session's actor. The rule
-- requires `runtime`, `assert_actor_kind_authentic` only guards `human`, and
-- the judgement really is the runtime's: a pass reading the whole Program
-- decided this claim can be settled. A session variable in that column would
-- let the caller's identity decide whether the pass was allowed to think.
--
-- Estimates on the Task are left NULL, as 20260819 leaves them, and for the
-- same reason: what a Task is worth on its own is the model's sentence, and a
-- runtime filling it in would be inventing the number the ranking rests on.

CREATE FUNCTION derive_hypothesis_hunts() RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p        uuid := rk2_program_required();
    ceiling  smallint;
    n_graded bigint := 0;
    n_wanted bigint := 0;
    n_tasks  bigint := 0;
BEGIN
    SELECT w.max_hunts_derived_per_pass INTO ceiling
      FROM scheduler_weights w WHERE w.active;
    IF NOT FOUND THEN RAISE EXCEPTION 'no active scheduler_weights row'; END IF;

    -- (1) Grading. Uncapped: see section 1.
    WITH graded AS (
        INSERT INTO hypothesis_transitions
                    (hypothesis_id, program_id, from_status, to_status,
                     actor_kind, rationale)
        SELECT g.hypothesis_id, p, 'proposed', 'testable', 'runtime',
               'the ranking pass graded this claim settleable by a Test'
          FROM rk2_gradable_claims(p) g
        RETURNING 1 AS one
    )
    SELECT count(*) INTO n_graded FROM graded;

    SELECT count(*) INTO n_wanted FROM rk2_hypothesis_hunt_frontier(p);

    -- (2) The Tasks, oldest claim first. Oldest and not highest-ranked: the
    --     ranking scores Tasks and these Tasks do not exist yet, so the only
    --     order available here is the order the claims arrived in. It is
    --     deterministic, which is what the ceiling needs to be reproducible.
    WITH wanted AS (
        SELECT fr.hypothesis_id, fr.subject_entity_id
          FROM rk2_hypothesis_hunt_frontier(p) fr
         ORDER BY fr.created_at, fr.hypothesis_id
         LIMIT ceiling
    ), made AS (
        INSERT INTO tasks (program_id, kind, hypothesis_id, subject_entity_id)
        SELECT p, 'hunt', w.hypothesis_id, w.subject_entity_id FROM wanted w
        RETURNING 1 AS one
    )
    SELECT count(*) INTO n_tasks FROM made;

    RETURN jsonb_build_object('graded', n_graded,
                              'candidates', n_wanted,
                              'derived', n_tasks,
                              'deferred', greatest(n_wanted - n_tasks, 0),
                              'ceiling', ceiling);
END $fn$;

COMMENT ON FUNCTION derive_hypothesis_hunts() IS
  'Grades every gradable proposed claim testable, then opens up to max_hunts_derived_per_pass hunt Tasks against testable claims no hunt Task names. The entrance to the loop between recon and a Finding.';

REVOKE ALL ON FUNCTION derive_hypothesis_hunts() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION derive_hypothesis_hunts() TO rk2_runtime;



-- ===========================================================================
-- 5. The pass calls it
-- ===========================================================================
--
-- Between the chain unlocks and the ranking. `CREATE OR REPLACE` rather than a
-- new name, because `rank_pass` is what every caller in the tree already calls
-- and a second pass function would be two schedulers.

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
                              'hunts_deferred', hunts -> 'deferred');
END 
 $rank$;

REVOKE ALL ON FUNCTION rank_pass(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rank_pass(text) TO rk2_runtime;


-- ===========================================================================
-- 6. What the runtime now holds, declared where 66 reads it
-- ===========================================================================
--
-- Three verbs closed to PUBLIC and executable by `rk2_runtime` is three
-- privileges, and 66's standing check refuses a privilege the runtime holds
-- that no row explains. The check is the point: a GRANT is the only part of a
-- migration that widens what a compromised runtime connection can reach, and a
-- reviewer reading this file should find the widening written down rather than
-- inferred from a GRANT three sections up.

INSERT INTO runtime_verb_surface (verb, added_by, note) VALUES
  ('rk2_gradable_claims(uuid)', '140',
   'the five conditions a proposed claim meets before a Test could settle it; read by the derivation and by anyone asking why a claim did not move'),
  ('rk2_hypothesis_hunt_frontier(uuid)', '140',
   'the testable claims no hunt Task names, which is what the derivation opens Tasks against'),
  ('derive_hypothesis_hunts()', '140',
   'grades the claims and opens the Tasks; called by rank_pass and by nothing else');
