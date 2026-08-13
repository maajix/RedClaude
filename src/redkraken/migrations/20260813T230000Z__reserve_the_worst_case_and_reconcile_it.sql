-- ---------------------------------------------------------------------------
-- 20260813T230000Z__reserve_the_worst_case_and_reconcile_it.sql       (PH2-25)
--
-- A budget that is only ever read after the fact cannot refuse anything. Every
-- ceiling in this schema is spelled as a comparison against what has already
-- been spent -- `program_budget.tokens_left` sums `agent_runs.input_tokens +
-- output_tokens`, `cancel_reason_for` abandons a Task once that reaches zero,
-- and `claimable_for` refuses an offer whose estimate does not fit what is
-- left. All of it is true and none of it bounds anything: four claims taken
-- inside one second all read the same spend, all conclude they fit, and the
-- Program is committed to four runs' worth of a budget that had room for one.
--
-- What is missing is the middle. A claim is the moment a Program commits to a
-- run it cannot un-commit -- the child is spawned, the tokens are the model's
-- to spend -- so the capacity has to leave the pool at the claim and come back
-- when the run is closed and counted. That is what this file adds:
--
--   * the ceilings a configuration states, per Agent run and per lane, beside
--     the total that has been on `programs` since 023;
--   * `budget_reservations`, one row per claim, holding the worst case that
--     claim could spend until the run it opened is settled;
--   * `budget_refusal_for`, the typed reason a Task is not claimable because
--     the capacity it would need is already promised to a run in flight;
--   * settlement, on the one event every terminal path already performs --
--     `agent_runs.finished_at` going from NULL to a time -- so success, abort,
--     refusal, timeout and crash recovery reconcile through one statement
--     rather than five that have to be kept agreeing.
--
-- No new lock. `claim_task` has taken `pg_advisory_xact_lock` over the Program
-- since 023 and calls it the counting window; the reservation is written
-- inside it, and the reads that decide admission happen inside it too. Two
-- concurrent claims on one Program therefore serialise where they already
-- serialised, and the second reads the first's reservation.
-- ---------------------------------------------------------------------------


-- ---------------------------------------------------------------------------
-- 1. The ceilings a configuration states
-- ---------------------------------------------------------------------------
-- `programs.token_budget` is the total and has been since 023. These are the
-- two ceilings a total cannot express: what one run may spend, which is what
-- makes a worst case a number rather than "the rest of the campaign", and what
-- one lane may spend, which is what stops a hunt lane consuming a budget that
-- was meant to reach a report.
--
-- Nullable, and NULL is not zero and not unbounded in the same way twice:
--
--   * `run_token_budget` NULL means the configuration stated no worst case, so
--     the worst case is everything the Program has left. That is the honest
--     reading and it has a visible consequence -- such a Program admits one
--     claim at a time while its total is bounded -- which is why the key is
--     required of every configuration this build accepts.
--   * `lane_token_budget` NULL means the lane is bounded only by the total,
--     which is what every Program did before this file.
--
-- Projected onto `programs` rather than read from the newest revision on every
-- admission, for `token_budget`'s own reason: the scheduler reads budgets in
-- predicates that run per candidate Task, and a lateral into an append-only
-- history there is a join per row for a value that changes on operator action.
-- `check_program_configuration()` below is extended to compare the projection
-- against the document that produced it, so the copy cannot drift quietly.
ALTER TABLE programs
    ADD COLUMN run_token_budget    bigint CHECK (run_token_budget    > 0),
    ADD COLUMN run_request_budget  bigint CHECK (run_request_budget  > 0),
    ADD COLUMN lane_token_budget   bigint CHECK (lane_token_budget   > 0),
    ADD COLUMN lane_request_budget bigint CHECK (lane_request_budget > 0);

COMMENT ON COLUMN programs.run_token_budget IS
  'The most tokens one Agent run may spend, which is the worst case a claim reserves before the child starts. NULL states no worst case, and the honest reading of that is the whole remaining total: such a Program admits one claim at a time while its total is bounded. `[budgets] run_tokens`.';

COMMENT ON COLUMN programs.run_request_budget IS
  'The most target contacts one Agent run may make. Reserved at the claim against the Program''s aggregate and enforced at the door, which is the only place a request is counted. NULL states no worst case, read the same way `run_token_budget` reads it. `[budgets] run_requests`.';

COMMENT ON COLUMN programs.lane_token_budget IS
  'The most tokens one lane may commit -- spent plus reserved -- across the campaign. One number for every lane rather than one per kind: which kinds run more is `scheduler_lanes` and the quota profiles, and this is the ceiling that stops any single lane consuming a total the others still need. NULL leaves the lane bounded only by the total. `[budgets] lane_tokens`.';

COMMENT ON COLUMN programs.lane_request_budget IS
  'The most target contacts one lane may commit, read exactly as `lane_token_budget` is. `[budgets] lane_requests`.';


-- ---------------------------------------------------------------------------
-- 2. The ledger: what a claim promised, until its run is counted
-- ---------------------------------------------------------------------------
-- A row per claim, not a counter on the Program. The reason is 023's own
-- ("recompute, not restore"): a counter and the runs it counts disagree across
-- an abort, and there is no statement that can put a decremented column right
-- again once a process died between the decrement and the spend. A row can be
-- settled by anything that can see the run, including a reconciler that
-- arrives an hour after the machine holding the run went away.
--
-- `tokens` and `requests` are nullable and mean "no worst case was statable":
-- a Program with an unbounded total and no per-run ceiling promises nothing
-- because there is nothing to promise it out of. Every sum over this table
-- coalesces, so an unstated promise counts as zero rather than erasing the sum.
CREATE TABLE budget_reservations (
    id             uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id     uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    agent_run_id   uuid NOT NULL,
    task_id        uuid NOT NULL,
    -- The lane, copied from the Task at the claim. Copied and not joined: a
    -- Task's kind cannot change, and the sums this column feeds run per
    -- candidate inside the claim's own lock.
    kind           text NOT NULL,
    tokens         bigint CHECK (tokens   IS NULL OR tokens   > 0),
    requests       bigint CHECK (requests IS NULL OR requests > 0),
    reserved_at    timestamptz NOT NULL DEFAULT now(),
    settled_at     timestamptz,
    tokens_spent   bigint CHECK (tokens_spent   IS NULL OR tokens_spent   >= 0),
    requests_spent bigint CHECK (requests_spent IS NULL OR requests_spent >= 0),
    -- Settled is one state, not three columns that can each be half of it.
    CHECK ((settled_at IS NULL) = (tokens_spent   IS NULL)),
    CHECK ((settled_at IS NULL) = (requests_spent IS NULL)),
    FOREIGN KEY (agent_run_id, program_id) REFERENCES agent_runs (id, program_id),
    FOREIGN KEY (task_id, program_id)      REFERENCES tasks      (id, program_id)
);

-- One promise per run. A second reservation against one run would be a second
-- claim of a Task that is already claimed, and the sums would count the worst
-- case twice.
CREATE UNIQUE INDEX budget_reservations_one_per_run
    ON budget_reservations (agent_run_id);

CREATE INDEX budget_reservations_open_idx
    ON budget_reservations (program_id, kind) WHERE settled_at IS NULL;

COMMENT ON TABLE budget_reservations IS
  'What one claim promised the run it opened could spend, held out of the Program''s capacity until that run is closed and counted. Written inside `claim_task`''s advisory lock, so concurrent claims cannot each read a pool the other is about to take from; settled by the trigger on `agent_runs.finished_at`, so every way a run can end reconciles through one statement.';

COMMENT ON COLUMN budget_reservations.tokens IS
  'The worst case this run may spend: the Program''s per-run ceiling, or everything left when it states none. NULL when neither is bounded, which promises nothing because there is nothing to promise out of.';

COMMENT ON COLUMN budget_reservations.tokens_spent IS
  'What the run actually cost, copied from `agent_runs` at settlement. The reservation is released by `settled_at`; this column is what it was released against, so a ledger row says both what was promised and what the promise turned out to be worth.';

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('budget_reservations', 'program_id', 'program-scoped: the purge root');

-- Bookkeeping, for 13's reason: the claim and the closure each emit their own
-- Event already, and this row is opened by one and settled by the other. An
-- Event per reservation would put a second copy of the run's life in the log.
INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('budget_reservations', 'bookkeeping',
     'the capacity one claim held out of the pool; the claim and the closure are the events', '25');

GRANT SELECT, INSERT, UPDATE ON budget_reservations TO rk2_runtime;

-- One question asked in three places -- what has this run already sent? -- and
-- therefore one function. The views subtract it from what a run still holds in
-- reserve, the settlement records it, and the door compares it to the ceiling
-- the claim promised; three spellings of one join is three chances for the
-- number the door enforces to stop being the number the pool believes.
--
-- A slot still in flight counts as a contact. The honest answer about a request
-- that may already have left the machine is that it did, and the alternative
-- lets a run hold its whole ceiling open at once.
CREATE FUNCTION run_contacts(p_agent_run uuid) RETURNS bigint
LANGUAGE sql STABLE AS $fn$
    SELECT count(*)::bigint
      FROM egress_reservations er
      JOIN tool_runs tr ON tr.id = er.tool_run_id
     WHERE tr.agent_run_id = p_agent_run
       AND er.contacted IS NOT FALSE
$fn$;

REVOKE ALL ON FUNCTION run_contacts(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION run_contacts(uuid) TO rk2_runtime, rk2_proxy;

COMMENT ON FUNCTION run_contacts(uuid) IS
    'How many target contacts one Agent run has made, counting a reservation '
    'still in flight as a contact. The one spelling of that count: the '
    'capacity views, the settlement and the door all read it here.';


-- ---------------------------------------------------------------------------
-- 3. What is committed, and what is therefore free
-- ---------------------------------------------------------------------------
-- Committed is spent plus promised. Spent comes from `program_budget`, which
-- sums the runs; promised comes from the open reservations. The two cannot
-- double count: a reservation is settled in the same statement that writes the
-- run's tokens, so a run is in exactly one of the two sums at any instant.
--
-- The request side is the same shape over 13's tables: the aggregate ceiling is
-- the compiled `budget_requests` of the Program's current scope version, and
-- what has been spent of it is `program_egress_spend.contacted`, which the door
-- increments once per contact. A Program with no compiled scope version has no
-- request ceiling here and none at the door either -- `reserve_egress_slot`
-- refuses every request with `budget not compiled` -- so there is nothing to
-- reserve and no arm below fires.
--
-- It is also the side where the two sums would otherwise overlap. Tokens are
-- written once, at the closing that settles the promise; contacts are counted
-- as they happen, while the promise that covers them is still open. So what an
-- open reservation still holds is what it has not yet sent, and `run_contacts`
-- is subtracted from it -- otherwise every request in flight is charged twice
-- and the pool refuses claims against capacity nobody holds.
CREATE VIEW program_capacity AS
    SELECT p.id AS program_id,
           b.token_budget,
           b.tokens_spent,
           r.tokens_reserved,
           f.tokens_free,
           -- The worst case one more claim would promise. `coalesce` and not a
           -- default: an unstated per-run ceiling is the whole remainder,
           -- which is what makes such a Program admit one claim at a time.
           coalesce(p.run_token_budget, f.tokens_free) AS run_tokens,
           q.budget_requests AS request_budget,
           e.requests_spent,
           r.requests_reserved,
           g.requests_free,
           coalesce(p.run_request_budget, g.requests_free) AS run_requests
      FROM programs p
      JOIN program_budget b ON b.program_id = p.id
      CROSS JOIN LATERAL (
          SELECT coalesce(sum(br.tokens), 0)::bigint AS tokens_reserved,
                 -- What the promise has left, not what it was made for. Tokens
                 -- need no such subtraction -- a run's tokens are written when
                 -- it closes, in the statement that settles the promise, so the
                 -- two sums cannot overlap -- but the door counts a contact the
                 -- moment it makes it, so a run halfway through its ceiling is
                 -- in `contacted` already. Subtracting the whole promise beside
                 -- it would charge every request in flight twice and refuse
                 -- claims against capacity nobody holds.
                 coalesce(sum(greatest(br.requests - run_contacts(br.agent_run_id), 0)),
                          0)::bigint AS requests_reserved
            FROM budget_reservations br
           WHERE br.program_id = p.id AND br.settled_at IS NULL
      ) r
      CROSS JOIN LATERAL (
          SELECT coalesce((SELECT s.contacted FROM program_egress_spend s
                            WHERE s.program_id = p.id), 0)::bigint AS requests_spent
      ) e
      LEFT JOIN LATERAL (
          SELECT sv.budget_requests FROM program_scope_versions sv
           WHERE sv.program_id = p.id AND sv.version = p.scope_version
      ) q ON true
      CROSS JOIN LATERAL (
          SELECT CASE WHEN b.token_budget IS NULL THEN NULL
                      ELSE greatest(b.token_budget - b.tokens_spent - r.tokens_reserved, 0)
                 END::bigint AS tokens_free
      ) f
      CROSS JOIN LATERAL (
          SELECT CASE WHEN q.budget_requests IS NULL THEN NULL
                      ELSE greatest(q.budget_requests - e.requests_spent - r.requests_reserved, 0)
                 END::bigint AS requests_free
      ) g;

COMMENT ON VIEW program_capacity IS
  'One row per Program: what it may spend, what it has spent, what its claims in flight have promised, and what a further claim would therefore have to fit inside. `run_tokens` and `run_requests` are the worst case the next claim reserves, which is the stated per-run ceiling or the whole remainder when none is stated.';

-- The same question per lane. The lane of a run is the kind of its Task, so a
-- run opened without a Task -- `rk proxy send` opens one -- belongs to no lane
-- and counts only against the Program.
CREATE VIEW lane_budget AS
    SELECT p.id AS program_id,
           k.kind,
           p.lane_token_budget   AS token_budget,
           p.lane_request_budget AS request_budget,
           s.tokens_spent,
           r.tokens_reserved,
           CASE WHEN p.lane_token_budget IS NULL THEN NULL
                ELSE greatest(p.lane_token_budget - s.tokens_spent - r.tokens_reserved, 0)
           END::bigint AS tokens_free,
           s.requests_spent,
           r.requests_reserved,
           CASE WHEN p.lane_request_budget IS NULL THEN NULL
                ELSE greatest(p.lane_request_budget - s.requests_spent - r.requests_reserved, 0)
           END::bigint AS requests_free
      FROM programs p
      CROSS JOIN (SELECT DISTINCT kind FROM scheduler_lanes) k
      CROSS JOIN LATERAL (
          SELECT coalesce(sum(a.input_tokens + a.output_tokens), 0)::bigint AS tokens_spent,
                 coalesce(sum(run_contacts(a.id)), 0)::bigint AS requests_spent
            FROM agent_runs a JOIN tasks t ON t.id = a.task_id
           WHERE a.program_id = p.id AND t.kind = k.kind
      ) s
      CROSS JOIN LATERAL (
          SELECT coalesce(sum(br.tokens), 0)::bigint AS tokens_reserved,
                 -- The Program's subtraction, per kind and for its reason.
                 coalesce(sum(greatest(br.requests - run_contacts(br.agent_run_id), 0)),
                          0)::bigint AS requests_reserved
            FROM budget_reservations br
           WHERE br.program_id = p.id AND br.kind = k.kind AND br.settled_at IS NULL
      ) r;

COMMENT ON VIEW lane_budget IS
  'One row per Program and lane: what that lane has spent and promised of the per-lane ceiling. Not lane_capacity, which is how many Tasks of a kind may run at once; this is how much they may cost. One bounds the concurrency, the other the spend, and a lane can be at neither, either or both. A request is counted for the lane of the Task whose run opened the Tool run that contacted the target; a slot still in flight counts as a contact, because the honest answer about a request that may already have been sent is that it was.';

GRANT SELECT ON program_capacity, lane_budget TO rk2_runtime;


-- ---------------------------------------------------------------------------
-- 4. Admission
-- ---------------------------------------------------------------------------
-- One helper returning one reason, in `cancel_reason_for`'s and `ready_for`'s
-- shape: `claimable_for` gains one arm rather than eight lines of arithmetic,
-- and the vocabulary stays a list of names something can be measured against.
--
-- Every arm reads a capacity that already includes what claims in flight
-- promised. That is the whole difference from the `unaffordable` arm above it,
-- which asks whether the estimate fits what has been spent -- true of four
-- simultaneous claims at once, and the reason this file exists.
CREATE FUNCTION budget_refusal_for(t tasks) RETURNS text
LANGUAGE plpgsql STABLE AS $fn$
DECLARE
    c record;
    l record;
    v_worst bigint;
BEGIN
    SELECT * INTO c FROM program_capacity WHERE program_id = t.program_id;
    -- No visible Program row. `unaffordable` above reaches the same conclusion
    -- from the same cause and gets there first, so this is defence rather than
    -- a path: a capacity that cannot be read is not one a claim may assume.
    IF NOT FOUND THEN RETURN 'budget_unreadable'; END IF;

    -- `run_tokens < 1` is the exhausted case, not a tightening: with no stated
    -- per-run ceiling the worst case IS the remainder, and a remainder of zero
    -- is a claim promising nothing out of nothing.
    IF c.tokens_free IS NOT NULL AND (c.run_tokens < 1 OR c.run_tokens > c.tokens_free) THEN
        RETURN 'program_tokens_reserved';
    END IF;

    IF c.requests_free IS NOT NULL
       AND (c.run_requests < 1 OR c.run_requests > c.requests_free) THEN
        RETURN 'program_requests_reserved';
    END IF;

    SELECT * INTO l FROM lane_budget
     WHERE program_id = t.program_id AND kind = t.kind;
    IF FOUND THEN
        -- With no worst case anywhere -- an unbounded total and no per-run
        -- ceiling -- there is nothing to hold against a lane in advance, and
        -- the lane bound degrades to what it was before this file: it refuses
        -- once the lane is spent rather than before it is. Stated here because
        -- it is the one place a stated ceiling does less than it reads.
        v_worst := coalesce(c.run_tokens, 1);
        IF l.tokens_free IS NOT NULL AND v_worst > l.tokens_free THEN
            RETURN 'lane_tokens_reserved';
        END IF;

        v_worst := coalesce(c.run_requests, 1);
        IF l.requests_free IS NOT NULL AND v_worst > l.requests_free THEN
            RETURN 'lane_requests_reserved';
        END IF;
    END IF;

    RETURN NULL;
END $fn$;

-- 23's discipline, for the arm this file adds to the rule it protects: a
-- scheduler function is the runtime's and nobody else's, and a role the agent
-- can reach must not be able to ask the scheduler anything.
REVOKE ALL ON FUNCTION budget_refusal_for(tasks) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION budget_refusal_for(tasks) TO rk2_runtime;

COMMENT ON FUNCTION budget_refusal_for(tasks) IS
    'NULL when the capacity this Task would need is free, else the name of the '
    'ceiling that is already promised: the Program''s tokens or requests, or '
    'its lane''s. Promised, not spent -- what a claim in flight may still spend '
    'has left the pool, which is what stops concurrent claims each reading a '
    'pool the others are about to take from.';

-- 170000Z's list with one question inserted, and the comment there restated
-- because a function's comment is replaced whole rather than appended to. The
-- new arm sits after `unaffordable` and before `identity_held`: both are about
-- the Program's capacity, one asks it of the estimate and one of the worst
-- case, and neither is a question about another run holding a credential.
CREATE OR REPLACE FUNCTION claimable_for(t tasks, w scheduler_weights) RETURNS text
LANGUAGE plpgsql STABLE AS $fn$
DECLARE v text;
BEGIN
    IF t.status IS DISTINCT FROM 'pending' THEN RETURN 'not_pending'; END IF;

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

    IF identity_held_for(t) THEN RETURN 'identity_held'; END IF;

    IF NOT EXISTS (SELECT 1 FROM effective_lane_capacity lc
                    WHERE lc.program_id = t.program_id AND lc.kind = t.kind) THEN
        RETURN 'no_role_runs_this_kind';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM scheduler_lane_state s
                    WHERE s.program_id = t.program_id AND s.kind = t.kind
                      AND s.headroom > 0) THEN
        RETURN 'lane_full';
    END IF;

    IF (SELECT count(*) FROM tasks c
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
    'answers to two different questions. Its global_subagent_cap arm counts '
    'the Program''s claimed and running subagent Tasks, which is the wider of '
    'the two populations max_concurrent_subagents bounds: the pre-tool gate '
    'counts one session''s outstanding delegations against the same number. '
    'Its budget arms ask `budget_refusal_for`, which reads capacity that '
    'claims in flight have already promised.';

-- 200000Z's claim with the reservation written into it. Everything above the
-- INSERT is that file's, unchanged; what is new is that the run it opens comes
-- with the capacity it is allowed to spend held out of the pool, inside the
-- advisory lock the function has taken since 023 and calls its counting window.
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
    IF v_clamp AND v_task.hypothesis_id IS NOT NULL THEN
        INSERT INTO identity_leases (identity_entity_id, holder_agent_run_id,
                                     expires_at, program_id)
        SELECT i, v_run, now() + w.lease_ttl, p
          FROM (SELECT unnest(ARRAY[h.identity_a_entity_id, h.identity_b_entity_id]) AS i
                  FROM hypotheses h WHERE h.id = v_task.hypothesis_id) x
         WHERE i IS NOT NULL;
    END IF;

    UPDATE task_slate SET consumed = true
     WHERE program_id = p AND task_id = v_task.id AND NOT consumed;

    -- The choice has been acted on, whichever entry the claim took. A pick left
    -- outstanding here would be read by the next claim as a choice about a Task
    -- that is already running.
    PERFORM supersede_pick(p);

    RETURN (SELECT label FROM agent_runs WHERE id = v_run);
END $fn$;

COMMENT ON FUNCTION claim_task(text) IS
    'Commits one choice off the current Slate, re-asking every eligibility '
    'condition inside the transaction that takes the Task. A named Task and a '
    'recorded pick are both refused when they have gone stale; with neither, '
    'the Slate is walked in its own order and the first entry still admitted '
    'is taken. The run it opens carries the claimed role''s own model and '
    'effort, read from the roster row rather than decided here, and the worst '
    'case that run may spend, held out of the Program''s capacity until it is '
    'closed and counted.';


-- ---------------------------------------------------------------------------
-- 5. Reconciliation, on the one event every ending already performs
-- ---------------------------------------------------------------------------
-- Success, refusal, park, abort, lease expiry and crash recovery are six code
-- paths and one fact: `agent_runs.finished_at` stops being NULL. Settling
-- there rather than in each of them is what makes "reconciled on every
-- terminal path" a property of the schema instead of a list of functions
-- somebody has to remember to extend -- including the ones this ticket has not
-- been written yet to know about.
--
-- What it settles against is what the run says it cost -- and a run that was
-- killed says nothing, which is the case the trigger below it exists for.
CREATE FUNCTION settle_budget_reservation() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    UPDATE budget_reservations br
       SET settled_at     = now(),
           tokens_spent   = coalesce(NEW.input_tokens, 0) + coalesce(NEW.output_tokens, 0),
           requests_spent = run_contacts(NEW.id)
     WHERE br.agent_run_id = NEW.id AND br.settled_at IS NULL;
    RETURN NULL;
END $fn$;

COMMENT ON FUNCTION settle_budget_reservation() IS
    'Gives back what a claim promised, against what the run it opened turned '
    'out to cost. Fires on the transition every ending shares, so no terminal '
    'path has to remember to reconcile and a path added later cannot forget.';

-- The run that cannot report. A child killed at its timeout and a run whose
-- machine went away are the two endings with no usage behind them: the tokens
-- were spent -- the model is not a process this system can interrupt mid-token
-- -- and the only account of them died with the child. `aborted` is the
-- column's word for exactly that ending, and both `resume_program` and the
-- lease sweep already write it.
--
-- Settling such a run at zero was the first draft and it is wrong: it gives
-- back capacity that was consumed, leaves `program_budget.tokens_spent` where
-- it was, and makes a Program that loses every child immortal -- the one shape
-- where a runaway costs nothing. What it is charged instead is what it
-- promised, which is the only number anyone has a right to. Charged as input
-- because the split is unknowable and the ceiling is the sum.
--
-- `BEFORE`, so the row the settlement reads is already the row that was
-- charged, and the two never disagree about one run. Not a renderer: 0019's
-- CHECK says a renderer spends nothing, and a renderer never held a promise
-- to charge.
CREATE FUNCTION charge_unmeasured_run() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE v_promised bigint;
BEGIN
    IF NEW.stop_reason = 'aborted'
       AND NEW.input_tokens IS NULL AND NEW.output_tokens IS NULL
       AND NEW.runs_as IS DISTINCT FROM 'renderer' THEN
        SELECT br.tokens INTO v_promised
          FROM budget_reservations br
         WHERE br.agent_run_id = NEW.id AND br.settled_at IS NULL;
        -- A promise of nothing is nothing to charge: an unbounded Program with
        -- no per-run ceiling reserved NULL, and there is no number to write.
        IF v_promised IS NOT NULL THEN
            NEW.input_tokens  := v_promised;
            -- Both columns, because `program_budget` sums `input + output` per
            -- run and NULL + n is NULL: a charge written to one column alone
            -- is a charge the Program's own budget never sees.
            NEW.output_tokens := 0;
        END IF;
    END IF;
    RETURN NEW;
END $fn$;

COMMENT ON FUNCTION charge_unmeasured_run() IS
    'Charges a run that was killed or lost what its claim reserved, because a '
    'run that cannot report is not a run that spent nothing. Only when nothing '
    'was measured: a reported zero is a measurement and stands.';

CREATE TRIGGER agent_runs_charge_unmeasured
    BEFORE UPDATE OF finished_at ON agent_runs
    FOR EACH ROW WHEN (OLD.finished_at IS NULL AND NEW.finished_at IS NOT NULL)
    EXECUTE FUNCTION charge_unmeasured_run();

CREATE TRIGGER agent_runs_settle_budget
    AFTER UPDATE OF finished_at ON agent_runs
    FOR EACH ROW WHEN (OLD.finished_at IS NULL AND NEW.finished_at IS NOT NULL)
    EXECUTE FUNCTION settle_budget_reservation();

-- The closing statement now carries the usage it is closing against. Two more
-- parameters and not two more statements: the trigger above reads the row it
-- settles from, so tokens written after `finished_at` would settle the
-- reservation against a run that had not been counted yet.
--
-- `coalesce(p_input_tokens, input_tokens)` rather than an assignment: a caller
-- with nothing to report -- a renderer, a run the SDK never answered for --
-- leaves what is already there rather than overwriting a measurement with the
-- absence of one.
DROP FUNCTION finish_task_attempt(uuid, text);

CREATE FUNCTION finish_task_attempt(p_agent_run uuid,
                                    p_stop_reason text DEFAULT 'completed',
                                    p_input_tokens bigint DEFAULT NULL,
                                    p_output_tokens bigint DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql AS $fn$
DECLARE
    p         uuid := rk2_program_required();
    w         scheduler_weights%ROWTYPE;
    v_run     agent_runs%ROWTYPE;
    v_task    tasks%ROWTYPE;
    v_accepted boolean;
    v_status  text;
    n_tool    bigint := 0;
    n_lease   bigint := 0;
    n_run     bigint := 0;
BEGIN
    SELECT * INTO w FROM scheduler_weights WHERE active;
    IF NOT FOUND THEN RAISE EXCEPTION 'no active scheduler_weights row'; END IF;

    SELECT * INTO v_run FROM agent_runs
     WHERE id = p_agent_run AND program_id = p FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'agent run % is not this Program''s', p_agent_run
            USING ERRCODE = 'check_violation';
    END IF;

    PERFORM set_actor('runtime', 'rk run');
    PERFORM set_cause(v_run.id, v_run.task_id);

    UPDATE tool_runs SET status = 'error', finished_at = now()
     WHERE program_id = p AND agent_run_id = v_run.id AND status = 'running';
    GET DIAGNOSTICS n_tool = ROW_COUNT;

    UPDATE agent_runs
       SET finished_at   = now(),
           stop_reason   = p_stop_reason,
           input_tokens  = coalesce(p_input_tokens,  input_tokens),
           output_tokens = coalesce(p_output_tokens, output_tokens)
     WHERE id = v_run.id AND finished_at IS NULL;
    GET DIAGNOSTICS n_run = ROW_COUNT;

    n_lease := (release_leases(v_run.id) ->> 'identity_leases')::bigint;

    IF v_run.task_id IS NULL THEN
        RETURN jsonb_build_object('agent_run', v_run.label, 'task', NULL,
                                  'task_status', NULL, 'runs_closed', n_run,
                                  'tool_runs_closed', n_tool, 'leases_released', n_lease);
    END IF;

    SELECT * INTO v_task FROM tasks WHERE id = v_run.task_id FOR UPDATE;
    v_accepted := EXISTS (SELECT 1 FROM proposals pr
                           WHERE pr.task_id = v_task.id AND pr.status = 'promoted');

    IF v_task.status IN ('done','failed','abandoned') THEN
        -- Already settled. Not re-settled and not re-counted: a second call is
        -- a repeat of one attempt, not a second attempt.
        v_status := v_task.status;
    ELSIF v_accepted THEN
        v_status := 'done';
        UPDATE tasks SET status = 'done', finished_at = now(), priority = NULL
         WHERE id = v_task.id;
    ELSIF v_task.attempts >= w.max_attempts THEN
        v_status := 'abandoned';
        UPDATE tasks SET status = 'abandoned', abandoned_reason = 'attempts_exhausted',
                         finished_at = now(), priority = NULL
         WHERE id = v_task.id;
    ELSE
        -- Back to the queue with the attempt spent. The attempt is spent
        -- because it happened: `claim_task` counted it, a child ran, and a
        -- runtime that gave it back would loop on a task that fails the same
        -- way every time.
        v_status := 'pending';
        UPDATE tasks SET status = 'pending', claimed_at = NULL, priority = NULL
         WHERE id = v_task.id;
    END IF;

    RETURN jsonb_build_object('agent_run', v_run.label, 'task', v_task.label,
                              'task_status', v_status, 'accepted', v_accepted,
                              'runs_closed', n_run, 'tool_runs_closed', n_tool,
                              'leases_released', n_lease);
END $fn$;

REVOKE ALL ON FUNCTION finish_task_attempt(uuid, text, bigint, bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION finish_task_attempt(uuid, text, bigint, bigint) TO rk2_runtime;

COMMENT ON FUNCTION finish_task_attempt(uuid, text, bigint, bigint) IS
    'Ends one attempt whichever way it went, and records what it cost. The '
    'Task''s next status is read from whether a proposal was promoted rather '
    'than from what the caller hoped; the usage is written in the same '
    'statement that closes the run, because the reservation is settled off '
    'that row the moment it closes.';


-- ---------------------------------------------------------------------------
-- 6. The door, where a request is actually counted
-- ---------------------------------------------------------------------------
-- 13's function with one arm added. A per-run request ceiling cannot be
-- enforced at the claim: the claim reserves the worst case, and what makes the
-- worst case true is something refusing the run's request number 51 when it
-- promised 50. That is here, and only here -- the door is the one place a
-- contact is counted.
--
-- The lane and the Program need no arm of their own. Admission has already
-- held every claim's worst case out of both, and this arm holds each run to
-- its own: a lane cannot exceed a ceiling that every run inside it is bounded
-- by and every claim into it was measured against.
--
-- No `retry_at`, for the reason 13 gives the aggregate: this is a limit no
-- amount of waiting clears, and a caller told to retry would spin until its
-- capability expired.
CREATE OR REPLACE FUNCTION reserve_egress_slot(
    p_capability text,
    p_protocol   text,
    p_host       text,
    p_port       integer,
    p_path_raw   text,
    p_path_norm  text
) RETURNS TABLE (
    reservation uuid,
    granted     boolean,
    reason      text,
    retry_at    timestamptz,
    -- Not `target`: an output parameter is a PL/pgSQL variable, and two of the
    -- tables below have a column of that name. Every statement mentioning one
    -- would be ambiguous, and PostgreSQL says so rather than guessing.
    scope_target text
)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    v_auth    record;
    v_version integer;
    v_limits  record;
    v_class   text;
    v_ord     integer;
    v_target  text;
    v_spend   program_egress_spend%ROWTYPE;
    v_bucket  program_egress_budget%ROWTYPE;
    v_tokens  numeric;
    v_live    integer;
    v_soonest timestamptz;
    v_run_cap bigint;
    v_run_hit bigint;
BEGIN
    -- Resolved here rather than trusted from the first decision. The capability
    -- is re-resolved on every call for the same reason `authorize` re-decides
    -- the URL: a Program halted, a lease lapsed or a Tool run closed between
    -- the two calls, and a budget taken against a dead capability would spend a
    -- Program's total on a request nothing authorised.
    SELECT * INTO v_auth FROM resolve_egress_capability(p_capability);
    IF NOT FOUND THEN
        RAISE EXCEPTION 'egress capability refused' USING ERRCODE = '23514';
    END IF;

    SELECT p.scope_version INTO v_version FROM programs p WHERE p.id = v_auth.program_id;
    SELECT sv.budget_burst, sv.budget_concurrency, sv.budget_requests,
           sv.budget_window_seconds
      INTO v_limits
      FROM program_scope_versions sv
     WHERE sv.program_id = v_auth.program_id AND sv.version = v_version;

    -- Which target this is, in the policy's words. `rule_ord` names the rule
    -- that decided the request, and its pattern is the thing being rate
    -- limited: one bucket for `*.example.com` and everything under it.
    SELECT s.scope_class, s.rule_ord INTO v_class, v_ord
      FROM scope_class_of(v_auth.program_id, v_version,
                          p_host, p_port, p_path_raw, p_path_norm,
                          p_protocol, 'request') s;
    IF coalesce(v_class, 'denied') NOT IN ('target', 'egress_support') THEN
        RAISE EXCEPTION 'egress request is outside current scope' USING ERRCODE = '23514';
    END IF;
    SELECT r.pattern_text INTO v_target
      FROM program_scope_rules r
     WHERE r.program_id = v_auth.program_id AND r.version = v_version AND r.ord = v_ord;
    -- The scope decision above cited a rule, so this is defence rather than a
    -- branch anything reaches: falling back to the host keeps the bucket
    -- narrower than the policy rather than wider.
    v_target := coalesce(v_target, p_host);
    scope_target := v_target;

    IF v_limits.budget_burst IS NULL OR v_limits.budget_concurrency IS NULL
       OR v_limits.budget_requests IS NULL OR v_limits.budget_window_seconds IS NULL THEN
        -- A policy that never said what it was authorising authorises nothing.
        reservation := NULL; granted := false; retry_at := NULL;
        reason := 'budget not compiled';
        RETURN NEXT; RETURN;
    END IF;

    PERFORM set_actor('runtime');

    -- The Program row first, always, so two targets under one Program take
    -- their locks in one order and cannot wait on each other.
    INSERT INTO program_egress_spend (program_id) VALUES (v_auth.program_id)
        ON CONFLICT (program_id) DO NOTHING;
    SELECT * INTO v_spend FROM program_egress_spend
     WHERE program_id = v_auth.program_id FOR UPDATE;

    INSERT INTO program_egress_budget (program_id, target, tokens)
    VALUES (v_auth.program_id, v_target, v_limits.budget_burst)
        ON CONFLICT (program_id, target) DO NOTHING;
    SELECT * INTO v_bucket FROM program_egress_budget
     WHERE program_id = v_auth.program_id AND target = v_target FOR UPDATE;

    -- Slots whose holder never came back. Released rather than refunded: a
    -- proxy that died mid-exchange may well have reached the target, and
    -- handing the request back would let a crash loop spend the total twice.
    UPDATE egress_reservations
       SET released_at = clock_timestamp(), contacted = true
     WHERE program_id = v_auth.program_id AND target = v_target
       AND released_at IS NULL AND expires_at <= clock_timestamp();

    -- Refill by elapsed time, clamped to the bucket's capacity. `least` is what
    -- makes a shrunk `burst` take effect on the next request rather than after
    -- the old capacity has drained.
    v_tokens := least(
        v_limits.budget_burst::numeric,
        v_bucket.tokens
            + extract(epoch FROM clock_timestamp() - v_bucket.refilled_at)::numeric
              * v_limits.budget_burst::numeric / v_limits.budget_window_seconds::numeric
    );

    -- The total first: it is the limit that no amount of waiting clears, and a
    -- caller told to retry a request the engagement can never afford would spin
    -- until the capability expired.
    IF v_spend.contacted >= v_limits.budget_requests THEN
        UPDATE program_egress_spend SET exhausted = exhausted + 1
         WHERE program_id = v_auth.program_id;
        UPDATE program_egress_budget
           SET tokens = v_tokens, refilled_at = clock_timestamp()
         WHERE program_id = v_auth.program_id AND target = v_target;
        INSERT INTO events (program_id, type, actor_kind, agent_run_id, task_id, payload)
        VALUES (v_auth.program_id, 'egress.budget_exhausted', 'runtime',
                v_auth.agent_run_id, v_auth.task_id,
                jsonb_build_object('schema_version', 1, 'target', v_target,
                                   'requests', v_limits.budget_requests,
                                   'contacted', v_spend.contacted));
        reservation := NULL; granted := false; retry_at := NULL;
        reason := 'budget exhausted';
        RETURN NEXT; RETURN;
    END IF;

    -- This run against what its claim promised. Only a run a claim opened has
    -- a reservation, so a Tool run opened outside the scheduler -- `rk proxy
    -- send` opens one -- is bounded by the Program's total alone, as it was
    -- before this arm existed.
    SELECT br.requests INTO v_run_cap
      FROM budget_reservations br
     WHERE br.agent_run_id = v_auth.agent_run_id AND br.settled_at IS NULL;

    IF v_run_cap IS NOT NULL THEN
        -- The same count the pool subtracted when it admitted this run, so what
        -- the door refuses at is what the capacity views already stopped
        -- offering.
        v_run_hit := run_contacts(v_auth.agent_run_id);

        IF v_run_hit >= v_run_cap THEN
            UPDATE program_egress_spend SET exhausted = exhausted + 1
             WHERE program_id = v_auth.program_id;
            UPDATE program_egress_budget
               SET tokens = v_tokens, refilled_at = clock_timestamp()
             WHERE program_id = v_auth.program_id AND target = v_target;
            INSERT INTO events (program_id, type, actor_kind, agent_run_id, task_id, payload)
            VALUES (v_auth.program_id, 'egress.budget_exhausted', 'runtime',
                    v_auth.agent_run_id, v_auth.task_id,
                    jsonb_build_object('schema_version', 1, 'target', v_target,
                                       'limit', 'run_requests',
                                       'requests', v_run_cap,
                                       'contacted', v_run_hit));
            reservation := NULL; granted := false; retry_at := NULL;
            reason := 'run budget exhausted';
            RETURN NEXT; RETURN;
        END IF;
    END IF;

    SELECT count(*), min(expires_at) INTO v_live, v_soonest
      FROM egress_reservations
     WHERE program_id = v_auth.program_id AND target = v_target
       AND released_at IS NULL;

    IF v_live >= v_limits.budget_concurrency THEN
        UPDATE program_egress_budget
           SET tokens = v_tokens, refilled_at = clock_timestamp(),
               throttled = throttled + 1
         WHERE program_id = v_auth.program_id AND target = v_target;
        -- The soonest a slot is certainly free. In practice one frees earlier,
        -- when an exchange finishes; an upper bound is the only honest answer a
        -- row can give about a request still in flight.
        retry_at := v_soonest;
        reservation := NULL; granted := false;
        reason := 'too many concurrent requests';
        INSERT INTO events (program_id, type, actor_kind, agent_run_id, task_id, payload)
        VALUES (v_auth.program_id, 'egress.throttled', 'runtime',
                v_auth.agent_run_id, v_auth.task_id,
                jsonb_build_object('schema_version', 1, 'target', v_target,
                                   'limit', 'concurrency',
                                   'concurrency', v_limits.budget_concurrency,
                                   'retry_at', retry_at));
        RETURN NEXT; RETURN;
    END IF;

    IF v_tokens < 1 THEN
        UPDATE program_egress_budget
           SET tokens = v_tokens, refilled_at = clock_timestamp(),
               throttled = throttled + 1
         WHERE program_id = v_auth.program_id AND target = v_target;
        retry_at := clock_timestamp()
                  + make_interval(secs => ((1 - v_tokens)
                        * v_limits.budget_window_seconds::numeric
                        / v_limits.budget_burst::numeric)::double precision);
        reservation := NULL; granted := false;
        reason := 'rate limited';
        INSERT INTO events (program_id, type, actor_kind, agent_run_id, task_id, payload)
        VALUES (v_auth.program_id, 'egress.throttled', 'runtime',
                v_auth.agent_run_id, v_auth.task_id,
                jsonb_build_object('schema_version', 1, 'target', v_target,
                                   'limit', 'rate',
                                   'burst', v_limits.budget_burst,
                                   'window_seconds', v_limits.budget_window_seconds,
                                   'retry_at', retry_at));
        RETURN NEXT; RETURN;
    END IF;

    UPDATE program_egress_budget
       SET tokens = v_tokens - 1, refilled_at = clock_timestamp(),
           contacted = contacted + 1
     WHERE program_id = v_auth.program_id AND target = v_target;
    UPDATE program_egress_spend
       SET contacted = contacted + 1, last_at = clock_timestamp()
     WHERE program_id = v_auth.program_id;

    INSERT INTO egress_reservations (program_id, tool_run_id, target, expires_at)
    VALUES (v_auth.program_id, v_auth.tool_run_id, v_target,
            clock_timestamp() + egress_reservation_life())
    RETURNING id INTO reservation;

    granted := true; reason := 'reserved'; retry_at := NULL;
    RETURN NEXT;
END $fn$;

COMMENT ON FUNCTION reserve_egress_slot(text,text,text,integer,text,text) IS
  'Takes one request''s worth of the Program''s shared budget under a row lock, or refuses with the reason and the moment the refusal stops being true. Called after the request is authorized and before the name is resolved, so a throttled request emits no DNS query. A run claimed with a request ceiling is also held to that ceiling here, which is what makes the worst case its claim reserved a true bound.';


-- ---------------------------------------------------------------------------
-- 7. The invariants
-- ---------------------------------------------------------------------------

-- Three arms are one property: a reservation is open exactly while the run it
-- was made for is. Structural rather than textual, unlike 71's and 73's,
-- because this one is about rows and not about where a number came from -- and
-- the rows are the whole mechanism. Two more arms guard the eligibility arm
-- this file added, in 23's own words.
--
-- Deliberately not an arm: a Program whose committed tokens exceed its total.
-- A run that spends more than its ceiling produces exactly that, the schema
-- permits it because the model is not a process this system can interrupt
-- mid-token, and a check that fires on data the system permits is one that
-- gets ignored. What is checked here is the bookkeeping; that concurrent
-- claims cannot collectively promise past a ceiling is proved by the tests
-- that run two claims at once.
CREATE FUNCTION check_budget_reservations()
RETURNS TABLE (problem text, subject text, detail text)
LANGUAGE sql STABLE AS $fn$
    SELECT 'reservation_outlives_its_run'::text, br.id::text,
           'capacity is still held out of the pool for an agent run that has finished'
      FROM budget_reservations br
      JOIN agent_runs a ON a.id = br.agent_run_id
     WHERE br.settled_at IS NULL AND a.finished_at IS NOT NULL
  UNION ALL
    SELECT 'reservation_settled_before_its_run', br.id::text,
           'capacity was given back while the run that may still spend it is open'
      FROM budget_reservations br
      JOIN agent_runs a ON a.id = br.agent_run_id
     WHERE br.settled_at IS NOT NULL AND a.finished_at IS NULL
  UNION ALL
    SELECT 'reservation_settled_against_another_number', br.id::text,
           'settled at ' || br.tokens_spent || ' tokens; the run records ' ||
           (coalesce(a.input_tokens, 0) + coalesce(a.output_tokens, 0))
      FROM budget_reservations br
      JOIN agent_runs a ON a.id = br.agent_run_id
     WHERE br.settled_at IS NOT NULL
       AND br.tokens_spent IS DISTINCT FROM
           (coalesce(a.input_tokens, 0) + coalesce(a.output_tokens, 0))
  UNION ALL
    -- 23's two questions, asked of the arm this file added to its rule. They
    -- are asked here rather than added to `check_slate_claim`'s two lists
    -- because the function this file owns is the one they are about, and a
    -- check that has to be edited in a neighbour's file to cover a new arm is
    -- a check the next ticket forgets.
    SELECT 'eligibility_reads_the_clock', p.proname,
           'a function the ranking filter runs reads the wall clock'
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.proname = 'budget_refusal_for'
       AND regexp_replace(p.prosrc, '--[^' || chr(10) || ']*', '', 'g')
           ~* '(now\(\)|current_timestamp|clock_timestamp)'
  UNION ALL
    SELECT 'scheduler_function_public_executable', p.proname,
           'an agent-reachable role can call a scheduler function'
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.proname IN ('budget_refusal_for', 'run_contacts')
       AND has_function_privilege('public', p.oid, 'EXECUTE')
$fn$;

REVOKE ALL ON FUNCTION check_budget_reservations() FROM PUBLIC;

COMMENT ON FUNCTION check_budget_reservations() IS
    'A reservation is open exactly while the run it was made for is, what it '
    'settled against is what that run recorded, and the arm that reads it is '
    'still deterministic and still the runtime''s alone. Capacity held for a '
    'run nobody will ever count is a Program that shrinks every time something '
    'crashes; capacity given back to a run still spending it is the overspend '
    'the reservation exists to prevent.';

INSERT INTO standing_checks(name, query, owner_ticket, note) VALUES
    ('budget_reservations', 'SELECT * FROM check_budget_reservations()', '25',
     'promised capacity is held exactly as long as the run it was promised to, '
     'and the eligibility arm that reads it stays deterministic and private');

-- Arm 4 of 04's check, extended. The four new columns are projections of the
-- same document `platform` and `token_budget` are projections of, and a
-- projection nobody compares is how a policy change goes missing. Compared
-- against the document itself rather than against four more columns on the
-- revision: the document is already on the row, and a second copy would be a
-- third place the number lives.
CREATE OR REPLACE FUNCTION check_program_configuration()
RETURNS TABLE (problem text, object text, detail text)
LANGUAGE sql STABLE AS $$
    -- 1. A Program nobody can say the policy of. This is what a create path
    --    that wrote the root row and then failed leaves behind, and what a
    --    Program opened by hand around `rk run` would leave behind for good.
    SELECT 'program_without_configuration', p.slug,
           'programs row with no program_configurations revision; nothing records the policy it runs under'
      FROM programs p
     WHERE NOT EXISTS (SELECT 1 FROM program_configurations c
                        WHERE c.program_id = p.id)
  UNION ALL
    -- 2. Revisions are 1..n with no gap. A gap means a revision was lost, and
    --    a lost revision is a policy that authorised work and cannot be read
    --    back -- the failure the append-only rule exists to prevent.
    SELECT 'configuration_revisions_not_contiguous', p.slug,
           'revisions ' || c.lowest || '..' || c.highest || ' but ' || c.total || ' row(s)'
      FROM programs p
      JOIN (SELECT program_id, min(revision) AS lowest, max(revision) AS highest,
                   count(*) AS total
              FROM program_configurations GROUP BY program_id) c
        ON c.program_id = p.id
     WHERE c.lowest <> 1 OR c.highest <> c.total
  UNION ALL
    -- 3. A revision that changes nothing. Recording one is how a resume path
    --    that compares the wrong hash announces itself: the policy is
    --    identical, so the revision says a change happened that did not, and
    --    every row citing it afterwards cites a version number with no meaning.
    SELECT 'configuration_revision_changes_nothing',
           p.slug || ' revision ' || c.revision,
           'canonical_sha256 is identical to revision ' || (c.revision - 1)
      FROM program_configurations c
      JOIN program_configurations prior
        ON prior.program_id = c.program_id AND prior.revision = c.revision - 1
       AND prior.canonical_sha256 = c.canonical_sha256
      JOIN programs p ON p.id = c.program_id
  UNION ALL
    -- 4. The Program is not running the policy its newest revision states.
    --    `programs` carries the platform and the budget ceilings as columns
    --    because the scheduler and the quota views read them there, and it
    --    emits no event of its own, so a write that moved them without
    --    recording a revision is a policy change with no before and after. The
    --    revision history is only worth citing if this cannot happen quietly.
    --    The four ceilings 25 added are compared against the revision's own
    --    document, which is where the loader read them from.
    SELECT 'configuration_not_applied', p.slug || ' revision ' || c.revision,
           'the Program runs platform ' || coalesce(p.platform, '(none)') ||
           ' with budget ' || coalesce(p.token_budget::text, '(none)') ||
           ' (run ' || coalesce(p.run_token_budget::text, '(none)') || '/' ||
           coalesce(p.run_request_budget::text, '(none)') || ', lane ' ||
           coalesce(p.lane_token_budget::text, '(none)') || '/' ||
           coalesce(p.lane_request_budget::text, '(none)') ||
           '); its newest revision states ' || coalesce(c.platform, '(none)') ||
           ' with ' || c.token_budget ||
           ' (run ' || coalesce(c.document #>> '{budgets,run_tokens}', '(none)') || '/' ||
           coalesce(c.document #>> '{budgets,run_requests}', '(none)') || ', lane ' ||
           coalesce(c.document #>> '{budgets,lane_tokens}', '(none)') || '/' ||
           coalesce(c.document #>> '{budgets,lane_requests}', '(none)') || ')'
      FROM programs p
      JOIN LATERAL (SELECT revision, platform, token_budget, document
                      FROM program_configurations
                     WHERE program_id = p.id
                     ORDER BY revision DESC
                     LIMIT 1) c ON true
     WHERE p.platform     IS DISTINCT FROM c.platform
        OR p.token_budget IS DISTINCT FROM c.token_budget
        OR p.run_token_budget    IS DISTINCT FROM (c.document #>> '{budgets,run_tokens}')::bigint
        OR p.run_request_budget  IS DISTINCT FROM (c.document #>> '{budgets,run_requests}')::bigint
        OR p.lane_token_budget   IS DISTINCT FROM (c.document #>> '{budgets,lane_tokens}')::bigint
        OR p.lane_request_budget IS DISTINCT FROM (c.document #>> '{budgets,lane_requests}')::bigint
  UNION ALL
    -- 5. Ceilings that cannot all be true at once. A per-run ceiling above the
    --    lane's or the campaign's is a Program where every claim promises more
    --    than there is, so `budget_refusal_for` refuses every Task from the
    --    first one -- and reports it as an exhausted budget, which is the true
    --    answer to the wrong question. The configuration is what is wrong, and
    --    a Program that can never claim anything should say so where the
    --    operator is already looking. Only the per-run ceiling is compared
    --    upwards: a lane ceiling above the total is slack, because the total
    --    binds first and the lane simply never does. A ceiling nobody stated
    --    is not compared either: NULL is unbounded, and unbounded disagrees
    --    with nothing.
    SELECT 'configuration_ceilings_disagree', p.slug,
           'per run ' || coalesce(p.run_token_budget::text, '(none)') || ' tokens/' ||
           coalesce(p.run_request_budget::text, '(none)') || ' requests, per lane ' ||
           coalesce(p.lane_token_budget::text, '(none)') || '/' ||
           coalesce(p.lane_request_budget::text, '(none)') || ', campaign ' ||
           coalesce(p.token_budget::text, '(none)') || '/' ||
           coalesce(q.budget_requests::text, '(none)')
      FROM programs p
      LEFT JOIN LATERAL (SELECT sv.budget_requests FROM program_scope_versions sv
                          WHERE sv.program_id = p.id AND sv.version = p.scope_version) q ON true
     WHERE p.run_token_budget   > p.token_budget
        OR p.run_token_budget   > p.lane_token_budget
        OR p.run_request_budget > q.budget_requests
        OR p.run_request_budget > p.lane_request_budget
$$;

COMMENT ON FUNCTION check_program_configuration() IS
  'Every Program states the policy it runs under, the statement is complete, no revision claims a change that did not happen, the Program runs every ceiling its newest revision states, and those ceilings can all be true at once -- one run may not be promised more than its lane or its campaign has, which is a Program that admits nothing and blames its budget for it. A lane or campaign ceiling nobody can reach is slack, not a contradiction: the tighter one binds first.';

DO $$
DECLARE n integer; d text;
BEGIN
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_budget_reservations();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-25 refuses to finish: % reservation problem(s): %', n, d;
    END IF;

    -- The two neighbours this file reached into: the claim, whose function it
    -- replaced, and the configuration, whose check it replaced.
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_slate_claim();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-25 breaks the slate and the claim (% problems): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_program_configuration();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-25 breaks program configuration (% problems): %', n, d;
    END IF;
END $$;
