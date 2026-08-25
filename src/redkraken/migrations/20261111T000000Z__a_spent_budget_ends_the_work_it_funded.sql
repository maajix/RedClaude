-- ---------------------------------------------------------------------------
-- 20261111T000000Z__a_spent_budget_ends_the_work_it_funded.sql
--                                                        (ticket 181)
--
-- A Program that has spent its stated token budget stops. It does not raise.
--
-- What was measured. Database `rk2grade7`, 2026-08-25, `browser-script`
-- against `markup-pair`. Repeat 1 of the secure variant was worked nine passes
-- and stopped on `refused`: `claim_task` raised 23514, `task T7 is no longer
-- claimable: program_tokens_reserved`. `evaluation._repeat` reads a violation
-- as a repeat that did not complete, files nothing for it and returns None, so
-- repeat 1 was discarded, repeat 2 never ran, and the verdict for the whole
-- Playbook came back `untested`. The invocation exited 3.
--
-- The arithmetic behind it, from `program_capacity` in that database. That
-- Program had `token_budget` 400000, `run_tokens` 40000 and `tokens_spent`
-- 366321, leaving `tokens_free` 33679 across seventeen Agent runs. Its sibling
-- `markup-pair-vulnerable-1` ended on 371054 spent and 28946 free without
-- tripping, and every `object-ownership` Program in the same canary ended with
-- at least 79208 free. So this is not a fault peculiar to one run: it is what
-- happens to any Program whose work spends the budget down to within one run's
-- worst case while a pick is outstanding, and `browser-script` is simply the
-- graded Playbook that spends the most.
--
-- Why the claim and the slate disagree. They do not, at the moment each is
-- taken. `rank_candidates` selects with `claimable_for(t, w) IS NULL`, so the
-- entry was affordable when the slate was written. Between the slate and the
-- claim the orchestrator runs its chooser, and that is an Agent run that
-- spends tokens like any other; the log records `AR17 answered chosen (T7)
-- after 1 pick(s)` immediately before the refusal. The margin the slate saw is
-- spent by the act of choosing from it.
--
-- What this changes. The pick branch of `claim_task` re-validates the chosen
-- Task and raises when `claimable_for` refuses it. That raise is right for what
-- it was written for -- the comment beside it calls it "the world moved under a
-- choice", a Task another claimant took -- and wrong for a spent budget. The
-- ELSE branch, which walks the slate when there is no pick, already states the
-- rule for that case: "Nothing claimable, including nothing offered. NULL
-- rather than a refusal: an empty slate is the queue being idle... A raise here
-- would make 'nothing to do' indistinguishable from 'the world moved under a
-- choice'." A reservation that cannot be made is the queue being idle. So the
-- four reservation reasons return NULL from the pick branch too, and the two
-- branches answer the same question the same way.
--
-- Four and not five. `unaffordable`, the other capacity answer, compares what
-- is left against *this* Task's `estimated_cost`; it says one Task is too
-- expensive, not that the Program has no room, and a cheaper Task on the same
-- slate may still be claimable. It is also what `SlateClaimTest`'s criterion 3
-- holds -- `test_a_task_the_budget_no_longer_covers_is_refused_after_being_offered`
-- reads that raise back by name -- and nothing measured here argues against it.
-- The four this file does change are reached by asking whether one more run's
-- worst case can be set aside at all, which has the same answer for every Task
-- the Program has.
--
-- And only when the caller named no Task. `claim_task(p_task_label)` is an
-- operator or a test asking for one Task in particular, and answering NULL
-- there would answer a question that was not asked;
-- `BudgetReservationTest.arrange_capped` names its Task for exactly that
-- reason. The runtime is the caller this ticket is about and it never names
-- one: `execution.CLAIM` is `SELECT claim_task()`.
--
-- Nothing is hidden by it. `scheduler_idle_report()` is what the runtime reads
-- an idle queue through, and it says which predicate refused each Task, so the
-- reason survives the NULL exactly as it does for the slate walk. `execution`
-- turns a NULL claim into `N Task(s) offered and none of them was claimable`
-- and the pass stops on `nothing_to_execute`, which is the stop reason
-- `evaluation._repeat` already treats as a Program that finished -- so the work
-- the budget did fund is filed instead of being thrown away with the raise.
--
-- `budget_unreadable` keeps the raise. `budget_refusal_for` returns it when no
-- `program_capacity` row can be read at all, which its own comment calls
-- defence rather than a path: that is a Program whose budget is broken, not one
-- whose budget is spent, and a Program that cannot be priced must not quietly
-- report an idle queue.
--
-- The function is otherwise the text 20260908T010000Z shipped, replaced whole
-- because that is how a plpgsql body is amended.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION claim_task(p_task_label text DEFAULT NULL)
RETURNS text LANGUAGE plpgsql AS $fn$
DECLARE
    p         uuid := rk2_program_required();
    w         scheduler_weights%ROWTYPE;
    v_task    tasks%ROWTYPE;
    v_entry   record;
    v_id      uuid;
    v_offered timestamptz;
    v_role    text;
    v_clamp   boolean;
    v_model   text;
    v_effort  text;
    v_run     uuid;
    v_reason  text;
    v_leases  integer;
BEGIN
    SELECT * INTO w FROM scheduler_weights WHERE active;

    -- Everything after this point is inside the counting window.
    PERFORM pg_advisory_xact_lock(hashtextextended(p::text, 0));

    -- The offer expired. Refused rather than silently re-offered: the caller
    -- asked to commit a choice it made against a list, and the honest answer is
    -- that the list is gone. The loop answers this by offering again.
    SELECT min(s.offered_at) INTO v_offered
      FROM task_slate s WHERE s.program_id = p AND NOT s.consumed;
    IF v_offered IS NOT NULL AND v_offered + w.slate_ttl < now() THEN
        RAISE EXCEPTION 'the slate offered at % expired after %', v_offered, w.slate_ttl
            USING ERRCODE = 'check_violation';
    END IF;

    v_id := NULL;
    IF p_task_label IS NOT NULL THEN
        SELECT s.task_id INTO v_id
          FROM task_slate s JOIN tasks t ON t.id = s.task_id
         WHERE s.program_id = p AND NOT s.consumed AND t.label = p_task_label;
        IF NOT FOUND THEN
            -- Off-slate, cross-Program and already-consumed all arrive here,
            -- and all three are the same refusal: the Program is a predicate on
            -- `task_slate` and `rk2_program_required()` is where it comes from,
            -- so another Program's label is a label this Program was never
            -- offered.
            RAISE EXCEPTION 'task % is not on the current slate', p_task_label
                USING ERRCODE = 'check_violation';
        END IF;
    ELSE
        SELECT k.task_id INTO v_id
          FROM task_picks k WHERE k.program_id = p AND NOT k.consumed;
        IF FOUND AND NOT EXISTS (
             SELECT 1 FROM task_slate s
              WHERE s.program_id = p AND NOT s.consumed AND s.task_id = v_id) THEN
            -- The pick outlived its entry. `offer_slate` consumes both together
            -- so a new offer cannot leave one behind; what reaches here is a
            -- choice whose Task was claimed by something else off the same
            -- slate, which is the stale choice criterion 4 names.
            RAISE EXCEPTION 'the choice recorded for this program is no longer on the slate'
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;

    IF v_id IS NOT NULL THEN
        -- The slate is a suggestion that was true when it was computed. This is
        -- the check that makes it true when it is acted on, under the row lock
        -- so that two claimants of one Task serialise here.
        SELECT t.* INTO v_task FROM tasks t WHERE t.id = v_id FOR UPDATE;
        v_reason := claimable_for(v_task, w);
        -- Ticket 181. A reservation that cannot be made is the queue being
        -- idle, not the world moving under a choice, and the ELSE branch below
        -- already states which of those NULL is for. `rank_candidates` filters
        -- the slate with `claimable_for(t, w) IS NULL`, so this entry was
        -- affordable when it was offered; what spends the margin between the
        -- offer and the claim is the orchestrator's own choosing run, which is
        -- an Agent run like any other.
        --
        -- These four and no others, because these four are the only answers
        -- that are not about this Task. `budget_refusal_for` reaches them by
        -- asking whether one more run's worst case -- `run_tokens`,
        -- `run_requests` -- can be set aside at all, which is a question with
        -- the same answer for every Task the Program has. There is therefore
        -- nothing to walk to and nothing a retry would mend, which is exactly
        -- the state the slate walk below reports by returning NULL.
        --
        -- `unaffordable` is deliberately not among them. It compares what is
        -- left against *this* Task's `estimated_cost`, so it is a statement
        -- about one Task being too expensive rather than about the Program
        -- having no room, and a cheaper Task may still be claimable. It is also
        -- the arm `SlateClaimTest`'s criterion 3 --
        -- `test_a_task_the_budget_no_longer_covers_is_refused_after_being_offered`
        -- -- exists to hold, and this ticket has no measurement that argues
        -- against it. `budget_unreadable` keeps the raise for its own reason: a
        -- capacity that cannot be read is a broken Program rather than a spent
        -- one, and must not quietly report an idle queue.
        --
        -- Only when nothing was named. `p_task_label` is a caller asking for
        -- one Task in particular, and NULL would answer a question it did not
        -- ask: `BudgetReservationTest.arrange_capped` names its Task precisely
        -- "so the refusal is about this Task and not about a slate that ran out
        -- of entries", and that reading has to keep working. The runtime never
        -- names one -- `execution.CLAIM` is `SELECT claim_task()` -- so the
        -- path this ticket measured is the argument-free one, which is also the
        -- only path the ELSE branch's NULL was ever reachable from.
        IF p_task_label IS NULL
           AND v_reason IN ('program_tokens_reserved', 'program_requests_reserved',
                            'lane_tokens_reserved', 'lane_requests_reserved') THEN
            RETURN NULL;
        END IF;
        IF v_reason IS NOT NULL THEN
            -- No `UPDATE task_slate SET consumed` before this, deliberately.
            -- The RAISE aborts the transaction and would take the update with
            -- it, in this function and in any caller's subtransaction alike.
            -- Nothing needs it: `offer_slate()` consumes every outstanding row
            -- of the Program before it writes a new slate.
            RAISE EXCEPTION 'task % is no longer claimable: %', v_task.label, v_reason
                USING ERRCODE = 'check_violation';
        END IF;
    ELSE
        FOR v_entry IN
            SELECT s.task_id FROM task_slate s
             WHERE s.program_id = p AND NOT s.consumed
             ORDER BY s.ordinal
        LOOP
            SELECT t.* INTO v_task FROM tasks t WHERE t.id = v_entry.task_id FOR UPDATE;
            IF claimable_for(v_task, w) IS NULL THEN
                v_id := v_entry.task_id;
                EXIT;
            END IF;
        END LOOP;
        -- Nothing claimable, including nothing offered. NULL rather than a
        -- refusal: an empty slate is the queue being idle, and the runtime
        -- reports idleness through `scheduler_idle_report()`, which can say
        -- which predicate refused every Task. A raise here would make "nothing
        -- to do" indistinguishable from "the world moved under a choice".
        IF v_id IS NULL THEN RETURN NULL; END IF;
    END IF;

    SELECT m.role, r.clamp_to_identity_leases, r.model, r.effort
      INTO v_role, v_clamp, v_model, v_effort
      FROM role_task_kinds m JOIN roles r ON r.role = m.role
     WHERE m.kind = v_task.kind;

    UPDATE tasks
       SET status = 'claimed', attempts = attempts + 1, claimed_at = now(),
           lease_expires_at = now() + w.lease_ttl
     WHERE id = v_task.id;

    INSERT INTO agent_runs (program_id, task_id, role, model, effort, mission_packet)
    VALUES (p, v_task.id, v_role, v_model, v_effort, '{}')
    RETURNING id INTO v_run;

    -- The promise. Written after the run exists because it names it, and read
    -- by the next claim through `program_capacity` -- which is why it has to be
    -- written before this transaction ends rather than by whoever starts the
    -- child. The amounts are the same expressions `budget_refusal_for` just
    -- admitted the Task against, from the same view in the same transaction.
    INSERT INTO budget_reservations (program_id, agent_run_id, task_id, kind,
                                     tokens, requests)
    SELECT p, v_run, v_task.id, v_task.kind, c.run_tokens, c.run_requests
      FROM program_capacity c WHERE c.program_id = p;

    -- Decision 7: the identity lease shares the task lease's clock. Two clocks
    -- would admit a live task lease beside a dead identity lease, and the agent
    -- would read the proxy's refusal to inject as the TARGET changing
    -- behaviour -- the false positive the identity model exists to prevent.
    --
    -- Ticket 72: every Identity the Task will act as, and no second condition.
    -- `identity_leases_exclusive_idx` is what makes two claimants of one
    -- Identity serialise if the gate above ever misses one.
    IF v_clamp THEN
        INSERT INTO identity_leases (identity_entity_id, holder_agent_run_id,
                                     expires_at, program_id)
        SELECT ti.identity_entity_id, v_run, now() + w.lease_ttl, p
          FROM task_identities ti WHERE ti.task_id = v_task.id;

        GET DIAGNOSTICS v_leases = ROW_COUNT;
        IF v_leases = 0 THEN
            RAISE EXCEPTION 'task % is clamped and names no identity to hold', v_task.label
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;

    UPDATE task_slate SET consumed = true
     WHERE program_id = p AND task_id = v_task.id AND NOT consumed;

    -- The choice has been acted on, whichever entry the claim took. A pick left
    -- outstanding here would be read by the next claim as a choice about a Task
    -- that is already running.
    PERFORM supersede_pick(p);

    RETURN (SELECT label FROM agent_runs WHERE id = v_run);
END $fn$;
