-- ---------------------------------------------------------------------------
-- 20260813T200000Z__a_role_runs_at_the_rosters_model_and_effort.sql   (PH2-71)
--
-- `claim_task` decided a run's model and effort from `runs_as` and nothing
-- else: `'none'` for the renderer, `'claude-opus-5'` and `'high'` for everyone
-- else. The roster disagrees with that for three of the five agent roles --
-- `recon` runs at `medium`, the orchestrator at `xhigh`, the validator at
-- `max`, and the validator's effort carries its reason in the roster ("a
-- validator false negative costs more than the tokens the effort buys"). A
-- validate task claimed at `high` is that reason silently not in force.
--
-- The model half is worse to leave. `claude-opus-5` is what the alias `opus`
-- resolved to for one measured SDK/CLI pair, recorded in the tool inventory
-- manifest under `models` and version-bound on purpose. The scheduler spelled
-- that resolution out as a literal, so the day the pair resolves `opus` to
-- something else the run row would say the old string and the child would run
-- on the new model.
--
-- So the model and the effort move onto `roles`, beside `max_concurrent` and
-- `clamp_to_identity_leases`, which are there for the same reason: the roster
-- states them once and the scheduler reads them. What lands in
-- `agent_runs.model` is the alias, not a resolution -- `_launch.options_for`
-- hands `role.model` to the SDK unchanged, so the alias is literally what the
-- child was started with, and the resolution stays in the manifest where the
-- pair that performs it is named.
-- ---------------------------------------------------------------------------

-- ---------------------------------------------------------------------------
-- 1. The two fields, on the table that already carries the rest of the row
-- ---------------------------------------------------------------------------

ALTER TABLE roles ADD COLUMN model  text;
ALTER TABLE roles ADD COLUMN effort text;

-- The roster's own values, in the roster's own order. `tests/test_roster.py`
-- reads this statement field by field against `roster.ROLES`, which is what
-- makes "stated in exactly one place" a test rather than a convention.
UPDATE roles r SET model = v.model, effort = v.effort
  FROM (VALUES
      ('orchestrator', 'opus', 'xhigh'),
      ('recon',        'opus', 'medium'),
      ('web_hunter',   'opus', 'high'),
      ('js_analyst',   'opus', 'high'),
      ('validator',    'opus', 'max'),
      ('reporter',     'none', 'none')
  ) AS v(role, model, effort)
 WHERE r.role = v.role;

ALTER TABLE roles ALTER COLUMN model  SET NOT NULL;
ALTER TABLE roles ALTER COLUMN effort SET NOT NULL;

-- Both vocabularies are `agent_runs`'s, because a role's model and effort exist
-- to be written into a run row: a roster value that column would refuse is a claim
-- that fails at INSERT time, on the first task of that kind, in production.
ALTER TABLE roles ADD CONSTRAINT roles_effort_check
    CHECK (effort IN ('none','low','medium','high','xhigh','max'));
ALTER TABLE roles ADD CONSTRAINT roles_renderer_runs_no_model
    CHECK ((runs_as = 'renderer') = (model = 'none' AND effort = 'none'));

COMMENT ON COLUMN roles.model IS
  'The model alias ticket 11''s roster gives this role, which is the string _launch hands the SDK. An alias and not a resolution: the resolution belongs to the measured SDK/CLI pair and lives in the tool inventory manifest, which is version-bound. ''none'' for the renderer, which is not an agent.';

COMMENT ON COLUMN roles.effort IS
  'The reasoning effort ticket 11''s roster gives this role. Three of the five agent roles differ, and the validator''s max carries a reason: a false negative costs more than the tokens the effort buys.';


-- ---------------------------------------------------------------------------
-- 2. The claim reads them
-- ---------------------------------------------------------------------------

-- One SELECT does what two did. `v_runs_as` is gone with the CASE expressions
-- that were its only readers: the renderer's `'none'` is now a row in the
-- roster rather than a branch in the scheduler, which is the whole of this
-- change -- there is no longer any way to spell a role's model or effort here.
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
    'effort, read from the roster row rather than decided here.';


-- ---------------------------------------------------------------------------
-- 3. The standing check
-- ---------------------------------------------------------------------------

-- Both arms are textual, and deliberately so. The property is about where a
-- model and an effort come from, not about what any row holds: a run claimed
-- under a literal that happens to match today's roster is indistinguishable,
-- row by row, from one that read the roster -- and they differ on exactly the
-- day the roster changes. `agent_runs` is also written by openers that are not
-- agent runs at all (`proxy.OPEN_RUN` records an orchestrator run at model
-- `operator` and effort `low`, for a request a person made and no model
-- served), so a row arm comparing every run to its role would be asking those
-- rows to lie.
--
-- Both arms strip `--` comments before matching. Arm (b) would otherwise fire
-- on the paragraph explaining why it exists; arm (a) fires on absence, so an
-- unstripped body would let a commented-out mention of the roster stand in for
-- reading it -- a false negative on exactly the defect being closed.
CREATE FUNCTION check_roster_model_and_effort()
RETURNS TABLE (problem text, subject text, detail text)
LANGUAGE sql STABLE AS $fn$
    -- (a) the claim reads the roster rather than deciding. Two halves, because
    --     each catches a different way back: a body that no longer selects both
    --     fields into its locals from `roles` has stopped reading, and a body
    --     that assigns either local with `:=` has gone back to deciding. The
    --     old defect was the second -- `v_model := CASE WHEN ... END`.
    SELECT 'claim_decides_a_roles_model_or_effort'::text, 'claim_task'::text,
           'claim_task writes a model or an effort it did not read from roles'
      FROM pg_proc p
     CROSS JOIN LATERAL (
         SELECT regexp_replace(p.prosrc, '--[^' || chr(10) || ']*', '', 'g')
     ) AS s(src)
     WHERE p.pronamespace = 'public'::regnamespace AND p.proname = 'claim_task'
       AND (s.src !~ 'roles'
            OR s.src !~ 'INTO[^;]*v_model'
            OR s.src !~ 'INTO[^;]*v_effort'
            OR s.src ~ 'v_model[[:space:]]*:='
            OR s.src ~ 'v_effort[[:space:]]*:=')

  UNION ALL
    -- (b) no function copies a resolution out of the manifest. `claude-opus-5`
    --     is what one measured SDK/CLI pair resolves `opus` to; the pair is
    --     what performs the resolution and the manifest is version-bound to it,
    --     so a copy in a function body is a value that goes stale silently and
    --     without moving.
    SELECT 'model_resolution_spelled_in_sql', p.proname,
           'a function body names a resolved model identifier the manifest owns'
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace
       AND regexp_replace(p.prosrc, '--[^' || chr(10) || ']*', '', 'g')
           ~ 'claude-[a-z]'
$fn$;

REVOKE ALL ON FUNCTION check_roster_model_and_effort() FROM PUBLIC;

COMMENT ON FUNCTION check_roster_model_and_effort() IS
    'Where a run''s model and effort come from: the claim reads the roster row '
    'rather than deciding, and no function body carries a model identifier the '
    'version-bound tool inventory manifest is what resolves.';

INSERT INTO standing_checks(name, query, owner_ticket, note) VALUES
    ('roster_model_and_effort', 'SELECT * FROM check_roster_model_and_effort()', '71',
     'a role''s model and effort are stated once, on roles, and the claim reads them there');


-- ---------------------------------------------------------------------------
-- 4. The invariants this file must not have broken
-- ---------------------------------------------------------------------------

DO $$
DECLARE n integer; d text;
BEGIN
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_roster_model_and_effort();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-71 refuses to finish: % roster problem(s): %', n, d;
    END IF;

    -- The claim is the scheduler's commit surface, so the scheduler's own
    -- closure is the thing a rewrite of it could break. Not
    -- `check_event_log_integrity()`: `roles` carries no emit trigger -- it was
    -- created in 019, after the registry -- and half of what that check asks is
    -- about a trigger sweep that runs as a finalizer, after the last migration.
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_scheduler_closure();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-71 breaks scheduler closure (% problems): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_slate_claim();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-71 breaks the slate and the claim (% problems): %', n, d;
    END IF;

    -- `roles` is readable by everyone and holds no program column, but the
    -- claim rewritten above is the one function that reads it and writes a row
    -- into a Program, so the isolation the claim runs under is asked here too.
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_program_isolation();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-71 breaks program isolation (% problems): %', n, d;
    END IF;
END $$;
