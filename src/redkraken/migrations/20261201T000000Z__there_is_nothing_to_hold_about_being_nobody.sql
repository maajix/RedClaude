-- ---------------------------------------------------------------------------
-- 20261201T000000Z__there_is_nothing_to_hold_about_being_nobody.sql
--
-- The anonymous Identity stops being leased.
--
-- Measured: `tests.test_database`, run against a disposable server on
-- 2026-08-26, is 30 failures and 57 errors out of 347, and every one of the 65
-- violations they carry names one source:
--
--     65 source='standing:identity_clamp'
--
-- including the control that exists to say the gate is quiet on a clean
-- database:
--
--     FAIL: test_the_gate_holds_when_nothing_is_broken
--     AssertionError: Lists differ: [] != ['standing:identity_clamp']
--
-- Nobody saw it because the module skips itself whole without
-- `RK_TEST_SUPERUSER_URL`, and the three gates this repository runs need no
-- server. Ticket 197 found this module doing damage when it was run; this is
-- what it was doing the rest of the time.
--
-- WHAT THE ARM ASKS. `check_identity_clamp()` arm (b) reports a clamped Task
-- whose Lease is live and whose run holds no Identity Lease on an Identity the
-- Task names. Three facts turned that into eighty-seven failures:
--
--   * `20261120T000000Z` made EVERY clamped Task carry a `task_identities` row
--     and default it to `_anonymous`. Before it, a fixture's Task named nothing
--     and the arm did not apply.
--   * A fixture that inserts `status = 'running'` with a `lease_expires_at`
--     writes the Task Lease and not the Identity Leases, which `claim_task`
--     writes in the same statement.
--   * The arm has no program filter, and every class in that module shares one
--     database -- so one fixture's Task is reported to every other class that
--     asserts `violations == []`.
--
-- WHY THE FIXTURES ARE NOT THE FIX. `WaveMeasurementTest` stands up four
-- concurrent hunters in one Program, which is what a wave is. Giving each of
-- them the Lease `claim_task` would have written is impossible:
-- `identity_leases_exclusive_idx` is UNIQUE on `identity_entity_id WHERE
-- released_at IS NULL`, they all name `_anonymous`, and only one may hold it.
-- The fixture is not wrong about the product. The product stopped being able to
-- run two anonymous hunts at once on 20261120, and the test is where that
-- showed.
--
-- SO THE LEASE GOES. `identities` carries
--
--     CHECK (class = 'anonymous' OR secret_ref IS NOT NULL)
--
-- which is the schema saying an anonymous Identity is the absence of a
-- credential. There is nothing about it to hold and nothing for a second holder
-- to take, and an exclusive Lease on it is a mutex on being nobody.
-- `20261120T000000Z:84` names this and measures the cost as zero because the
-- driver claims one Task per pass. Ticket 199's `chain` profile floors two
-- clamped lanes -- `hunt` and `conclude` are both `web_hunter` -- so the cost
-- stops being zero the first time two children run at once.
--
-- NOTHING DOWNSTREAM READ IT. `enforce_allowed_receipt_capability` admits a
-- Receipt whose Tool run names no `identity_slot` and whose Identity is NULL
-- through a branch that asks for no Lease at all, and an anonymous Identity has
-- no `identity_slots` row for the other branch to join. The Lease this file
-- stops writing was written and never read.
--
-- TWO FUNCTIONS, REPRODUCED WHOLE because `CREATE OR REPLACE` is the whole
-- body. In `claim_task` the change is the `IF v_clamp` block and nothing else;
-- in `check_identity_clamp` it is one predicate in arm (b).
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
    -- Ticket 201: every Identity the Task names EXCEPT the anonymous one.
    -- `identities` carries `CHECK (class = 'anonymous' OR secret_ref IS NOT
    -- NULL)`: an anonymous Identity is the absence of a credential, so there is
    -- nothing about it to hold and nothing for a second holder to take. Leasing
    -- it anyway put it under `identity_leases_exclusive_idx` -- UNIQUE on
    -- `identity_entity_id WHERE released_at IS NULL` -- which capped every
    -- clamped lane at one concurrent run per Program from the moment
    -- `20261120T000000Z` gave every clamped Task an Identity to name. That file
    -- says so itself and measures the cost as zero because this driver claims
    -- one Task per pass; the cost stops being zero the first time two children
    -- run at once, and `chain` floors two clamped lanes.
    --
    -- The request side already reads it this way. `enforce_allowed_receipt_
    -- capability` admits a Receipt with no `identity_slot` and no Identity
    -- through a branch that asks for no Lease at all, and an anonymous Identity
    -- has no `identity_slots` row to join. So nothing downstream was reading
    -- the Lease this used to write.
    IF v_clamp THEN
        INSERT INTO identity_leases (identity_entity_id, holder_agent_run_id,
                                     expires_at, program_id)
        SELECT ti.identity_entity_id, v_run, now() + w.lease_ttl, p
          FROM task_identities ti
          JOIN identities i ON i.entity_id = ti.identity_entity_id
         WHERE ti.task_id = v_task.id AND i.class <> 'anonymous';

        -- Counted off what the Task NAMES rather than off what was inserted.
        -- A Task that acts anonymously names an Identity and takes no Lease,
        -- and the refusal here has always been about a clamped Task that names
        -- nothing at all -- which `claimable_for` already refuses as
        -- `clamped_without_identity` and this repeats at the last moment it can
        -- still be true.
        SELECT count(*) INTO v_leases
          FROM task_identities ti WHERE ti.task_id = v_task.id;
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


CREATE OR REPLACE FUNCTION check_identity_clamp()
RETURNS TABLE (problem text, subject text, detail text)
LANGUAGE sql STABLE AS $fn$
    -- (a) a clamped Task that acts as nothing. The refusal keeps this out of
    --     flight, so a row here is the refusal having been bypassed -- a
    --     hand-written status change, or a derivation that did not run.
    SELECT 'clamped_task_acts_as_nothing', t.label,
           'status ' || t.status || ' on a clamped lane with no task_identities row'
      FROM tasks t
     WHERE t.status IN ('claimed','running')
       AND identity_clamped_for(t)
       AND NOT EXISTS (SELECT 1 FROM task_identities ti WHERE ti.task_id = t.id)

  UNION ALL
    -- (b) criterion 1's "every", which arm (i) of 024's check does not ask:
    --     that arm passes a run holding one Lease of the two its Task names.
    SELECT 'task_identity_not_held_by_its_run', t.label,
           'the run acts as ' || i.slot_name || ' and holds no lease on it'
      FROM tasks t
      JOIN task_identities ti ON ti.task_id = t.id
      JOIN identities i ON i.entity_id = ti.identity_entity_id
     WHERE lease_live_for(t)
       AND identity_clamped_for(t)
       -- Ticket 201: except the anonymous one, which is no longer leased. The
       -- table's own CHECK says an anonymous Identity has no `secret_ref`, so
       -- asking for a Lease on it is asking a run to hold the absence of a
       -- credential -- and since `20261120T000000Z` every clamped Task names
       -- it, which made this arm report every anonymous hunt in flight.
       AND i.class <> 'anonymous'
       AND NOT EXISTS (SELECT 1 FROM task_held_identities(t.id) hi
                        WHERE hi.identity_entity_id = ti.identity_entity_id)

  UNION ALL
    -- (c) criterion 3 as a standing question rather than as an edit that was
    --     made once. The column is in a capacity view; if nothing in the lane's
    --     own state reads it, it is back to being a name that claims a bound it
    --     does not apply.
    SELECT 'lane_state_ignores_the_clamp', 'scheduler_lane_state',
           'the lane view does not read clamp_to_identity_leases, so the column bounds nothing'
     WHERE pg_get_viewdef('scheduler_lane_state'::regclass)
           !~ 'clamp_to_identity_leases'
$fn$;


DO $$
DECLARE n integer; d text;
BEGIN
    -- Both halves took the change. Asked of the installed text because that is
    -- what a later `CREATE OR REPLACE` would silently undo, and because the
    -- behaviour itself needs two concurrent children to show and this schema
    -- has no way to stand one up inside a migration.
    SELECT count(*) INTO n FROM pg_proc
     WHERE pronamespace = 'public'::regnamespace
       AND proname IN ('claim_task', 'check_identity_clamp')
       AND prosrc ~ 'class <> ''anonymous''';
    IF n <> 2 THEN
        RAISE EXCEPTION 'ticket 201: % of 2 functions exempt the anonymous Identity', n;
    END IF;

    -- And the clamp still holds over everything that is here. A Task acting as
    -- a named Identity without the Lease is still a violation; only the one
    -- that names nobody stopped being one.
    SELECT count(*), string_agg(problem || ' ' || subject, '; ')
      INTO n, d FROM check_identity_clamp();
    IF n > 0 THEN
        RAISE EXCEPTION 'ticket 201: the clamp reports % problem(s): %', n, d;
    END IF;
END $$;
