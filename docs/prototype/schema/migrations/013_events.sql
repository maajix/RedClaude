-- ---------------------------------------------------------------------------
-- 013_events.sql   (ticket 07; the ticket calls this "012_events.sql",
-- renumbered because ticket 08's migration takes 012 — divergence D1)
-- ---------------------------------------------------------------------------

-- Correction 1: the only exit from `testing` that a crash can take.
INSERT INTO transition_rules
    (machine, from_status, to_status, required_actor_kind, requires_receipt,
     min_supporting_evidence, min_control_evidence)
VALUES ('hypothesis','testing','testable','runtime', false, 0, 0);

-- Correction 2: immutability that does not block the purge cascade.
CREATE FUNCTION reject_mutation_unless_purging() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE'
       AND coalesce(current_setting('app.purging', true), 'off') = 'on' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION '% rows are immutable', TG_TABLE_NAME;
END $$;

DROP TRIGGER observations_immutable          ON observations;
DROP TRIGGER tests_immutable                 ON tests;
DROP TRIGGER hypothesis_transitions_immutable ON hypothesis_transitions;
DROP TRIGGER finding_transitions_immutable   ON finding_transitions;

CREATE TRIGGER observations_immutable BEFORE UPDATE OR DELETE ON observations
    FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_purging();
CREATE TRIGGER tests_immutable BEFORE UPDATE OR DELETE ON tests
    FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_purging();
CREATE TRIGGER hypothesis_transitions_immutable
    BEFORE UPDATE OR DELETE ON hypothesis_transitions
    FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_purging();
CREATE TRIGGER finding_transitions_immutable
    BEFORE UPDATE OR DELETE ON finding_transitions
    FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_purging();

-- Correction 3: the event trigger needs the program without a join.
ALTER TABLE identity_leases
    ADD COLUMN program_id uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE;
ALTER TABLE hypothesis_transitions
    ADD COLUMN program_id uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE;
ALTER TABLE finding_transitions
    ADD COLUMN program_id uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE;
ALTER TABLE test_runs
    ADD COLUMN program_id uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE;

-- ---------------------------------------------------------------------------
-- The catalogue (decisions 6, 15, 16)
-- ---------------------------------------------------------------------------

CREATE TABLE event_types (
    id            text PRIMARY KEY,        -- '<noun>.<past-tense-verb>'
    family        text NOT NULL CHECK (family IN ('row','occurrence')),
    subject_table text,                    -- row events only
    description   text NOT NULL,
    CHECK ((family = 'row') = (subject_table IS NOT NULL))
);

INSERT INTO event_types (id, family, subject_table, description) VALUES
    -- mutable tables: generic pair, the delta carries the meaning
    ('entity.created',          'row','entities',    'attack-surface node discovered'),
    ('entity.updated',          'row','entities',    'attack-surface node changed'),
    ('relationship.created',    'row','relationships','typed edge discovered'),
    ('relationship.updated',    'row','relationships','typed edge changed'),
    ('task.created',            'row','tasks',       'schedulable unit created'),
    ('task.updated',            'row','tasks',       'schedulable unit changed'),
    ('agent_run.created',       'row','agent_runs',  'subagent invoked'),
    ('agent_run.updated',       'row','agent_runs',  'subagent run changed'),
    ('hypothesis.created',      'row','hypotheses',  'hypothesis proposed'),
    ('hypothesis.updated',      'row','hypotheses',  'hypothesis changed (status excluded)'),
    ('finding.created',         'row','findings',    'finding claimed'),
    ('finding.updated',         'row','findings',    'finding changed (status excluded)'),
    ('identity_lease.created',  'row','identity_leases','identity leased'),
    ('identity_lease.updated',  'row','identity_leases','identity lease changed'),
    -- immutable tables: one insert is one occurrence, semantic name
    ('observation.recorded',    'row','observations','immutable fact recorded'),
    ('hypothesis.transitioned', 'row','hypothesis_transitions','hypothesis state transition'),
    ('finding.transitioned',    'row','finding_transitions','finding state transition'),
    ('test.specified',          'row','tests',       'immutable test spec created'),
    ('test_run.recorded',       'row','test_runs',   'test spec executed'),
    -- occurrence events: no row exists to point at
    ('agent.refused',      'occurrence', NULL, 'model declined; category and responsible task in payload (Q19)'),
    ('run.stopped',        'occurrence', NULL, 'graceful operator stop, written before shutdown'),
    ('run.resumed',        'occurrence', NULL, 'reconciliation sweep after any abort, with its counts'),
    ('budget.exhausted',   'occurrence', NULL, 'agent run hit its budget stop condition'),
    ('rate_limit.hit',     'occurrence', NULL, 'subscription rate limit reached'),
    ('scheduler.ranked',   'occurrence', NULL, 'one ranking pass; owed a payload shape by ticket 08'),
    ('decision.requested', 'occurrence', NULL, 'human consultation opened (Q9); table owed by ticket 28'),
    ('decision.answered',  'occurrence', NULL, 'human consultation closed or deadline-aborted');

-- ---------------------------------------------------------------------------
-- The envelope (decisions 2, 4, 5, 8)
-- ---------------------------------------------------------------------------

CREATE TABLE events (
    program_id         uuid   NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    seq                bigint GENERATED ALWAYS AS IDENTITY,
    id                 uuid   NOT NULL DEFAULT uuidv7(),
    type               text   NOT NULL REFERENCES event_types(id),

    -- decision 2: a pair, no FK. Null for occurrence events.
    subject_table      text,
    subject_id         uuid,

    -- decision 5: same vocabulary as hypothesis_transitions.actor_kind
    actor_kind         text NOT NULL CHECK (actor_kind IN ('llm','runtime','human')),
    agent_run_id       uuid REFERENCES agent_runs(id) ON DELETE SET NULL,
    task_id            uuid REFERENCES tasks(id) ON DELETE CASCADE,
    caused_by_event_id uuid,
    trace_id           text,                -- joins the OTel span (Q18)

    -- decision 1: pointer + changed columns. {"after":{…}} on insert,
    -- {"before":{…},"after":{…}} on update. Never a full row image.
    payload            jsonb NOT NULL DEFAULT '{}'::jsonb,

    -- decision 4: seq is APPEND order, not commit order. A tailer must re-scan a
    -- lookback window rather than trust a high-water mark.
    xact_id            xid8        NOT NULL DEFAULT pg_current_xact_id(),
    tx_at              timestamptz NOT NULL DEFAULT now(),             -- groups a transaction
    recorded_at        timestamptz NOT NULL DEFAULT clock_timestamp(), -- orders within one

    -- decision 8: program_id in the PK keeps LIST partitioning reachable
    PRIMARY KEY (program_id, seq),
    UNIQUE (program_id, id),
    -- causation cannot cross a program boundary; MATCH SIMPLE, so a null
    -- caused_by_event_id simply does not constrain
    FOREIGN KEY (program_id, caused_by_event_id) REFERENCES events (program_id, id)
);

CREATE INDEX events_subject_idx  ON events (subject_table, subject_id);
CREATE INDEX events_task_idx     ON events (task_id) WHERE task_id IS NOT NULL;
CREATE INDEX events_type_idx     ON events (program_id, type, seq);
CREATE INDEX events_tx_at_brin   ON events USING brin (tx_at);

CREATE FUNCTION enforce_event_envelope() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE t event_types%ROWTYPE;
BEGIN
    SELECT * INTO t FROM event_types WHERE id = NEW.type;
    IF t.family = 'row' THEN
        IF NEW.subject_id IS NULL OR NEW.subject_table IS DISTINCT FROM t.subject_table THEN
            RAISE EXCEPTION 'event type % is a row event on %, got subject (%, %)',
                NEW.type, t.subject_table, NEW.subject_table, NEW.subject_id;
        END IF;
    ELSIF NEW.subject_table IS NOT NULL OR NEW.subject_id IS NOT NULL THEN
        RAISE EXCEPTION 'event type % is an occurrence event and must not carry a subject',
            NEW.type;
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER events_envelope_guard BEFORE INSERT ON events
    FOR EACH ROW EXECUTE FUNCTION enforce_event_envelope();

CREATE TRIGGER events_immutable BEFORE UPDATE OR DELETE ON events
    FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_purging();

-- ---------------------------------------------------------------------------
-- Emission policy as rows (decisions 10, 11, 17)
-- ---------------------------------------------------------------------------

-- `updated_type IS NULL` declares the table immutable: an UPDATE that reaches
-- the trigger is a bug, and raises.
--
-- ignored_columns  -> not compared, not copied. If every changed column is
--                     ignored, NO event is written.
-- redacted_columns -> compared and reported as changed, value replaced by
--                     "[redacted]". Secrets, and every bulk JSONB column.
CREATE TABLE event_table_config (
    table_name       text PRIMARY KEY,
    created_type     text NOT NULL REFERENCES event_types(id),
    updated_type     text REFERENCES event_types(id),
    ignored_columns  text[] NOT NULL DEFAULT '{}',
    redacted_columns text[] NOT NULL DEFAULT '{}'
);

INSERT INTO event_table_config
    (table_name, created_type, updated_type, ignored_columns, redacted_columns) VALUES
    ('entities', 'entity.created', 'entity.updated',
        '{last_seen_at}', '{metadata}'),
    ('relationships', 'relationship.created', 'relationship.updated',
        '{last_seen_at}', '{metadata}'),
    -- the four ranking columns are scheduler output recomputed every pass, not
    -- epistemic state; ticket 08 wants one scheduler.ranked event, not N of these
    ('tasks', 'task.created', 'task.updated',
        '{priority,novelty,estimated_cost,confidence_of_execution}', '{}'),
    ('agent_runs', 'agent_run.created', 'agent_run.updated',
        '{}', '{mission_packet,result}'),
    -- status/status_changed_at excluded: the transition row is the real event
    ('hypotheses', 'hypothesis.created', 'hypothesis.updated',
        '{status,status_changed_at}', '{}'),
    ('findings', 'finding.created', 'finding.updated',
        '{status,status_changed_at}', '{}'),
    ('identity_leases', 'identity_lease.created', 'identity_lease.updated',
        '{}', '{}'),
    ('observations', 'observation.recorded', NULL, '{}', '{metadata}'),
    ('hypothesis_transitions', 'hypothesis.transitioned', NULL, '{}', '{}'),
    ('finding_transitions', 'finding.transitioned', NULL, '{}', '{}'),
    ('tests', 'test.specified', NULL, '{}', '{spec}'),
    ('test_runs', 'test_run.recorded', NULL, '{}', '{assertion_results}');

-- ---------------------------------------------------------------------------
-- The emitter (decision 9)
-- ---------------------------------------------------------------------------

CREATE FUNCTION emit_event() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    cfg      event_table_config%ROWTYPE;
    new_j    jsonb := to_jsonb(NEW);
    old_j    jsonb;
    before_j jsonb := '{}'::jsonb;
    after_j  jsonb := '{}'::jsonb;
    k        text;
    changed  boolean := false;
    v_actor  text;
    v_type   text;
BEGIN
    SELECT * INTO cfg FROM event_table_config WHERE table_name = TG_TABLE_NAME;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'emit_event is attached to % with no event_table_config row',
            TG_TABLE_NAME;
    END IF;

    -- decision 9: the runtime's session helper is the only way to write. Not
    -- setting the actor is an error, never a silently unattributed event.
    v_actor := nullif(current_setting('app.actor_kind', true), '');
    IF v_actor IS NULL THEN
        RAISE EXCEPTION
            'app.actor_kind is unset: every write must go through the runtime session helper';
    END IF;

    IF TG_OP = 'INSERT' THEN
        v_type  := cfg.created_type;
        after_j := new_j;
        FOREACH k IN ARRAY cfg.redacted_columns LOOP
            IF after_j ? k THEN
                after_j := jsonb_set(after_j, ARRAY[k], '"[redacted]"'::jsonb);
            END IF;
        END LOOP;
        FOREACH k IN ARRAY cfg.ignored_columns LOOP
            after_j := after_j - k;
        END LOOP;
        changed := true;
    ELSE
        v_type := cfg.updated_type;
        IF v_type IS NULL THEN
            RAISE EXCEPTION '% is declared immutable in event_table_config', TG_TABLE_NAME;
        END IF;
        old_j := to_jsonb(OLD);
        FOR k IN SELECT jsonb_object_keys(new_j) LOOP
            CONTINUE WHEN k = ANY (cfg.ignored_columns);
            CONTINUE WHEN new_j -> k IS NOT DISTINCT FROM old_j -> k;
            changed := true;
            IF k = ANY (cfg.redacted_columns) THEN
                before_j := before_j || jsonb_build_object(k, '[redacted]');
                after_j  := after_j  || jsonb_build_object(k, '[redacted]');
            ELSE
                before_j := before_j || jsonb_build_object(k, old_j -> k);
                after_j  := after_j  || jsonb_build_object(k, new_j -> k);
            END IF;
        END LOOP;
    END IF;

    -- decision 10: every changed column was ignored, so nothing happened that
    -- anyone asking "why did it think this" would care about.
    IF NOT changed THEN
        RETURN NEW;
    END IF;

    INSERT INTO events (
        program_id, type, subject_table, subject_id,
        actor_kind, agent_run_id, task_id, caused_by_event_id, trace_id, payload)
    VALUES (
        (new_j ->> 'program_id')::uuid,     -- correction 3 makes this total
        v_type, TG_TABLE_NAME, (new_j ->> 'id')::uuid,
        v_actor,
        nullif(current_setting('app.agent_run_id',       true), '')::uuid,
        nullif(current_setting('app.task_id',            true), '')::uuid,
        nullif(current_setting('app.caused_by_event_id', true), '')::uuid,
        nullif(current_setting('app.trace_id',           true), ''),
        CASE WHEN TG_OP = 'INSERT'
             THEN jsonb_build_object('after', after_j)
             ELSE jsonb_build_object('before', before_j, 'after', after_j)
        END);

    RETURN NEW;
END $$;

-- AFTER, so an event exists only if the row write itself succeeded — still the
-- same transaction, which is the ADR 0001 invariant.
CREATE FUNCTION attach_event_triggers() RETURNS void LANGUAGE plpgsql AS $$
DECLARE c event_table_config%ROWTYPE;
BEGIN
    FOR c IN SELECT * FROM event_table_config LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS %I ON %I',
                       c.table_name || '_emit_event', c.table_name);
        EXECUTE format('CREATE TRIGGER %I AFTER INSERT %s ON %I
                        FOR EACH ROW EXECUTE FUNCTION emit_event()',
                       c.table_name || '_emit_event',
                       CASE WHEN c.updated_type IS NULL THEN '' ELSE 'OR UPDATE' END,
                       c.table_name);
    END LOOP;
END $$;

SELECT attach_event_triggers();   -- re-run by every migration that touches the config

-- ---------------------------------------------------------------------------
-- Integrity (decision 12)
-- ---------------------------------------------------------------------------

-- One query, two callers: CI after a scripted mini-hunt over the ticket-05
-- fixture pair, and the runtime as a periodic check plus at program retire.
CREATE FUNCTION check_event_log_integrity(p_program uuid DEFAULT NULL)
RETURNS TABLE (problem text, detail text, count bigint)
LANGUAGE plpgsql AS $$
DECLARE c event_table_config%ROWTYPE;
BEGIN
    -- (a) the failure mode that actually happens: a migration adds a table or
    -- rewrites one and its trigger is silently gone
    RETURN QUERY
    SELECT 'config_row_without_trigger', etc.table_name, 1::bigint
      FROM event_table_config etc
     WHERE NOT EXISTS (
           SELECT 1 FROM pg_trigger t
             JOIN pg_class r ON r.oid = t.tgrelid
            WHERE r.relname = etc.table_name
              AND t.tgname  = etc.table_name || '_emit_event'
              AND NOT t.tgisinternal);

    FOR c IN SELECT * FROM event_table_config LOOP
        -- (b) a row with no creation event
        RETURN QUERY EXECUTE format($q$
            SELECT 'row_without_event', %L, count(*)::bigint
              FROM %I r
             WHERE (%L::uuid IS NULL OR r.program_id = %L::uuid)
               AND NOT EXISTS (SELECT 1 FROM events e
                                WHERE e.subject_table = %L
                                  AND e.subject_id = r.id
                                  AND e.type = %L)
            HAVING count(*) > 0 $q$,
            c.table_name, c.table_name, p_program, p_program,
            c.table_name, c.created_type);

        -- (c) an event pointing at nothing (no FK enforces this, by decision 2)
        RETURN QUERY EXECUTE format($q$
            SELECT 'event_without_row', %L, count(*)::bigint
              FROM events e
             WHERE e.subject_table = %L
               AND (%L::uuid IS NULL OR e.program_id = %L::uuid)
               AND NOT EXISTS (SELECT 1 FROM %I r WHERE r.id = e.subject_id)
            HAVING count(*) > 0 $q$,
            c.table_name, c.table_name, p_program, p_program, c.table_name);
    END LOOP;
END $$;

-- ---------------------------------------------------------------------------
-- Resume (decisions 7, 16)
-- ---------------------------------------------------------------------------

-- An abort is never observed as it happens; it is inferred here, on next start,
-- from rows left in flight. Returns the counts the caller puts in run.resumed.
CREATE FUNCTION resume_program(p_program uuid) RETURNS jsonb
LANGUAGE plpgsql AS $$
DECLARE
    n_tasks  bigint;
    n_runs   bigint;
    n_leases bigint;
    n_hyp    bigint;
BEGIN
    PERFORM set_config('app.actor_kind', 'runtime', true);

    -- Q29: the ranking is recomputed from current rows, never continued.
    UPDATE tasks SET status = 'pending', claimed_at = NULL, priority = NULL
     WHERE program_id = p_program AND status IN ('claimed','running');
    GET DIAGNOSTICS n_tasks = ROW_COUNT;

    -- a session is not replayed, it is recompiled: the raw result dies unpromoted
    UPDATE agent_runs
       SET finished_at = now(), stop_reason = 'aborted', result = NULL
     WHERE program_id = p_program AND finished_at IS NULL;
    GET DIAGNOSTICS n_runs = ROW_COUNT;

    UPDATE identity_leases SET released_at = now()
     WHERE program_id = p_program AND released_at IS NULL;
    GET DIAGNOSTICS n_leases = ROW_COUNT;

    -- correction 1 is what makes this legal
    INSERT INTO hypothesis_transitions
        (program_id, hypothesis_id, from_status, to_status, actor_kind, rationale)
    SELECT p_program, h.id, 'testing', 'testable', 'runtime',
           'runtime abort: test did not complete'
      FROM hypotheses h
     WHERE h.program_id = p_program AND h.status = 'testing';
    GET DIAGNOSTICS n_hyp = ROW_COUNT;

    RETURN jsonb_build_object('tasks_unclaimed', n_tasks,
                              'agent_runs_aborted', n_runs,
                              'leases_released', n_leases,
                              'hypotheses_returned_to_testable', n_hyp);
END $$;
