-- ---------------------------------------------------------------------------
-- 20261113T000000Z__the_last_budget_reason_ends_the_claim_too.sql
--                                                        (ticket 184)
--
-- The fifth answer a spent budget gives ends the claim like the other four.
--
-- What was measured. Database `rk2grade9`, 2026-08-25, `object-ownership`
-- against `object-ownership-pair`. Repeats 0 and 1 filed both variants
-- cleanly -- the furthest any canary has reached. Repeat 2 of the secure
-- variant was worked eight passes and stopped on `refused`:
--
--     the claim against a 1-Task slate failed: 23514: task T7 is no longer
--     claimable: unaffordable | PL/pgSQL function claim_task(text) line 113
--
-- `evaluation._repeat` reads a violation as a repeat that did not complete,
-- files nothing for it and returns None, so the third repeat was discarded and
-- the invocation exited 3 with a verdict of `pass` it could not stand behind.
--
-- This is ticket 181's fault reached by its fifth door. Everything 181 wrote
-- about the mechanism holds unchanged: `rank_candidates` selects with
-- `claimable_for(t, w) IS NULL` so the entry was affordable when the slate was
-- written, and the orchestrator's chooser run spends the margin between the
-- slate and the claim. Only the name of the refusal differs.
--
-- 181 excluded this one on two readings, and this migration's own comment
-- records why neither survived contact with the measurement: the cheaper Task
-- the exclusion was protecting is not reachable from the pick branch and is
-- never offered in the first place, and the test the exclusion was protecting
-- names its Task, so the `p_task_label IS NULL` clause already excludes it.
--
-- What does not change. The predicate is untouched: `claimable_for` still
-- refuses, `budget_refusal_for` still computes the same answer, and no Task
-- becomes claimable that was not. `budget_unreadable` still raises. A caller
-- naming a Task still gets its raise. The pick stays on the books unconsumed,
-- so nothing about what the Program was going to do is lost -- only the
-- exception that threw away the work the budget did fund.
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
        -- These five and no others, because these five are the answers a
        -- retry cannot mend. The four reservation answers come from
        -- `budget_refusal_for` asking whether one more run's worst case --
        -- `run_tokens`, `run_requests` -- can be set aside at all, which is a
        -- question with the same answer for every Task the Program has.
        --
        -- Ticket 184 adds `unaffordable`, which ticket 181 left out on the
        -- reading that it "is a statement about one Task being too expensive
        -- rather than about the Program having no room, and a cheaper Task may
        -- still be claimable". Both halves of that were wrong here. The cheaper
        -- Task is not reachable from this branch -- a Task has already been
        -- picked, and the walk that could go looking is the ELSE below -- and it
        -- does not need to be: `rank_candidates` selects with
        -- `claimable_for(t, w) IS NULL`, and `SlateClaimTest`'s
        -- `test_an_unaffordable_task_is_not_offered` holds that an unaffordable
        -- Task is never written into a slate at all. The only way to reach this
        -- arm is therefore the race ticket 181 measured: affordable when the
        -- slate was written, unaffordable by the claim, because the
        -- orchestrator's own chooser run spent the margin in between. A Program
        -- in that state has no room, which is the same fact the four above
        -- report.
        --
        -- The other half was about a test, and that reading was simply not
        -- checked. `test_a_task_the_budget_no_longer_covers_is_refused_after_being_offered`
        -- arranges its refusal with `SELECT claim_task($1)` naming the Task, so
        -- the `p_task_label IS NULL` clause ticket 181 added excludes it however
        -- long this list grows. It still asserts its raise and still gets it.
        --
        -- `budget_unreadable` keeps the raise for its own reason: a capacity
        -- that cannot be read is a broken Program rather than a spent one, and
        -- must not quietly report an idle queue.
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
                            'lane_tokens_reserved', 'lane_requests_reserved',
                            'unaffordable') THEN
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
