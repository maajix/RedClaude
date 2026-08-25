-- ---------------------------------------------------------------------------
-- 20261110T000000Z__a_replay_is_not_refused_a_budget_it_cannot_spend.sql
--                                                        (ticket 180)
--
-- `rk2_replay_plan` asks `budget_refusal_for` whether the Task may spend, and
-- refuses the replay on any answer. Two of those answers are about tokens, and
-- a replay spends none: it re-sends a Test the model already authored, with no
-- child, no session and no model call anywhere in it.
--
-- The test that refuses is `run_tokens > tokens_free`, where `run_tokens` is
-- the worst case of one more *agent* run. So a Program with 38127 tokens left
-- and a 40000-token per-run ceiling refuses an operation that would have spent
-- nothing. The request arms are the ceiling a replay can actually reach, and
-- they are untouched: `program_requests_reserved`, `lane_requests_reserved` and
-- everything else `budget_refusal_for` answers still refuse as before.
--
-- Measured in `rk2grade6`, 2026-08-24, all five graded pairs. Four of five
-- evaluations ended on
--
--     the registry refused this replay: the budget refuses this replay:
--     program_tokens_reserved
--
-- and lost the repeat that carried it. `program_capacity` in that database
-- shows why: the graded Programs are funded 400000 tokens with a 40000 per-run
-- ceiling, and twelve passes of an Opus child spend between 190000 and 403446
-- of them -- so by the time the Test is performed there is routinely less than
-- one run's worst case left. The Playbook that never performs a Test,
-- `attack-surface`, was the one evaluation that passed.
--
-- The budget stays small. `evaluation.BUDGETS` is small on purpose and this
-- does not raise it: a synthetic target on loopback that needs thousands of
-- requests is a run that has stopped measuring the Playbook, and that argument
-- is about requests, which still bind. What changes is that the resource a
-- replay does not consume no longer decides whether it may run.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION rk2_replay_plan(p_program uuid, p_run agent_runs, p_test tests,
                                p_identity_slot text)
RETURNS text[]
LANGUAGE plpgsql AS $fn$
DECLARE
    v_refusal text;
    v_action  jsonb;
    v_route   record;
    v_class   text;
    v_methods text[] := '{}';
BEGIN
    -- The Identity is named once for the whole run and resolved by the door.
    -- Checked now so a run holding a slot it does not lease is refused before
    -- anything is sent, and checked again on every request by
    -- `resolve_egress_identity`, which is the one that counts.
    IF p_identity_slot IS NOT NULL THEN
        IF NOT EXISTS (
            SELECT 1 FROM identities i
              JOIN identity_leases l
                ON l.identity_entity_id = i.entity_id
               AND l.program_id = i.program_id
               AND l.holder_agent_run_id = p_run.id
               AND l.released_at IS NULL
               AND l.expires_at > clock_timestamp()
             WHERE i.program_id = p_program
               AND i.slot_name = p_identity_slot
               AND i.invalidated_at IS NULL) THEN
            RAISE EXCEPTION 'Identity lease refused' USING ERRCODE = '23514';
        END IF;
    END IF;

    -- A budget is a property of a Task, so a run carrying none has none to
    -- consult. That is not a way past the criterion: 025 puts the ceiling on
    -- the Task, and a run without one holds no Task lease either, which is what
    -- `enforce_allowed_receipt_capability` requires before the door may write
    -- an allowed Receipt at all. Such a run is refused a Receipt rather than a
    -- budget, one request later.
    IF p_run.task_id IS NOT NULL THEN
        SELECT budget_refusal_for(t.*) INTO v_refusal
          FROM tasks t WHERE t.id = p_run.task_id;
        -- Ticket 180. The token arms do not apply to a replay. `budget_refusal_for`
        -- is written for a claim that is about to start a model, and its token
        -- test is `run_tokens > tokens_free`: it refuses as soon as fewer than one
        -- agent run's worst case remains. A replay starts no model and spends no
        -- tokens at all, so that is a zero-token operation being refused because
        -- it cannot afford a 40000-token one. The request arms below are the
        -- ceiling a replay can actually reach, and they still bind.
        IF v_refusal IN ('program_tokens_reserved', 'lane_tokens_reserved') THEN
            v_refusal := NULL;
        END IF;
        IF v_refusal IS NOT NULL THEN
            RAISE EXCEPTION 'the budget refuses this replay: %', v_refusal
                USING ERRCODE = '23514';
        END IF;
    END IF;

    -- Every request the plan will make, scope-classed before one is sent. The
    -- setup and the cleanup are held to the same rule as the actions: a
    -- cleanup step pointing outside the scope is a request the door would
    -- refuse, at the moment the run is least able to do anything about it.
    FOR v_action IN
        SELECT * FROM jsonb_array_elements(
            (p_test.spec -> 'actions') || (p_test.spec -> 'setup')
                                       || (p_test.spec -> 'cleanup'))
    LOOP
        SELECT * INTO v_route FROM rk2_test_route(v_action ->> 'url');
        SELECT s.scope_class INTO v_class
          FROM programs pr
          CROSS JOIN LATERAL scope_class_of(
                pr.id, pr.scope_version, v_route.host, v_route.port,
                v_route.path, v_route.path, v_route.scheme, 'request') s
         WHERE pr.id = p_program;
        IF coalesce(v_class, 'denied') NOT IN ('target', 'egress_support') THEN
            RAISE EXCEPTION 'the Test reaches outside the current scope: %',
                v_action ->> 'url'
                USING ERRCODE = '42501',
                      HINT = 'the door would refuse it; the run is refused instead';
        END IF;
        IF NOT (upper(v_action ->> 'method') = ANY (v_methods)) THEN
            v_methods := array_append(v_methods, upper(v_action ->> 'method'));
        END IF;
    END LOOP;

    RETURN v_methods;
END $fn$;
