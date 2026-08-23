-- ===========================================================================
-- Production harness 165 -- an Agent run records what the budget policy
-- charged it, and a Task that burned the same budget twice ends
-- ===========================================================================
-- `agent_runs` has held two numbers since 0006 -- `input_tokens` and
-- `output_tokens` -- and every ceiling in this schema is a comparison against
-- their sum. That sum is the provider's own reading of what each turn's request
-- cost, prefix and all, so the ceiling it bounds is not a token budget: it is a
-- turn budget, and the number of turns it buys is `ceiling / context`. Measured
-- on `rk2hunt20`, a `recon` run carrying 14 000 tokens of context finishes in
-- three of the eighteen turns 250 000 buys it, and a `web_hunter` carrying
-- 40 000 gets six -- which is fewer than a `conclude` needs, so every
-- `web_hunter` run in this tree has ended on `budget` and no Task has ever
-- reached a Finding.
--
-- The reading is not wrong about what was sent. It is wrong about what it
-- costs: a cache read is billed at roughly a tenth of an uncached one, and a
-- long-lived session is mostly cache reads. So the number a budget is spent in
-- and the numbers a provider reports stop being the same number here.
--
--   * the provider's own categories are recorded beside the two that were
--     already there, as telemetry -- `uncached_input_tokens`,
--     `cache_creation_input_tokens`, `cache_read_input_tokens` -- together with
--     `answer_count`, the turns the child counted for itself, which the run
--     report used to drop on the floor;
--   * `budget_tokens` is what the Program, the Lane and the Reservation are
--     charged, and `budget_policy` is the name of the arithmetic that produced
--     it, because a number whose formula moved between two releases and did not
--     say so is a budget nobody can read backwards;
--   * `attempt_profile_sha256` is what makes two attempts the same attempt, and
--     sections 4 and 5 below are the rule that says a Task may not have a
--     third one;
--   * `error_detail` is the redacted sentence a failed run leaves, bounded at
--     2048 characters by the column rather than by whoever writes it.
--
-- What this file does NOT do is decide the arithmetic. `cache-credit-v1` is the
-- launcher's, computed where the usage is read; the database stores the number
-- and the name of the policy that produced it. A CHECK listing the policies
-- would be a second copy of a decision that lives in one place, stale the first
-- time somebody adds one -- the same argument the roster already makes about
-- the vulnerability-class vocabulary.
--
--
-- Why every parameter added below defaults to NULL
-- ---------------------------------------------------------------------------
-- This migration lands before the launcher and the supervisor that fill the
-- columns. An unchanged caller must keep working, so `finish_task_attempt`
-- keeps applying `coalesce(p_x, x)` -- 32's own idiom, for 32's own reason: a
-- caller with nothing to report leaves what is there rather than overwriting a
-- measurement with the absence of one.
--
-- The same rule is what makes the accounting switch safe on its own.
-- `derive_budget_tokens` below fills `budget_tokens` from the raw sum whenever
-- nobody stated one, under the policy name that says that is what happened, so
-- a run closed by today's Python is charged exactly what it is charged today
-- and the historical rows are charged what they were charged when they ran.
-- ===========================================================================


-- ---------------------------------------------------------------------------
-- 1. What a run now records about what it spent
-- ---------------------------------------------------------------------------
ALTER TABLE agent_runs
    ADD COLUMN uncached_input_tokens       bigint,
    ADD COLUMN cache_creation_input_tokens bigint,
    ADD COLUMN cache_read_input_tokens     bigint,
    ADD COLUMN answer_count                integer,
    ADD COLUMN budget_tokens               bigint,
    ADD COLUMN budget_policy               text,
    ADD COLUMN attempt_profile_sha256      text,
    ADD COLUMN error_detail                text;

COMMENT ON COLUMN agent_runs.uncached_input_tokens IS
  'Provider telemetry: the input tokens of this run that were neither written to nor read from the prompt cache. Not what the budget is spent in; `budget_tokens` is.';
COMMENT ON COLUMN agent_runs.cache_creation_input_tokens IS
  'Provider telemetry: the input tokens this run paid to write into the prompt cache.';
COMMENT ON COLUMN agent_runs.cache_read_input_tokens IS
  'Provider telemetry: the input tokens this run read back out of the prompt cache. A long session is mostly this, which is why the raw sum is a turn budget rather than a token budget.';
COMMENT ON COLUMN agent_runs.answer_count IS
  'How many turns the child answered, counted by the child rather than derived from the spend, so that "six turns" stops being arithmetic somebody does afterwards.';
COMMENT ON COLUMN agent_runs.budget_tokens IS
  'What this run is charged against the Program, the Lane and its Reservation. The one number the accounting reads; the provider categories beside it are telemetry.';
COMMENT ON COLUMN agent_runs.budget_policy IS
  'The name of the arithmetic that produced `budget_tokens`. `legacy-raw-v1` is the raw provider sum, which is what a run that stated no policy is charged and what every historical row was charged. Deliberately not a closed vocabulary in the schema: the formula lives in the launcher and a second copy here would go stale the first time one is added.';
COMMENT ON COLUMN agent_runs.attempt_profile_sha256 IS
  'The digest of everything that decides what this attempt was -- the Task, the mission packet, the role, the model, the agent-run ceiling, the budget policy and the build. Two budget ends under one digest are two attempts at the same thing, which is what finish_task_attempt refuses a third of.';
COMMENT ON COLUMN agent_runs.error_detail IS
  'The redacted sentence a run that failed leaves behind, so that a Tool-run or child failure is legible without a transcript. Bounded here rather than by whoever writes it.';

-- Bounded at the column, because "at most 2048 characters" stated only in
-- Python is a bound one more writer can be added without.
ALTER TABLE agent_runs ADD CONSTRAINT agent_runs_error_detail_bounded
    CHECK (error_detail IS NULL OR length(error_detail) <= 2048);

-- A number and the name of what produced it travel together. A `budget_tokens`
-- with no policy is a charge nobody can read backwards, and a policy with no
-- number charged nothing.
ALTER TABLE agent_runs ADD CONSTRAINT agent_runs_budget_tokens_named
    CHECK ((budget_tokens IS NULL) = (budget_policy IS NULL));

-- The digest is compared for equality by section 5, so a blank, a truncated or
-- an upper-case spelling of the same profile would read as a different attempt.
ALTER TABLE agent_runs ADD CONSTRAINT agent_runs_attempt_profile_is_a_digest
    CHECK (attempt_profile_sha256 IS NULL
           OR attempt_profile_sha256 ~ '^[0-9a-f]{64}$');

-- 0019's rule, restated over the column the accounting now reads. A renderer
-- with a model of `none` that had spent budget was already a contradiction the
-- schema refused; moving the accounting without moving this would have left the
-- refusal true of a number nothing reads.
ALTER TABLE agent_runs DROP CONSTRAINT agent_runs_renderer_spends_nothing;
ALTER TABLE agent_runs ADD CONSTRAINT agent_runs_renderer_spends_nothing
    CHECK (runs_as <> 'renderer'
           OR (coalesce(input_tokens, 0) + coalesce(output_tokens, 0) = 0
               AND coalesce(budget_tokens, 0) = 0));


-- ---------------------------------------------------------------------------
-- 2. A run that states no policy is charged the raw sum, and says so
-- ---------------------------------------------------------------------------
-- The whole of what makes this migration landable before the launcher that
-- fills the columns. Every accounting site below reads `budget_tokens` and
-- nothing else; a row whose writer never heard of `budget_tokens` would
-- therefore be charged nothing at all, which is a budget with a hole in it
-- rather than a budget in a new unit.
--
-- So the derivation is the backfill rule applied continuously: whatever raw
-- numbers a run reports, if nobody said what policy charged it, the policy that
-- charged it is the raw sum and the row says that in as many words. A caller
-- that states `budget_tokens` -- which is what `cache-credit-v1` will do --
-- keeps its own number untouched.
--
-- `coalesce` on both, unlike the sum this replaces. `input + output` is NULL
-- when either half is, so a run that reported one of the two counted as zero in
-- `program_budget` and as its measured half in `settle_budget_reservation`.
-- The two disagreed; one column read the same way everywhere ends that.
CREATE FUNCTION derive_budget_tokens() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    IF NEW.budget_tokens IS NULL
       AND (NEW.input_tokens IS NOT NULL OR NEW.output_tokens IS NOT NULL) THEN
        NEW.budget_tokens := coalesce(NEW.input_tokens, 0)
                           + coalesce(NEW.output_tokens, 0);
        -- Named after what actually produced the number rather than after
        -- whatever the caller hoped would: a policy that stated no number did
        -- not charge this run.
        NEW.budget_policy := 'legacy-raw-v1';
    END IF;
    RETURN NEW;
END $fn$;

COMMENT ON FUNCTION derive_budget_tokens() IS
    'Fills `budget_tokens` from the raw provider sum for any run that states no '
    'budget of its own, under the policy name that says the raw sum is what '
    'charged it. What lets the accounting read one column while a caller that '
    'has not been taught about it goes on reporting two.';

-- BEFORE, and named to sort after `agent_runs_charge_unmeasured`: Postgres
-- fires row triggers of one event in trigger-name order, and 32's charge writes
-- the promised tokens onto a run that could not report, which this then has to
-- see. `agent_runs_c...` before `agent_runs_d...` is that ordering, and it is
-- the reason for the name rather than a coincidence of it.
CREATE TRIGGER agent_runs_derive_budget_tokens
    BEFORE INSERT OR UPDATE ON agent_runs
    FOR EACH ROW EXECUTE FUNCTION derive_budget_tokens();

-- And the rows that are already there. Same rule, stated once over history:
-- what they were charged when they ran is the raw sum, and `legacy-raw-v1` is
-- the name of that. A run that reported neither number measured nothing and is
-- left saying so, exactly as it does today.
UPDATE agent_runs
   SET budget_tokens = coalesce(input_tokens, 0) + coalesce(output_tokens, 0),
       budget_policy = 'legacy-raw-v1'
 WHERE budget_tokens IS NULL
   AND (input_tokens IS NOT NULL OR output_tokens IS NOT NULL);


-- ---------------------------------------------------------------------------
-- 3. The accounting reads one column
-- ---------------------------------------------------------------------------
-- Every place this schema summed `input_tokens + output_tokens` to answer "what
-- has been spent". The raw columns stay where they are and go on saying what
-- the provider reported; what moves is which number a ceiling is compared
-- against.

-- The Program envelope, 023's.
CREATE OR REPLACE VIEW program_budget AS
    SELECT p.id AS program_id,
           p.token_budget,
           coalesce(sum(a.budget_tokens), 0)::bigint AS tokens_spent,
           CASE WHEN p.token_budget IS NULL THEN NULL
                ELSE greatest(p.token_budget
                              - coalesce(sum(a.budget_tokens), 0), 0)
           END::bigint AS tokens_left
      FROM programs p
      LEFT JOIN agent_runs a ON a.program_id = p.id
     GROUP BY p.id, p.token_budget;

COMMENT ON VIEW program_budget IS
  'One row per Program: the token envelope it was opened with, what its Agent runs have been charged under their own budget policies, and what is left. Spend is `agent_runs.budget_tokens` and not the raw provider sum, because the raw sum counts a cached prefix at full price on every turn that re-sends it.';

-- The same question per lane, 32's. `program_capacity` reads `program_budget`
-- and needs no edit of its own.
CREATE OR REPLACE VIEW lane_budget AS
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
          SELECT coalesce(sum(a.budget_tokens), 0)::bigint AS tokens_spent,
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

-- The Reservation, settled against what the run was charged rather than against
-- what the provider reported it sent.
CREATE OR REPLACE FUNCTION settle_budget_reservation() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    UPDATE budget_reservations br
       SET settled_at     = now(),
           tokens_spent   = coalesce(NEW.budget_tokens, 0),
           requests_spent = run_contacts(NEW.id)
     WHERE br.agent_run_id = NEW.id AND br.settled_at IS NULL;
    RETURN NULL;
END $fn$;

-- The check that holds the two together, asked in the same unit.
CREATE OR REPLACE FUNCTION check_budget_reservations()
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
           'settled at ' || br.tokens_spent || ' tokens; the run was charged ' ||
           coalesce(a.budget_tokens, 0)
      FROM budget_reservations br
      JOIN agent_runs a ON a.id = br.agent_run_id
     WHERE br.settled_at IS NOT NULL
       AND br.tokens_spent IS DISTINCT FROM coalesce(a.budget_tokens, 0)
  UNION ALL
    -- 23's two questions, asked of the arm 32 added to its rule. They are asked
    -- here rather than added to `check_slate_claim`'s two lists because the
    -- function 32 owns is the one they are about, and a check that has to be
    -- edited in a neighbour's file to cover a new arm is a check the next
    -- ticket forgets.
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

-- What a Task of this kind has cost before, which is what the ranking's cost
-- factor is shrunk toward. Read in the unit the budget is spent in, so a
-- campaign that switches policy does not compare one policy's history against
-- the other's ceiling.
CREATE OR REPLACE FUNCTION cost_for(t tasks, w scheduler_weights) RETURNS numeric
LANGUAGE plpgsql STABLE AS $fn$
DECLARE
    v_role text;
    med    numeric;
    n      integer;
    est    numeric;
BEGIN
    SELECT m.role INTO v_role FROM role_task_kinds m WHERE m.kind = t.kind;

    SELECT count(*), percentile_cont(0.5) WITHIN GROUP (ORDER BY r.total)
      INTO n, med
      FROM (SELECT ar.budget_tokens AS total
              FROM agent_runs ar
             WHERE ar.program_id = t.program_id
               AND ar.stop_reason = 'completed'
               AND ar.role = v_role
               AND ar.kind = t.kind
               AND ar.budget_tokens IS NOT NULL
             -- deterministic: started_at ties are broken by id, exactly as the
             -- queue order is, so two passes read the same N rows
             ORDER BY ar.started_at DESC, ar.id DESC
             LIMIT w.history_window_n) r;

    est := shrunk_toward(n, med,
                         coalesce((w.cost_prior ->> t.kind)::numeric, 0.5)
                             * w.cost_reference_tokens,
                         w.shrinkage_n0);
    RETURN least(greatest(est / w.cost_reference_tokens, w.cost_floor), 1.0);
END $fn$;

-- And the orchestrator session's own ceiling, which counts the runs it opened.
CREATE OR REPLACE VIEW orchestrator_session_usage AS
    SELECT s.id AS session_id,
           s.program_id,
           s.label,
           s.generation,
           s.max_turns,
           s.max_tokens,
           s.max_decisions,
           s.closed_at,
           u.turns,
           u.tokens,
           d.decisions
      FROM orchestrator_sessions s
      CROSS JOIN LATERAL (
          -- A turn is counted the moment it starts, not when it finishes: a
          -- pass that opened a child and died is a turn the session spent.
          SELECT count(*)::integer AS turns,
                 coalesce(sum(coalesce(ar.budget_tokens, 0)), 0)::bigint AS tokens
            FROM agent_runs ar
           WHERE ar.orchestrator_session_id = s.id) u
      CROSS JOIN LATERAL (
          -- Decisions are the choices the session recorded, in every one of the
          -- five words 27 writes: a session that answered `no_choice` eighty
          -- times has decided eighty times and learned something each time.
          SELECT count(*)::integer AS decisions
            FROM events e
            JOIN agent_runs ar ON ar.id = e.agent_run_id
           WHERE ar.orchestrator_session_id = s.id
             AND e.type = 'scheduler.chose') d;


-- ---------------------------------------------------------------------------
-- 4. A Task that has burned the same budget twice
-- ---------------------------------------------------------------------------
-- One more `abandoned_reason`, and it is a fact about the attempt rather than
-- about the engagement or the installation: nothing is wrong with the Task, and
-- nothing has been tried that is not exactly what was tried before. Told apart
-- from `attempts_exhausted` because that one counts attempts however they
-- ended, and this one is the narrower statement that two of them ended the same
-- way against an unchanged profile.
ALTER TABLE tasks DROP CONSTRAINT tasks_abandoned_reason_check;
ALTER TABLE tasks ADD CONSTRAINT tasks_abandoned_reason_check
    CHECK (abandoned_reason IN (
        'out_of_scope','superseded','answered','attempts_exhausted',
        'program_closed','budget_exhausted','near_duplicate',
        'decision_timeout','decision_denied','settled_negative',
        'undispatchable','budget_exhausted_twice'));


-- ---------------------------------------------------------------------------
-- 5. The closing statement, with the values it is closing against
-- ---------------------------------------------------------------------------
-- Dropped and recreated rather than replaced, because a default cannot be added
-- to a signature: `CREATE OR REPLACE` with more parameters is a second function,
-- and a four-argument call would then match both and resolve to neither. 32 made
-- the same move for the same reason when it added the first two.
--
-- The rule this file owns lives here and not in Python, so that no other path
-- into the runtime can produce a third unchanged dispatch. It is enforced by
-- ending the Task: an `abandoned` Task is one no Slate offers and no claim can
-- take, which is what "not picked a third time" means in this schema.
--
-- Read off the rows rather than off a counter: the run being closed has already
-- had its stop reason and its profile written by the statement above, so
-- "how many budget ends does this Task have under this profile" is a count over
-- `agent_runs` and needs nothing remembered between attempts. A changed packet,
-- build or budget policy is a different digest, so the count it belongs to
-- starts at one and the Task gets a first retry again -- without this function
-- knowing what any of those three are.
DROP FUNCTION finish_task_attempt(uuid, text, bigint, bigint);

CREATE FUNCTION finish_task_attempt(
        p_agent_run                   uuid,
        p_stop_reason                 text    DEFAULT 'completed',
        p_input_tokens                bigint  DEFAULT NULL,
        p_output_tokens               bigint  DEFAULT NULL,
        p_uncached_input_tokens       bigint  DEFAULT NULL,
        p_cache_creation_input_tokens bigint  DEFAULT NULL,
        p_cache_read_input_tokens     bigint  DEFAULT NULL,
        p_answer_count                integer DEFAULT NULL,
        p_budget_tokens               bigint  DEFAULT NULL,
        p_budget_policy               text    DEFAULT NULL,
        p_attempt_profile_sha256      text    DEFAULT NULL,
        p_error_detail                text    DEFAULT NULL)
RETURNS jsonb LANGUAGE plpgsql AS $fn$
DECLARE
    p         uuid := rk2_program_required();
    w         scheduler_weights%ROWTYPE;
    v_run     agent_runs%ROWTYPE;
    v_task    tasks%ROWTYPE;
    v_accepted boolean;
    v_status  text;
    v_profile text;
    v_ends    bigint := 0;
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

    n_tool := close_tool_runs(v_run.id);

    UPDATE agent_runs
       SET finished_at   = now(),
           stop_reason   = p_stop_reason,
           input_tokens  = coalesce(p_input_tokens,  input_tokens),
           output_tokens = coalesce(p_output_tokens, output_tokens),
           uncached_input_tokens
               = coalesce(p_uncached_input_tokens, uncached_input_tokens),
           cache_creation_input_tokens
               = coalesce(p_cache_creation_input_tokens, cache_creation_input_tokens),
           cache_read_input_tokens
               = coalesce(p_cache_read_input_tokens, cache_read_input_tokens),
           answer_count  = coalesce(p_answer_count, answer_count),
           budget_tokens = coalesce(p_budget_tokens, budget_tokens),
           budget_policy = coalesce(p_budget_policy, budget_policy),
           attempt_profile_sha256
               = coalesce(p_attempt_profile_sha256, attempt_profile_sha256),
           -- Truncated here as well as bounded on the column, because a run
           -- whose detail ran long is a run whose ending would otherwise be
           -- rolled back by the constraint that was meant to redact it.
           error_detail  = coalesce(left(p_error_detail, 2048), error_detail)
     WHERE id = v_run.id AND finished_at IS NULL;
    GET DIAGNOSTICS n_run = ROW_COUNT;

    n_lease := (release_leases(v_run.id) ->> 'identity_leases')::bigint;

    IF v_run.task_id IS NULL THEN
        RETURN jsonb_build_object('agent_run', v_run.label, 'task', NULL,
                                  'task_status', NULL, 'runs_closed', n_run,
                                  'tool_runs_closed', n_tool, 'leases_released', n_lease);
    END IF;

    SELECT * INTO v_task FROM tasks WHERE id = v_run.task_id FOR UPDATE;
    v_accepted := task_result_accepted(v_task.id);

    -- Ticket 165's fourth open question. Only a budget ending counts, and only
    -- one carrying a profile: a run nobody digested is a run this rule cannot
    -- say anything about, and guessing would end Tasks that had changed.
    v_profile := coalesce(p_attempt_profile_sha256, v_run.attempt_profile_sha256);
    IF p_stop_reason = 'budget' AND v_profile IS NOT NULL THEN
        SELECT count(*) INTO v_ends FROM agent_runs a
         WHERE a.task_id = v_task.id
           AND a.stop_reason = 'budget'
           AND a.attempt_profile_sha256 = v_profile;
    END IF;

    IF v_task.status IN ('done','failed','abandoned') THEN
        -- Already settled. Not re-settled and not re-counted: a second call is
        -- a repeat of one attempt, not a second attempt.
        v_status := v_task.status;
    ELSIF v_accepted THEN
        v_status := 'done';
        UPDATE tasks SET status = 'done', finished_at = now(), priority = NULL
         WHERE id = v_task.id;
    ELSIF v_ends >= 2 THEN
        -- Before `attempts_exhausted`, because it is the more exact account of
        -- the same ending: the attempts were spent, and they were spent twice
        -- on the identical dispatch.
        v_status := 'abandoned';
        UPDATE tasks SET status = 'abandoned',
                         abandoned_reason = 'budget_exhausted_twice',
                         finished_at = now(), priority = NULL
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
                              'leases_released', n_lease,
                              'budget_ends', v_ends);
END $fn$;

REVOKE ALL ON FUNCTION finish_task_attempt(
        uuid, text, bigint, bigint, bigint, bigint, bigint, integer, bigint,
        text, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION finish_task_attempt(
        uuid, text, bigint, bigint, bigint, bigint, bigint, integer, bigint,
        text, text, text) TO rk2_runtime;

COMMENT ON FUNCTION finish_task_attempt(
        uuid, text, bigint, bigint, bigint, bigint, bigint, integer, bigint,
        text, text, text) IS
    'Ends one attempt whichever way it ended, in one transaction: the Tool runs '
    'are closed, the run is closed with what it reported and what its budget '
    'policy charged it, the Leases are released and the Task is settled. Every '
    'value after the stop reason defaults to NULL and is applied with coalesce, '
    'so a caller with nothing to report overwrites no measurement. A second '
    'budget ending under the same attempt profile abandons the Task as '
    'budget_exhausted_twice rather than offering an identical dispatch a third '
    'time.';

-- The declared surface follows the signature, and it is checked both ways: a
-- granted verb with no row and a row naming no verb both fail the gate.
DELETE FROM runtime_verb_surface
 WHERE verb = 'finish_task_attempt(uuid, text, bigint, bigint)';

INSERT INTO runtime_verb_surface (verb, added_by, note) VALUES
    ('finish_task_attempt(uuid, text, bigint, bigint, bigint, bigint, bigint, integer, bigint, text, text, text)',
     '165',
     'ends one Task attempt and records what the run reported, what its budget policy charged it and the attempt profile the two-budget-ends rule reads');
