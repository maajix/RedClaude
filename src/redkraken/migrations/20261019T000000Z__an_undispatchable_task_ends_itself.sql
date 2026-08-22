-- ---------------------------------------------------------------------------
-- 20261019T000000Z__an_undispatchable_task_ends_itself.sql        (ticket 143)
--
-- `rk2hunt4`, 2026-08-22. An `analyze` Task was opened by hand against an
-- Application, ranked to the top of the slate, and claimed. `Slice._run` then
-- refused it:
--
--     a js_analyst run holds no net.request; this slice serves one target
--     request and T3 needs a role that may make it
--
-- through `ledger.fail`, which makes the whole pass `ok: false` and exits 3.
-- `_pass` claims one Task per pass, so the same Task was claimed again on the
-- next pass and refused the same way. One Task nobody could dispatch ended the
-- campaign, and every later `rk run` with it.
--
-- Two halves, because there are two ways a Task becomes undispatchable and
-- only one of them is a fact the database holds.
--
--   THE HALF THE DATABASE KNOWS. `Slice._run` resolves a target URL from
--   `applications` and `endpoints` and from nothing else, so a `recon` or a
--   `hunt` Task whose subject is a Domain, a Host, a Service, a Technology or
--   an Identity has no address to send its one request to. That is knowable
--   before the Task is ranked, and `ready_for` is where the scheduler asks it.
--   Asked there, the Task never reaches the slate, `scheduler_idle_report`
--   names the predicate that held it back, and `open_task` -- which calls
--   `ready_for` after its insert -- refuses to open one at all. Every producer
--   inherits the refusal at once, including an operator's hand and whatever
--   ticket 140 derives.
--
--   THE HALF IT DOES NOT. Whether the role the roster gives a kind holds
--   `net.request`, and whether that role can be started as an isolated child at
--   all, are facts about `roster.ROLES` and not about any row here. Ticket
--   143's fourth criterion is that this migration does not quietly reverse that
--   decision, and encoding the roster in SQL is exactly what reversing it would
--   look like. So the runtime keeps deciding, and what it gains here is a way
--   to end the Task it decided against: `retire_task`.
--
-- `retire_task` rather than a new `finish_task_attempt` arm. That function
-- settles an attempt, and the arithmetic of an attempt is right for a child
-- that ran: this Task never reached one. It is also the wrong shape, because
-- the caller has a Task and no run to name it by at the point it finds out.
--
-- Why not `cancel_reason_for`. That is the other permanent ending, and it is
-- read by `rank_pass` over every live Task each pass -- a good home for the
-- address question and a bad one for the roster question, which would have to
-- be a list of kinds in SQL that the roster is free to change under it. The
-- address question is not put there either: `ready_for` refusing it is the
-- stronger statement, since a Task that is unready is one the ranking never
-- offers, and a Task that is cancellable is one it offers until the next pass
-- sweeps it.
-- ---------------------------------------------------------------------------

-- ---------------------------------------------------------------------------
-- 1. The ending
-- ---------------------------------------------------------------------------
-- One more `abandoned_reason`. The nine already there are all facts about the
-- engagement -- the scope moved, the claim was answered, the budget ran out.
-- This one is a fact about the installation: the Task is well-formed and this
-- runtime cannot serve it. Told apart from `attempts_exhausted` on purpose,
-- because that one means something tried and failed and this one means nothing
-- tried at all.

ALTER TABLE tasks DROP CONSTRAINT tasks_abandoned_reason_check;
ALTER TABLE tasks ADD CONSTRAINT tasks_abandoned_reason_check
    CHECK (abandoned_reason IN (
        'out_of_scope','superseded','answered','attempts_exhausted',
        'program_closed','budget_exhausted','near_duplicate',
        'decision_timeout','decision_denied','settled_negative',
        'undispatchable'));

INSERT INTO event_types (id, family, subject_table, description) VALUES
    ('task.retired', 'occurrence', NULL,
     'the runtime ended a Task it cannot dispatch, and the sentence that says why');

CREATE FUNCTION retire_task(p_task uuid, p_detail text)
RETURNS text LANGUAGE plpgsql AS $fn$
DECLARE
    p        uuid := rk2_program_required();
    v_task   tasks%ROWTYPE;
    actor    text := coalesce(current_setting('app.actor_id', true), 'rk run');
    cause    uuid;
    prior    text;
BEGIN
    IF nullif(btrim(coalesce(p_detail, '')), '') IS NULL THEN
        RAISE EXCEPTION 'a retired Task says why it was retired'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    SELECT * INTO v_task FROM tasks
     WHERE id = p_task AND program_id = p FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'task % is not this Program''s', p_task
            USING ERRCODE = 'check_violation';
    END IF;

    -- Already ended. Not re-ended and not re-evented: the caller finds out the
    -- same way it would have if it had been the one to end it, and a second
    -- call is a repeat rather than a second ending.
    IF v_task.status IN ('done','failed','abandoned') THEN
        RETURN v_task.status;
    END IF;

    INSERT INTO events (program_id, type, actor_kind, task_id, payload)
    VALUES (p, 'task.retired', 'runtime', v_task.id,
            jsonb_build_object('task', v_task.label,
                               'kind', v_task.kind,
                               'reason', 'undispatchable',
                               'detail', left(p_detail, 500),
                               'actor', actor))
    RETURNING id INTO cause;

    -- The row event the update emits names this one as its cause, the way
    -- `open_task` does it, and puts back whatever cause the caller was already
    -- writing under.
    prior := coalesce(current_setting('app.caused_by_event_id', true), '');
    PERFORM set_config('app.caused_by_event_id', cause::text, true);
    UPDATE tasks
       SET status = 'abandoned', abandoned_reason = 'undispatchable',
           finished_at = now(), priority = NULL, claimed_at = NULL,
           lease_expires_at = NULL
     WHERE id = v_task.id;
    PERFORM set_config('app.caused_by_event_id', prior, true);

    RETURN 'abandoned';
END $fn$;

COMMENT ON FUNCTION retire_task(uuid, text) IS
    'End one live Task this runtime cannot dispatch, as abandoned/undispatchable, '
    'with the sentence that says why as a task.retired event the row event names '
    'as its cause. Returns the status the Task now holds; a Task already ended is '
    'returned as it stands rather than ended twice.';

REVOKE ALL ON FUNCTION retire_task(uuid, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION retire_task(uuid, text) TO rk2_runtime;


-- ---------------------------------------------------------------------------
-- 2. The half the database knows
-- ---------------------------------------------------------------------------
-- `ready_for` unchanged except for the two kinds whose subject is dispatched
-- against a target. The question is the one `execution.STARTED` asks -- is
-- there an `applications` or an `endpoints` row for this subject -- and it is
-- asked in the same words `rk2_promote_tasks` asks it in, because an Endpoint's
-- Application is NOT NULL in 003 and reaching the Endpoint reaches the address.
--
-- `analyze` is not given the same guard. Its Task is dispatched to a role that
-- makes no request at all, so an address is not what it needs, and the reason
-- it cannot run today is the roster's and belongs to section 1.

-- The question `execution.STARTED` asks, as a predicate, so that `ready_for`
-- and anything later that needs it ask it in one place rather than in two
-- copies that can drift. NULL in, NULL out: "is this subject addressable" has
-- no answer about a Task that names no subject, and the callers below say what
-- they make of that themselves.
CREATE FUNCTION rk2_subject_addressable(p_entity uuid) RETURNS boolean
LANGUAGE sql STABLE AS $fn$
    SELECT CASE WHEN p_entity IS NULL THEN NULL ELSE
        EXISTS (SELECT 1 FROM applications a WHERE a.entity_id = p_entity)
     OR EXISTS (SELECT 1 FROM endpoints ep  WHERE ep.entity_id = p_entity)
    END
$fn$;

COMMENT ON FUNCTION rk2_subject_addressable(uuid) IS
    'Whether this Entity is one the dispatch slice can resolve a target URL from '
    '-- an Application, or an Endpoint under one. NULL for no Entity at all.';

REVOKE ALL ON FUNCTION rk2_subject_addressable(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rk2_subject_addressable(uuid) TO rk2_runtime;


CREATE OR REPLACE FUNCTION ready_for(t tasks) RETURNS text
LANGUAGE plpgsql STABLE AS $fn$
DECLARE ok boolean;
BEGIN
    IF t.subject_entity_id IS NOT NULL THEN
        SELECT e.in_scope INTO ok FROM entities e WHERE e.id = t.subject_entity_id;
        IF NOT coalesce(ok, false) THEN RETURN t.kind || '.subject_not_in_scope'; END IF;
    END IF;

    IF t.kind = 'recon' THEN
        IF t.subject_entity_id IS NULL THEN RETURN 'recon.no_subject'; END IF;
        IF rk2_subject_addressable(t.subject_entity_id) IS NOT TRUE THEN
            RETURN 'recon.no_address';
        END IF;
        RETURN NULL;

    ELSIF t.kind = 'hunt' THEN
        IF t.hypothesis_id IS NULL THEN RETURN 'hunt.no_hypothesis'; END IF;
        IF NOT EXISTS (SELECT 1 FROM hypotheses h
                        WHERE h.id = t.hypothesis_id AND h.status = 'testable') THEN
            RETURN 'hunt.hypothesis_not_testable';
        END IF;
        -- Asked only where there is a subject to ask it about. A hunt Task
        -- with none is undispatchable too, but it is not this predicate's
        -- sentence to say so: `derive_chain_unlocks` takes the subject off the
        -- frontier and a NULL there is the runtime's case, ended by
        -- `retire_task` at the point the URL comes back missing.
        IF t.subject_entity_id IS NOT NULL
           AND rk2_subject_addressable(t.subject_entity_id) IS NOT TRUE THEN
            RETURN 'hunt.no_address';
        END IF;
        RETURN NULL;

    ELSIF t.kind = 'analyze' THEN
        -- "at least one agent-visible artifact reachable from an observation on
        -- the subject". Reachability is ticket 12's `artifact_refs` bridge:
        -- `artifacts` is content-addressed and program-global, so a bare hash
        -- lookup would cross programs.
        IF NOT EXISTS (
             SELECT 1
               FROM observations o
               JOIN receipts r     ON r.id = o.receipt_id
               JOIN artifact_refs x ON x.ref_label = r.label
                                   AND x.program_id = o.program_id
               JOIN artifacts a    ON a.sha256 = x.sha256
              WHERE o.subject_entity_id = t.subject_entity_id
                AND a.visibility = 'agent_visible'
                AND NOT a.encrypted AND a.purged_at IS NULL) THEN
            RETURN 'analyze.no_agent_visible_artifact';
        END IF;
        RETURN NULL;

    ELSIF t.kind = 'perform' THEN
        IF t.test_id IS NULL THEN RETURN 'perform.no_test'; END IF;
        IF NOT EXISTS (SELECT 1 FROM tests ts
                         JOIN hypotheses h ON h.id = ts.hypothesis_id
                        WHERE ts.id = t.test_id AND h.status = 'testable') THEN
            RETURN 'perform.claim_not_testable';
        END IF;
        IF EXISTS (SELECT 1 FROM test_replays tp WHERE tp.test_id = t.test_id) THEN
            RETURN 'perform.already_performed';
        END IF;
        RETURN NULL;

    ELSIF t.kind = 'validate' THEN
        IF t.finding_id IS NULL THEN RETURN 'validate.no_finding'; END IF;
        IF NOT EXISTS (SELECT 1 FROM findings f
                        WHERE f.id = t.finding_id AND f.status = 'candidate') THEN
            RETURN 'validate.finding_not_candidate';
        END IF;
        IF NOT EXISTS (SELECT 1 FROM tests ts
                         JOIN finding_hypotheses fh ON fh.hypothesis_id = ts.hypothesis_id
                        WHERE fh.finding_id = t.finding_id) THEN
            RETURN 'validate.no_test_spec';
        END IF;
        RETURN NULL;

    ELSIF t.kind = 'report' THEN
        IF NOT EXISTS (SELECT 1 FROM findings f
                        WHERE f.program_id = t.program_id AND f.status = 'validated') THEN
            RETURN 'report.no_validated_finding';
        END IF;
        RETURN NULL;
    END IF;
    RETURN t.kind || '.unknown_kind';
END $fn$;


-- ---------------------------------------------------------------------------
-- 3. What the runtime now holds
-- ---------------------------------------------------------------------------
-- Ticket 66's registry. A function closed to PUBLIC and executable by
-- `rk2_runtime` is an exception to the rule that closing a function closes it
-- to the runtime too, and `standing:runtime_privileges` refuses an exception
-- nobody wrote down.

INSERT INTO runtime_verb_surface (verb, added_by, note) VALUES
  ('rk2_subject_addressable(uuid)', '143',
   'whether the dispatch slice can resolve a target URL from this Entity; read by ready_for'),
  ('retire_task(uuid, text)', '143',
   'ends one live Task this runtime cannot dispatch; called by Slice._run and by nothing else');
