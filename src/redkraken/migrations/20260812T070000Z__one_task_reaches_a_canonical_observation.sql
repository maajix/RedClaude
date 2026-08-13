-- ===========================================================================
-- Production harness 20 -- one Task reaches a canonical Observation
-- ===========================================================================
-- Every row this slice needs already exists. `claim_task` opens the Agent run,
-- `authorize_tool_run` mints the capability, `record_proxy_exchange` writes the
-- Receipt and the Artifact reference, and `proposals` holds what the child
-- said. What no migration has ever written is the step between the last two and
-- the first: the runtime turning a staged proposal into canonical rows, and the
-- Task closing because it did.
--
-- Four things, and the order is the argument.
--
--   `set_cause` -- the two identifiers 013 reads off the session and nothing
--   has ever set. Without it every Event this slice emits names a Program and
--   no run, so "the Receipt, the Artifact, the Tool run, the Agent run, the
--   Task attempt and the proposal share the correct causal identifiers" would
--   be true of the rows and false of the log that proves it.
--
--   `promote_proposal` -- the whole of Promotion. It re-checks provenance on
--   the runtime connection, refuses what it cannot ground, inserts the
--   Observations that survive, and marks the proposal. One transaction, and the
--   Event arrives inside it because `observations` is a row-event table: there
--   is no arrangement here in which the fact and the record of the fact commit
--   apart.
--
--   `tasks_completion_needs_promotion` -- a Task may not reach `done` unless a
--   promoted proposal names it. This is the structural form of "agent
--   completion prose cannot close the Task": the child's `completion_claim` is
--   free text on a staging row, and no amount of it satisfies a predicate over
--   `proposals.status`.
--
--   `finish_task_attempt` -- one call that ends the attempt whichever way it
--   went: the Agent run closed, its Tool runs closed (which is what revokes a
--   capability), its Identity Leases released, and the Task settled to `done`,
--   back to `pending`, or `abandoned` when its attempts are spent. Idempotent,
--   because a crash between the child exiting and this call is the case it
--   exists for -- a second run of it finds nothing open and says so.
-- ===========================================================================


-- ---------------------------------------------------------------------------
-- 1. The causal identifiers the emitter already reads
-- ---------------------------------------------------------------------------
-- 013 writes `events.agent_run_id` and `events.task_id` from two settings and
-- documents neither, because nothing in the harness set them. They are
-- transaction-local for the same reason `set_actor` is: an attribution that
-- survived its transaction would attribute the next one, and on a pooled
-- connection the next one belongs to a different run.
--
-- Deliberately not folded into `set_actor`. An actor is who wrote the row and
-- every write has one; a cause is which run the write happened inside, and the
-- runtime has plenty of writes -- a migration, a resume, an operator's compact
-- read -- that happen inside no run at all. Two calls, so the second one is
-- absent rather than null when there is nothing to say.

CREATE FUNCTION set_cause(p_agent_run uuid, p_task uuid DEFAULT NULL) RETURNS void
LANGUAGE plpgsql AS $fn$
BEGIN
    PERFORM set_config('app.agent_run_id', coalesce(p_agent_run::text, ''), true),
            set_config('app.task_id',      coalesce(p_task::text, ''), true);
END $fn$;

COMMENT ON FUNCTION set_cause(uuid, uuid) IS
    'Declares which Agent run and Task this transaction''s Events were caused '
    'by. Transaction-local, like set_actor: a cause that outlived its '
    'transaction would name the wrong run for the next one.';


-- ---------------------------------------------------------------------------
-- 2. Four more reasons an element can be refused
-- ---------------------------------------------------------------------------
-- 020's eight reasons are everything the staging step can prove: whether the
-- Receipt exists, whose it is, which lane and which run it belongs to. Four
-- more become provable only at Promotion, because only Promotion resolves the
-- element against the canonical tables it is about to become a row in.
--
--   `no_subject`          an Observation is about an Entity -- `observations`
--                         has the column `NOT NULL` -- and the element either
--                         named none or named one this Program has not got.
--                         Staging cannot refuse this: a Mission may propose
--                         the Entity beside the Observation about it, and the
--                         question is whether that Entity resolves by the time
--                         the runtime commits, not whether it existed when the
--                         child spoke.
--   `unknown_kind`        `observation_kinds` is closed and 018 says why: the
--                         value is written by promotion from agent output, so
--                         a free string is a value a model invented.
--   `incompatible_provenance`
--                         the kind exists, the provenance record exists, and
--                         018's `allowed_provenance` says that kind cannot be
--                         produced by that record. Ticket 19's criterion names
--                         "absent, foreign or incompatible provenance"; the
--                         first two are staging's and this is the third, which
--                         needs the kind to be decidable at all.
--   `refused_by_invariant`
--                         `observations` carries six BEFORE INSERT guards and
--                         a promotion cannot restate them: 025 alone refuses a
--                         `transport_parameters_observed` row whose Receipt is
--                         not transport-citable or whose asserted wire fields
--                         disagree with the Receipt's. So the row is attempted
--                         and its refusal caught, and this is what the drop is
--                         called. Without it one element of a kind no promotion
--                         anticipated raises out of the loop, takes every other
--                         Observation of the same proposal with it, and jams
--                         the Task for good -- which an agent choosing that
--                         kind could do on purpose.
--
-- Refusals, not exceptions, for 020's reason: a silent drop is
-- indistinguishable from a thing the agent never proposed, and a raise would
-- lose the other elements of the same proposal along with it.

ALTER TABLE proposal_drops DROP CONSTRAINT proposal_drops_reason_check;
ALTER TABLE proposal_drops ADD CONSTRAINT proposal_drops_reason_check
    CHECK (reason IN ('no_such_receipt','receipt_other_program',
                      'receipt_proxy_internal','receipt_other_run',
                      'no_such_tool_run','no_such_label',
                      'label_other_program','no_provenance',
                      'no_subject','unknown_kind','incompatible_provenance',
                      'refused_by_invariant'));


-- ---------------------------------------------------------------------------
-- 3. Promotion
-- ---------------------------------------------------------------------------
-- The element walk numbers objects and skips everything else, which is exactly
-- what `proposal.Result.elements` does on the way in. It has to be exactly
-- that: `proposal_drops.element_path` is `observations[i]` for the i-th
-- *object*, and a promotion that numbered the raw array would skip a different
-- element than the one staging refused.
--
-- Two provenances and not three. `observation_kinds` also allows `callback`,
-- and nothing here ever promotes one: a callback interaction is a fact the
-- harness observed for itself, `record_callback_interaction` writes that
-- Observation at the moment the interaction lands, and an agent citing a
-- callback would be citing evidence it did not produce. Staging accepts
-- `receipt_label` and `tool_run_label` for the same reason.
--
-- Two things it does not do. It does not judge the completion claim -- that is
-- a claim about the Task, and the Task is settled by `finish_task_attempt`
-- below out of what was promoted rather than out of what was claimed. And it
-- promotes no Entity, Relationship, Hypothesis, evidence edge or suggested
-- Task: those are the next tickets' rows, they have their own dedup and
-- transition rules, and a promotion that wrote them here would write them
-- without those rules. The elements stay in `proposals.payload`, which is where
-- ticket 21 reads them from.

CREATE FUNCTION promote_proposal(p_proposal uuid) RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p           uuid := rk2_program_required();
    v           proposals%ROWTYPE;
    v_next      integer;
    v_element   jsonb;
    v_path      text;
    v_receipt   uuid;
    v_tool_run  uuid;
    v_cited_receipt  text;
    v_cited_tool_run text;
    v_subject   uuid;
    v_kind      text;
    v_allowed   text[];
    v_provenance text;
    v_reason    text;
    v_cited     text;
    v_label     text;
    v_promoted  text[] := '{}';
    v_refused   integer := 0;
BEGIN
    SELECT * INTO v FROM proposals
     WHERE id = p_proposal AND program_id = p FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'proposal % is not a staged result of this Program', p_proposal
            USING ERRCODE = 'check_violation';
    END IF;

    -- Idempotent, and it reports the same answer rather than a different one.
    -- A promotion that ran and a promotion that had already run are the same
    -- state, and the caller retrying after a lost connection needs to be told
    -- what is true rather than what this call did.
    IF v.status <> 'staged' THEN
        RETURN jsonb_build_object(
            'proposal', v.label, 'status', v.status, 'repeated', true,
            'observations', coalesce(
                (SELECT jsonb_agg(o.label ORDER BY o.label) FROM observations o
                  WHERE o.program_id = p AND o.metadata ->> 'proposal' = v.label),
                '[]'::jsonb),
            'refused', (SELECT count(*) FROM proposal_drops d WHERE d.proposal_id = v.id));
    END IF;

    PERFORM set_actor('runtime', 'promotion');
    PERFORM set_cause(v.agent_run_id, v.task_id);

    SELECT coalesce(max(ordinal) + 1, 0) INTO v_next
      FROM proposal_drops WHERE proposal_id = v.id;

    FOR v_element, v_path IN
        SELECT e.value, 'observations[' || (e.n - 1) || ']'
          FROM (SELECT value, row_number() OVER () AS n
                  FROM jsonb_array_elements(
                          CASE WHEN jsonb_typeof(v.payload -> 'observations') = 'array'
                               THEN v.payload -> 'observations' ELSE '[]'::jsonb END)
                 WHERE jsonb_typeof(value) = 'object') e
         ORDER BY e.n
    LOOP
        -- Already refused on the way in. Staging proved the citation wrong;
        -- promotion does not get a second opinion about it.
        CONTINUE WHEN EXISTS (
            SELECT 1 FROM proposal_drops d
             WHERE d.proposal_id = v.id AND d.element_path = v_path);

        v_reason := NULL;
        v_receipt := NULL;
        v_tool_run := NULL;
        v_provenance := NULL;
        v_subject := NULL;
        v_cited := NULL;

        -- Exactly one label, resolving to exactly that row. Deciding out of
        -- what resolved instead would promote an element citing both under
        -- whichever of the two still existed, and citing both is the ambiguity
        -- staging refuses the element for -- the two steps would disagree about
        -- the same element, which is the one thing re-checking must not do.
        v_cited_receipt  := nullif(btrim(v_element ->> 'receipt_label'), '');
        v_cited_tool_run := nullif(btrim(v_element ->> 'tool_run_label'), '');
        IF v_cited_receipt IS NOT NULL AND v_cited_tool_run IS NULL THEN
            SELECT r.id INTO v_receipt FROM receipts r
             WHERE r.program_id = p AND r.label = v_cited_receipt;
            v_provenance := CASE WHEN v_receipt IS NOT NULL THEN 'receipt' END;
        ELSIF v_cited_tool_run IS NOT NULL AND v_cited_receipt IS NULL THEN
            SELECT t.id INTO v_tool_run FROM tool_runs t
             WHERE t.program_id = p AND t.label = v_cited_tool_run;
            v_provenance := CASE WHEN v_tool_run IS NOT NULL THEN 'tool_run' END;
        END IF;

        SELECT e.id INTO v_subject FROM entities e
         WHERE e.program_id = p AND e.label = v_element ->> 'subject_label';
        v_kind := v_element ->> 'kind';
        SELECT k.allowed_provenance INTO v_allowed
          FROM observation_kinds k WHERE k.id = v_kind;

        IF v_provenance IS NULL THEN
            -- Reachable even though staging checks the same thing: staging ran
            -- against the rows as they were then, and a Receipt can be purged
            -- between the child speaking and the runtime committing.
            v_reason := 'no_provenance';
            v_cited := coalesce(v_cited_receipt, v_cited_tool_run);
        ELSIF v_subject IS NULL THEN
            v_reason := 'no_subject';
            v_cited := v_element ->> 'subject_label';
        ELSIF v_allowed IS NULL THEN
            v_reason := 'unknown_kind';
            v_cited := v_kind;
        ELSIF NOT (v_provenance = ANY (v_allowed)) THEN
            v_reason := 'incompatible_provenance';
            v_cited := v_kind;
        END IF;

        IF v_reason IS NOT NULL THEN
            INSERT INTO proposal_drops
                (proposal_id, program_id, ordinal, element_path, reason, cited)
            VALUES (v.id, p, v_next, v_path, v_reason, v_cited);
            v_next := v_next + 1;
            v_refused := v_refused + 1;
            CONTINUE;
        END IF;

        -- The guards on `observations` get the last word, and catching them is
        -- how the rest of the proposal survives one element they refuse. Named
        -- conditions rather than OTHERS: a deadlock, a serialization failure or
        -- a disk error is not the agent having proposed something ungrounded,
        -- and recording it as one would be this function inventing evidence.
        BEGIN
            INSERT INTO observations
                (program_id, agent_run_id, subject_entity_id, kind, summary,
                 provenance_kind, receipt_id, tool_run_id, metadata)
            VALUES
                (p, v.agent_run_id, v_subject, v_kind,
                 left(coalesce(v_element ->> 'summary', ''), 2000),
                 v_provenance, v_receipt, v_tool_run,
                 jsonb_build_object('proposal', v.label, 'element', v_path))
            RETURNING label INTO v_label;
            v_promoted := v_promoted || v_label;
        EXCEPTION WHEN check_violation OR raise_exception OR not_null_violation
                    OR foreign_key_violation OR unique_violation THEN
            -- `cited` holds the server's sentence rather than a label, because
            -- no label is what was wrong: everything this element cited
            -- resolved, and an invariant of the canonical table refused the row
            -- anyway. The sentence is the only statement of which one.
            INSERT INTO proposal_drops
                (proposal_id, program_id, ordinal, element_path, reason, cited)
            VALUES (v.id, p, v_next, v_path, 'refused_by_invariant',
                    left(SQLERRM, 300));
            v_next := v_next + 1;
            v_refused := v_refused + 1;
        END;
    END LOOP;

    -- `rejected` when nothing survived, and it is a decision rather than a
    -- failure: the proposal is still the record of what the child claimed, and
    -- the drops beside it are still the record of why none of it grounded.
    UPDATE proposals
       SET status = CASE WHEN cardinality(v_promoted) > 0 THEN 'promoted' ELSE 'rejected' END,
           promoted_at = CASE WHEN cardinality(v_promoted) > 0 THEN now() END
     WHERE id = v.id;

    RETURN jsonb_build_object(
        'proposal', v.label,
        'status', CASE WHEN cardinality(v_promoted) > 0 THEN 'promoted' ELSE 'rejected' END,
        'repeated', false,
        'observations', to_jsonb(v_promoted),
        'refused', v_refused);
END $fn$;

REVOKE ALL ON FUNCTION promote_proposal(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION promote_proposal(uuid) TO rk2_runtime;

COMMENT ON FUNCTION promote_proposal(uuid) IS
    'Turns one staged Mission result into canonical Observations, in one '
    'transaction with the Events that record them. Refuses what it cannot '
    'ground into proposal_drops rather than raising, and is idempotent: a '
    'proposal that is no longer staged is reported, not promoted twice.';


-- ---------------------------------------------------------------------------
-- 4. Prose does not close a Task
-- ---------------------------------------------------------------------------
-- The child's claim of completion is `proposals.completion`, which is a word
-- copied out of free text on a staging row. This trigger is the reason that
-- word decides nothing: `done` requires a proposal the runtime promoted, and
-- the only thing that promotes one is section 3 above, which reads canonical
-- rows the child cannot write.
--
-- ENABLE ALWAYS for the reason 018 gives about its own guard: a restore run
-- under `session_replication_role = 'replica'` otherwise skips it, and a Task
-- that closed during a restore would be indistinguishable from one that closed
-- because the work was accepted.

CREATE FUNCTION enforce_task_completion() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    IF NEW.status = 'done' AND OLD.status IS DISTINCT FROM 'done'
       AND NOT EXISTS (SELECT 1 FROM proposals pr
                        WHERE pr.task_id = NEW.id AND pr.status = 'promoted') THEN
        RAISE EXCEPTION
            'task % cannot be closed as done: no proposal of it has been promoted',
            NEW.label
          USING DETAIL = 'an agent''s completion claim is staging data; the runtime '
                         'accepting a structured result is what closes a task',
                ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $fn$;

REVOKE ALL ON FUNCTION enforce_task_completion() FROM PUBLIC;

CREATE TRIGGER tasks_completion_needs_promotion
    BEFORE UPDATE ON tasks
    FOR EACH ROW EXECUTE FUNCTION enforce_task_completion();
ALTER TABLE tasks ENABLE ALWAYS TRIGGER tasks_completion_needs_promotion;


-- ---------------------------------------------------------------------------
-- 5. The end of one attempt
-- ---------------------------------------------------------------------------
-- `sweep_expired_leases` already does most of this, for every expired lease in
-- a Program at once and on a clock. This is the same closing for one run, on
-- purpose rather than on a deadline -- and with the one thing the sweep cannot
-- do, which is close a Task as done, because the sweep runs where no proposal
-- has been promoted by definition.
--
-- The order matters in one place: the Tool runs close before the Agent run.
-- Closing a Tool run is what revokes its capability -- 038's
-- `guard_tool_run_authorization` clears the digest on any update that leaves
-- `running` -- and a run that ended while a capability of its own was still
-- resolvable is the leak this closing exists to prevent.

CREATE FUNCTION finish_task_attempt(p_agent_run uuid, p_stop_reason text DEFAULT 'completed')
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
    -- Raised rather than tolerated, as 023's ranking pass raises it. The row is
    -- read for one comparison, `attempts >= w.max_attempts`, and a missing row
    -- makes that NULL -- which is not an error but a false: the Task would go
    -- back to the queue after every attempt, forever, and nothing would say why.
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

    UPDATE agent_runs SET finished_at = now(), stop_reason = p_stop_reason
     WHERE id = v_run.id AND finished_at IS NULL;
    GET DIAGNOSTICS n_run = ROW_COUNT;

    UPDATE identity_leases SET released_at = now()
     WHERE program_id = p AND holder_agent_run_id = v_run.id AND released_at IS NULL;
    GET DIAGNOSTICS n_lease = ROW_COUNT;

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
        UPDATE tasks SET status = 'done', finished_at = now(),
                         lease_expires_at = NULL, priority = NULL
         WHERE id = v_task.id;
    ELSIF v_task.attempts >= w.max_attempts THEN
        v_status := 'abandoned';
        UPDATE tasks SET status = 'abandoned', abandoned_reason = 'attempts_exhausted',
                         finished_at = now(), lease_expires_at = NULL, priority = NULL
         WHERE id = v_task.id;
    ELSE
        -- Back to the queue with the attempt spent. The attempt is spent
        -- because it happened: `claim_task` counted it, a child ran, and a
        -- runtime that gave it back would loop on a task that fails the same
        -- way every time.
        v_status := 'pending';
        UPDATE tasks SET status = 'pending', claimed_at = NULL,
                         lease_expires_at = NULL, priority = NULL
         WHERE id = v_task.id;
    END IF;

    RETURN jsonb_build_object('agent_run', v_run.label, 'task', v_task.label,
                              'task_status', v_status, 'accepted', v_accepted,
                              'runs_closed', n_run, 'tool_runs_closed', n_tool,
                              'leases_released', n_lease);
END $fn$;

REVOKE ALL ON FUNCTION finish_task_attempt(uuid, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION finish_task_attempt(uuid, text) TO rk2_runtime;

COMMENT ON FUNCTION finish_task_attempt(uuid, text) IS
    'Ends one attempt: Tool runs closed (which revokes their capabilities), '
    'Agent run closed, Identity Leases released, and the Task settled from what '
    'was promoted rather than from what was claimed. Idempotent.';


-- ---------------------------------------------------------------------------
-- 6. The standing check
-- ---------------------------------------------------------------------------
-- Rows rather than shapes, for the five leaks criterion 5 names -- the four an
-- attempt can spring at its end, plus the Agent run left open on a Task that
-- settled without it -- and the two structures the rows depend on. A closing
-- that stopped running would leave the first five empty for exactly as long as
-- nothing had crashed yet.

CREATE FUNCTION check_execution_closure()
RETURNS TABLE (problem text, subject text, detail text)
LANGUAGE sql STABLE AS $fn$
    SELECT 'task_done_without_promotion', t.label,
           'closed as done and no proposal of it is promoted'
      FROM tasks t
     WHERE t.status = 'done'
       AND NOT EXISTS (SELECT 1 FROM proposals pr
                        WHERE pr.task_id = t.id AND pr.status = 'promoted')

  UNION ALL
    SELECT 'live_capability_after_close', tr.label,
           'status=' || tr.status || ' and a capability digest is still installed'
      FROM tool_runs tr
     WHERE tr.status <> 'running' AND tr.egress_token_sha256 IS NOT NULL

  UNION ALL
    SELECT 'open_tool_run_of_closed_agent_run', tr.label,
           'still running inside agent run ' || ar.label || ', which finished'
      FROM tool_runs tr JOIN agent_runs ar ON ar.id = tr.agent_run_id
     WHERE tr.status = 'running' AND ar.finished_at IS NOT NULL

  UNION ALL
    SELECT 'unreleased_lease_of_closed_agent_run', l.identity_entity_id::text,
           'held by agent run ' || ar.label || ', which finished'
      FROM identity_leases l JOIN agent_runs ar ON ar.id = l.holder_agent_run_id
     WHERE l.released_at IS NULL AND ar.finished_at IS NOT NULL

  UNION ALL
    SELECT 'open_agent_run_on_settled_task', ar.label,
           'unfinished on task ' || t.label || ', which is ' || t.status
      FROM agent_runs ar JOIN tasks t ON t.id = ar.task_id
     WHERE ar.finished_at IS NULL AND t.status IN ('done','failed','abandoned')

  UNION ALL
    SELECT 'completion_guard_detached', 'tasks',
           'tasks_completion_needs_promotion is missing or not ENABLE ALWAYS'
     WHERE NOT EXISTS (
        SELECT 1 FROM pg_trigger
         WHERE tgrelid = 'tasks'::regclass
           AND tgname = 'tasks_completion_needs_promotion'
           AND tgenabled = 'A')

  UNION ALL
    SELECT 'promotion_writes_no_event', 'observations',
           'observations is not a row-event table, so a promoted Observation '
           'could commit without the Event that records it'
     WHERE NOT EXISTS (
        SELECT 1 FROM event_table_config
         WHERE table_name = 'observations' AND created_type = 'observation.recorded')
$fn$;

REVOKE ALL ON FUNCTION check_execution_closure() FROM PUBLIC;

INSERT INTO standing_checks(name, query, owner_ticket, note) VALUES
    ('execution_closure', 'SELECT * FROM check_execution_closure()', '20',
     'a finished attempt leaves no live capability, no open Tool run, no open Agent run and no held Lease, and a Task is done only where the runtime promoted a result');

COMMENT ON FUNCTION check_execution_closure() IS
    'The five leaks a Task attempt can spring, as rows, plus the two structures '
    'that keep the first of them empty by construction.';
