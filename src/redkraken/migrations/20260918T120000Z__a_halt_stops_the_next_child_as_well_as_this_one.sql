-- Ticket 64: a Halt stops new work, which is what the console has always said
-- it does.
--
-- Stories 14 and 125 ask for a Halt that is re-evaluated at the egress door on
-- every exchange, and that is what 20260811T130000Z built: a halted Program
-- resolves no capability, so a child already running stops at its next request.
-- Three operator-facing strings promise more than that -- `rk halt`'s help,
-- `operator.halt`'s docstring and the UI action all say "no egress and no new
-- work until it is lifted" -- and nothing anywhere consulted the Halt before a
-- claim. A halted Program went on ranking, offering, claiming and starting
-- children; each one was refused at the door on its first request, each one
-- spent an attempt, and after three the Task was abandoned as
-- `attempts_exhausted`. Halting a Program for an hour cost it the queue, and
-- the only place the stop was stated to the model was the capsule's status
-- line, which is prompt text doing a scheduler's job.
--
-- One arm, and second. After `not_pending`, because a Task that is claimed or
-- done is not a Task a Halt refuses -- it is a Task with nothing left to refuse
-- -- and before everything else, because a Halt is a fact about the Program and
-- outranks every reason to do with the Task itself. `claim_task` re-asks
-- `claimable_for` under the row lock, so a Halt landing between the offer and
-- the claim refuses the claim; `offer_slate` filters on the same function, so a
-- Halt landing before the offer empties the slate; and `rank_candidates` ranks
-- what the same function admits, so nothing is ranked for a stopped Program
-- either.
--
-- What this does not touch is the door. `resolve_egress_capability` still
-- re-asks the Halt on every exchange, which is what stops the children that
-- were already running when the Halt landed. This stops the next ones from
-- being started, and the two together are the sentence the console shows.
--
-- Clearing is nothing but the absence of the row's `halted` status, which is
-- how `clear_program_halt` already writes it: a lifted Halt makes the arm fall
-- through on the next call, with nothing to re-rank and no Task changed.

-- ---------------------------------------------------------------------------
-- 1. The arm
-- ---------------------------------------------------------------------------
-- Restated whole rather than amended, because a plpgsql body cannot be patched
-- in place. Every other arm is 20260916T000000Z's, in 20260916T000000Z's order.

CREATE OR REPLACE FUNCTION claimable_for(t tasks, w scheduler_weights) RETURNS text
LANGUAGE plpgsql STABLE AS $fn$
DECLARE v text;
BEGIN
    IF t.status IS DISTINCT FROM 'pending' THEN RETURN 'not_pending'; END IF;

    IF EXISTS (SELECT 1 FROM program_halts h
                WHERE h.program_id = t.program_id AND h.status = 'halted') THEN
        RETURN 'halted';
    END IF;

    v := cancel_reason_for(t, w);
    IF v IS NOT NULL THEN RETURN v; END IF;

    v := ready_for(t);
    IF v IS NOT NULL THEN RETURN v; END IF;

    IF t.estimated_cost IS NULL THEN RETURN 'not_ranked'; END IF;

    IF NOT EXISTS (SELECT 1 FROM program_budget b
                    WHERE b.program_id = t.program_id
                      AND (b.tokens_left IS NULL
                           OR b.tokens_left >= t.estimated_cost * w.cost_reference_tokens)) THEN
        RETURN 'unaffordable';
    END IF;

    v := budget_refusal_for(t);
    IF v IS NOT NULL THEN RETURN v; END IF;

    IF identity_clamped_for(t)
       AND NOT EXISTS (SELECT 1 FROM task_identities ti
                        WHERE ti.task_id = t.id) THEN
        RETURN 'clamped_without_identity';
    END IF;

    IF identity_held_for(t) THEN RETURN 'identity_held'; END IF;

    IF NOT EXISTS (SELECT 1 FROM effective_lane_capacity lc
                    WHERE lc.program_id = t.program_id AND lc.kind = t.kind) THEN
        RETURN 'no_role_runs_this_kind';
    END IF;

    IF skills_ungranted_for(t) THEN RETURN 'skill_not_granted_to_role'; END IF;

    IF NOT EXISTS (SELECT 1 FROM scheduler_lane_state s
                    WHERE s.program_id = t.program_id AND s.kind = t.kind
                      AND s.headroom > 0) THEN
        RETURN 'lane_full';
    END IF;

    IF subject_held_for(t) THEN RETURN 'subject_held'; END IF;

    IF subagent_started_for(t)
       AND (SELECT count(*) FROM tasks c
              JOIN effective_lane_capacity lc
                ON lc.program_id = c.program_id AND lc.kind = c.kind
              JOIN roles r ON r.role = lc.role
             WHERE c.program_id = t.program_id
               AND c.status IN ('claimed','running')
               AND r.runs_as = 'subagent') >= w.max_concurrent_subagents THEN
        RETURN 'global_subagent_cap';
    END IF;

    RETURN NULL;
END $fn$;

COMMENT ON FUNCTION claimable_for(tasks, scheduler_weights) IS
    'NULL when this Task may be claimed, else the name of the condition that '
    'refuses it. The offer filters on it and the claim re-asks it, so the list '
    'the orchestrator was given and the decision the runtime commits cannot be '
    'made under different rules. An operator Halt is the second arm and the '
    'only one that is not about the Task: no work starts for a stopped Program, '
    'which is the half of a Halt the egress door cannot enforce.';


-- ---------------------------------------------------------------------------
-- 2. The invariants this file must not have broken
-- ---------------------------------------------------------------------------

DO $$
DECLARE n integer; d text;
BEGIN
    -- The restatement is the whole of `claimable_for`, so the arms it inherited
    -- are the ones that can have gone missing in the copying. Asked of the
    -- source, because what is checked is that the text still says them and not
    -- that some row happens to reach them.
    SELECT count(*) INTO n
      FROM unnest(ARRAY['not_pending', 'halted', 'not_ranked', 'unaffordable',
                        'clamped_without_identity', 'identity_held',
                        'no_role_runs_this_kind', 'skill_not_granted_to_role',
                        'lane_full', 'subject_held', 'global_subagent_cap']) AS arm
     WHERE (SELECT prosrc FROM pg_proc
             WHERE proname = 'claimable_for'
               AND pronamespace = 'public'::regnamespace) LIKE '%' || arm || '%';
    IF n <> 11 THEN
        RAISE EXCEPTION 'claimable_for lost an arm in the restatement: % of 11 present', n;
    END IF;

    -- 073's guard, restated as this file's concern rather than trusted: the
    -- subagent cap is still asked only of a claim that starts a subagent.
    SELECT count(*) INTO n FROM check_subagent_cap_guard();
    IF n <> 0 THEN
        SELECT string_agg(problem || ' ' || subject, ', ') INTO d
          FROM check_subagent_cap_guard();
        RAISE EXCEPTION 'the subagent cap guard no longer holds: %', d;
    END IF;

    -- And the door's own half, which this file must leave exactly as it found
    -- it: only an operator changes Halt state, and a current Halt admits no
    -- later allowed Receipt.
    SELECT count(*) INTO n FROM check_program_halt();
    IF n <> 0 THEN
        SELECT string_agg(problem || ' ' || detail, ', ') INTO d FROM check_program_halt();
        RAISE EXCEPTION 'the Halt at the door no longer holds: %', d;
    END IF;
END $$;
