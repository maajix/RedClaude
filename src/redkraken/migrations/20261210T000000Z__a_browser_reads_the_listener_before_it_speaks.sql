-- Ticket 99, the five browser additions left after the Contract was built.
--
-- A probe owns the complete digest-visible shape of its answer. Client state
-- is read through six named CDP paths rather than through owner JavaScript, and
-- cookie values have no output column. A fragment is admitted because it never
-- participates in scope classification. The one fabricated page event carries
-- a migration-owned body and is only admitted immediately after the same plan
-- inventories message listeners. The active fetch oracle is deliberately not
-- added; ADR 0007 records that decision.


-- ---------------------------------------------------------------------------
-- 1. The result shape belongs to the resolved step
-- ---------------------------------------------------------------------------

ALTER TABLE browser_probes ADD COLUMN outcome_keys text[];

UPDATE browser_probes SET outcome_keys = '{verdict}';
UPDATE browser_probes
   SET outcome_keys = '{verdict,node_count,marker_in_text}'
 WHERE probe = 'markup_injection';

ALTER TABLE browser_probes ALTER COLUMN outcome_keys SET NOT NULL;
ALTER TABLE browser_probes ADD CONSTRAINT browser_probes_outcome_keys_ck
    CHECK (cardinality(outcome_keys) BETWEEN 1 AND 8
           AND rk2_lowercase_words(outcome_keys)
           AND 'verdict' = ANY (outcome_keys));

COMMENT ON COLUMN browser_probes.outcome_keys IS
    'The complete digest-visible shape of this probe''s JSON answer. Verdict '
    'is mandatory, every other field remains bounded by '
    'rk2_browser_outcome_word, and the full JSON is still a probe Artifact.';

ALTER TABLE browser_steps ADD COLUMN outcome_keys text[];

UPDATE browser_steps s
   SET outcome_keys = CASE
       WHEN s.action = 'probe' THEN
           (SELECT p.outcome_keys FROM browser_probes p
             WHERE p.probe = s.arguments ->> 'probe')
       ELSE (SELECT a.outcome_keys FROM browser_actions a
              WHERE a.action = s.action)
   END;

ALTER TABLE browser_steps ALTER COLUMN outcome_keys SET NOT NULL;
ALTER TABLE browser_steps ADD CONSTRAINT browser_steps_outcome_keys_ck
    CHECK (cardinality(outcome_keys) BETWEEN 1 AND 8
           AND rk2_lowercase_words(outcome_keys));

COMMENT ON COLUMN browser_steps.outcome_keys IS
    'The outcome schema resolved when this plan opened. Frozen on the step so '
    'a later registry migration cannot change an old run''s result digest.';

INSERT INTO state_read_surface (table_name, column_name, added_by) VALUES
    ('browser_steps', 'outcome_keys', '99');


-- ---------------------------------------------------------------------------
-- 2. Passive client-state reads and one registry-owned message
-- ---------------------------------------------------------------------------

INSERT INTO browser_argument_kinds
    (value_kind, pattern, max_length, description) VALUES
    ('client_state_kind',
     '^(local_storage|session_storage|indexeddb_names|cookies|service_workers|message_listeners)$',
     32,
     'one of the six passive client-state inventories the browser registry owns'),
    ('message', '^[a-z][a-z0-9_]{0,31}$', 32,
     'the name of a registry-owned same-origin message body');

CREATE TABLE browser_client_state_kinds (
    kind        text PRIMARY KEY
        CHECK (kind ~ '^[a-z][a-z0-9_]{0,31}$'),
    description text NOT NULL
);

INSERT INTO browser_client_state_kinds (kind, description) VALUES
    ('local_storage',    'the current origin localStorage key/value entries'),
    ('session_storage',  'the current origin sessionStorage key/value entries'),
    ('indexeddb_names',  'the current origin IndexedDB database names'),
    ('cookies',          'cookie attributes with values removed before the Artifact exists'),
    ('service_workers',  'service worker registrations and versions visible to this page'),
    ('message_listeners','message listeners registered on the current window');

CREATE TABLE browser_messages (
    message     text PRIMARY KEY
        CHECK (message ~ '^[a-z][a-z0-9_]{0,31}$'),
    body        jsonb NOT NULL
        CHECK (jsonb_typeof(body) IN ('object','string')
               AND octet_length(body::text) BETWEEN 1 AND 512),
    description text NOT NULL
);

INSERT INTO browser_messages (message, body, description) VALUES
    ('listener_inventory_probe',
     '{"redkraken":"listener_inventory_probe"}'::jsonb,
     'a harmless body for asking whether an inventoried same-origin message listener reacts');

INSERT INTO browser_actions
    (action, reaches_network, submits, outcome_keys, description) VALUES
    ('read_client_state', false, false, '{entries}',
     'store one passive registry-named client-state inventory as a JSON Artifact'),
    ('send_message', true, true, '{matched}',
     'post one registry-owned body to the current window immediately after listener inventory');

INSERT INTO browser_action_arguments
    (action, name, value_kind, required, pattern, description) VALUES
    ('read_client_state', 'kind', 'client_state_kind', true, NULL,
     'which of the six passive inventories to store'),
    ('send_message', 'message', 'message', true, NULL,
     'which migration-owned body to post to the current same-origin window');

INSERT INTO program_global_tables (table_name, reason) VALUES
    ('browser_client_state_kinds',
     'the closed passive client-state inventory; a Program may not add a new read path'),
    ('browser_messages',
     'the bodies a browser may fabricate as page events; a Program may not author one');

INSERT INTO event_table_exempt
    (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('browser_client_state_kinds', 'reference',
     'the client-state kind registry, changed only by migration', '99'),
    ('browser_messages', 'reference',
     'the same-origin message-body registry, changed only by migration', '99');

GRANT SELECT ON browser_client_state_kinds, browser_messages TO rk2_runtime;

-- And the same registry 066's standing check reads: a table privilege the
-- runtime holds that no surface row explains is refused, because a GRANT is the
-- one part of a migration that widens what a compromised runtime connection can
-- reach and is written twice on purpose.
INSERT INTO runtime_table_surface (table_name, privilege, added_by) VALUES
    ('browser_client_state_kinds', 'SELECT', '99'),
    ('browser_messages', 'SELECT', '99');


-- A fragment is browser-local. The scope compiler and Receipt lookup already
-- classify the scheme, host, port and path while deliberately discarding it.
UPDATE browser_argument_kinds
   SET pattern =
       '^https?://[A-Za-z0-9][A-Za-z0-9.-]{0,252}(:[0-9]{1,5})?(/[A-Za-z0-9._~%!$&()*+,;=:@/-]*)?(\?[A-Za-z0-9._~%!$&()*+,;=:@/?-]*)?(#[A-Za-z0-9._~%!$&()*+,;=:@/?-]*)?$',
       description =
       'an absolute http or https URL, optionally with a fragment and without an address literal'
 WHERE value_kind = 'url';


-- ---------------------------------------------------------------------------
-- 3. One JSON Artifact for each sanctioned client-state read
-- ---------------------------------------------------------------------------

ALTER TABLE tool_run_artifacts DROP CONSTRAINT tool_run_artifacts_stream_check;
ALTER TABLE tool_run_artifacts ADD CONSTRAINT tool_run_artifacts_stream_check
    CHECK (stream IN ('stdout','stderr','output',
                      'dom','screenshot','console','probe','client_state'));

ALTER TABLE tool_run_artifacts DROP CONSTRAINT tool_run_artifacts_named_output_ck;
ALTER TABLE tool_run_artifacts ADD CONSTRAINT tool_run_artifacts_named_output_ck
    CHECK ((stream IN ('output','probe','client_state')) = (output_name IS NOT NULL));

ALTER TABLE tool_run_artifacts DROP CONSTRAINT tool_run_artifacts_browser_step_ck;
ALTER TABLE tool_run_artifacts ADD CONSTRAINT tool_run_artifacts_browser_step_ck
    CHECK ((stream IN ('dom','screenshot','probe','client_state')) =
           (browser_step_ordinal IS NOT NULL));

COMMENT ON COLUMN tool_run_artifacts.stream IS
    'Which stream of the producing run these bytes are. stdout, stderr and a '
    'declared output belong to an offline tool; dom, screenshot, probe and '
    'client_state belong to one browser step and console to the mission. A '
    'client_state Artifact is named by its closed kind; cookie values have '
    'already been removed before its bytes reach this table.';

CREATE OR REPLACE FUNCTION tool_run_artifact_is_this_runs_output() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE
    v_run     tool_runs%ROWTYPE;
    v_browser boolean;
    v_size    bigint;
BEGIN
    SELECT * INTO v_run FROM tool_runs
     WHERE id = NEW.tool_run_id AND program_id = NEW.program_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'tool run % is not a Tool run of this Program',
            NEW.tool_run_id USING ERRCODE = '23503';
    END IF;
    v_browser := EXISTS (SELECT 1 FROM browser_runs b WHERE b.tool_run_id = v_run.id);
    IF v_run.offline_tool IS NULL AND NOT v_browser THEN
        RAISE EXCEPTION 'tool run % is neither an offline Tool run nor a browser mission',
            v_run.label USING ERRCODE = '23503';
    END IF;
    IF v_browser <> (NEW.stream IN
                     ('dom','screenshot','console','probe','client_state')) THEN
        RAISE EXCEPTION 'the % stream does not belong to this kind of run', NEW.stream
            USING ERRCODE = '23514';
    END IF;
    IF v_run.status <> 'running' THEN
        RAISE EXCEPTION 'tool run % has already been closed as %',
            v_run.label, v_run.status USING ERRCODE = '23514';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM artifact_references r
                    WHERE r.program_id = NEW.program_id AND r.sha256 = NEW.sha256) THEN
        RAISE EXCEPTION 'artifact % is not held by this Program', NEW.sha256
            USING ERRCODE = '42704',
                  HINT = 'store the bytes and reference them before recording them as output';
    END IF;
    SELECT byte_size INTO v_size FROM artifacts WHERE sha256 = NEW.sha256;
    IF NEW.produced_bytes < v_size THEN
        RAISE EXCEPTION 'a stream of % byte(s) cannot have stored % byte(s)',
            NEW.produced_bytes, v_size USING ERRCODE = '23514';
    END IF;
    IF NEW.truncated <> (NEW.produced_bytes > v_size) THEN
        RAISE EXCEPTION 'the truncation flag disagrees with the stored size'
            USING ERRCODE = '23514',
                  HINT = 'truncated is produced_bytes > the stored artifact size, and nothing else';
    END IF;
    IF NEW.stream = 'output'
       AND NOT EXISTS (SELECT 1 FROM offline_tool_outputs o
                        WHERE o.tool = v_run.offline_tool AND o.name = NEW.output_name) THEN
        RAISE EXCEPTION '% declares no output named %', v_run.offline_tool, NEW.output_name
            USING ERRCODE = '42704';
    END IF;
    IF NEW.stream = 'probe'
       AND NOT EXISTS (SELECT 1 FROM browser_steps s
                        WHERE s.tool_run_id = NEW.tool_run_id
                          AND s.ordinal = NEW.browser_step_ordinal
                          AND s.action = 'probe'
                          AND s.arguments ->> 'probe' = NEW.output_name) THEN
        RAISE EXCEPTION 'step % of this mission does not run the probe %',
            NEW.browser_step_ordinal, NEW.output_name USING ERRCODE = '42704';
    END IF;
    IF NEW.stream = 'client_state'
       AND NOT EXISTS (SELECT 1 FROM browser_steps s
                        WHERE s.tool_run_id = NEW.tool_run_id
                          AND s.ordinal = NEW.browser_step_ordinal
                          AND s.action = 'read_client_state'
                          AND s.arguments ->> 'kind' = NEW.output_name) THEN
        RAISE EXCEPTION 'step % of this mission does not read client state %',
            NEW.browser_step_ordinal, NEW.output_name USING ERRCODE = '42704';
    END IF;
    RETURN NEW;
END $fn$;


-- ---------------------------------------------------------------------------
-- 4. Compile the resolved registries into the plan before anything starts
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION open_browser_run(
        p_agent_run_id  uuid,
        p_steps         jsonb,
        p_identity_slot text DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p          uuid := rk2_program_required();
    v_run      agent_runs%ROWTYPE;
    v_ceil     browser_ceilings%ROWTYPE := rk2_browser_ceilings();
    v_step     jsonb;
    v_action   browser_actions%ROWTYPE;
    v_arg      browser_action_arguments%ROWTYPE;
    v_kind     browser_argument_kinds%ROWTYPE;
    v_probe    browser_probes%ROWTYPE;
    v_message  browser_messages%ROWTYPE;
    v_name     text;
    v_value    text;
    v_ordinal  integer := 0;
    v_methods  text[] := ARRAY['GET','HEAD','OPTIONS'];
    v_lines    text[] := '{}';
    v_plan     jsonb := '[]'::jsonb;
    v_args     jsonb;
    v_class    text;
    v_url      text[];
    v_id       uuid;
    v_label    text;
    v_outcomes text[];
    v_previous_action text;
    v_previous_kind   text;
BEGIN
    IF jsonb_typeof(p_steps) <> 'array' THEN
        RAISE EXCEPTION 'the plan of a browser mission is an array of steps'
            USING ERRCODE = '22023';
    END IF;
    IF jsonb_array_length(p_steps) = 0
       OR jsonb_array_length(p_steps) > v_ceil.max_steps THEN
        RAISE EXCEPTION 'a browser mission has between 1 and % steps', v_ceil.max_steps
            USING ERRCODE = '22023';
    END IF;

    SELECT * INTO v_run FROM agent_runs
     WHERE id = p_agent_run_id AND program_id = p;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'agent run % is not a run of this Program', p_agent_run_id
            USING ERRCODE = '23503';
    END IF;
    IF v_run.finished_at IS NOT NULL THEN
        RAISE EXCEPTION 'agent run % has already ended', v_run.label
            USING ERRCODE = '23514';
    END IF;
    IF EXISTS (SELECT 1 FROM program_halts h
                WHERE h.program_id = p AND h.status = 'halted') THEN
        RAISE EXCEPTION 'the Program is Halted and may not start new work'
            USING ERRCODE = '42501', HINT = 'rk resume lifts the Halt';
    END IF;
    IF p_identity_slot IS NOT NULL THEN
        IF NOT EXISTS (
            SELECT 1 FROM identities i
              JOIN identity_leases l
                ON l.identity_entity_id = i.entity_id
               AND l.program_id = i.program_id
               AND l.holder_agent_run_id = v_run.id
               AND l.released_at IS NULL
               AND l.expires_at > clock_timestamp()
             WHERE i.program_id = p
               AND i.slot_name = p_identity_slot
               AND i.invalidated_at IS NULL) THEN
            RAISE EXCEPTION 'Identity lease refused' USING ERRCODE = '23514';
        END IF;
    END IF;

    v_lines := array_append(v_lines, 'identity=' || coalesce(p_identity_slot, '-'));

    FOR v_step IN SELECT * FROM jsonb_array_elements(p_steps) LOOP
        v_ordinal := v_ordinal + 1;
        v_probe := NULL;
        v_message := NULL;
        IF jsonb_typeof(v_step) <> 'object' THEN
            RAISE EXCEPTION 'step % is not an object', v_ordinal USING ERRCODE = '22023';
        END IF;
        SELECT * INTO v_action FROM browser_actions
         WHERE action = v_step ->> 'action';
        IF NOT FOUND THEN
            RAISE EXCEPTION 'step % names no action this browser performs: %',
                v_ordinal, coalesce(v_step ->> 'action', '<none>')
                USING ERRCODE = '42704';
        END IF;

        v_args := coalesce(v_step -> 'arguments', '{}'::jsonb);
        IF jsonb_typeof(v_args) <> 'object' THEN
            RAISE EXCEPTION 'the arguments of step % are an object', v_ordinal
                USING ERRCODE = '22023';
        END IF;
        FOR v_name IN SELECT jsonb_object_keys(v_args) LOOP
            IF NOT EXISTS (SELECT 1 FROM browser_action_arguments a
                            WHERE a.action = v_action.action AND a.name = v_name) THEN
                RAISE EXCEPTION '% takes no argument named %', v_action.action, v_name
                    USING ERRCODE = '22023';
            END IF;
        END LOOP;

        FOR v_arg IN
            SELECT * FROM browser_action_arguments
             WHERE action = v_action.action ORDER BY name
        LOOP
            v_value := v_args ->> v_arg.name;
            IF v_value IS NULL THEN
                IF v_arg.required THEN
                    RAISE EXCEPTION 'step % (%) requires the argument %',
                        v_ordinal, v_action.action, v_arg.name USING ERRCODE = '22023';
                END IF;
                CONTINUE;
            END IF;
            IF jsonb_typeof(v_args -> v_arg.name) <> 'string' THEN
                RAISE EXCEPTION 'the argument % of step % is given as text',
                    v_arg.name, v_ordinal USING ERRCODE = '22023';
            END IF;
            SELECT * INTO v_kind FROM browser_argument_kinds
             WHERE value_kind = v_arg.value_kind;
            IF length(v_value) > v_kind.max_length THEN
                RAISE EXCEPTION 'the argument % of step % is longer than a % may be',
                    v_arg.name, v_ordinal, v_arg.value_kind USING ERRCODE = '22023';
            END IF;
            IF v_value !~ v_kind.pattern THEN
                RAISE EXCEPTION 'the argument % of step % is not a well formed %',
                    v_arg.name, v_ordinal, v_arg.value_kind USING ERRCODE = '22023';
            END IF;
            IF v_arg.pattern IS NOT NULL AND v_value !~ v_arg.pattern THEN
                RAISE EXCEPTION 'the argument % of step % does not match what % accepts there',
                    v_arg.name, v_ordinal, v_action.action USING ERRCODE = '22023';
            END IF;

            IF v_arg.value_kind = 'probe' THEN
                SELECT * INTO v_probe FROM browser_probes WHERE probe = v_value;
                IF NOT FOUND THEN
                    RAISE EXCEPTION 'no probe named %', v_value USING ERRCODE = '42704';
                END IF;
                IF v_arg.name = 'probe' AND v_action.action = 'inject'
                   AND v_probe.payload IS NULL THEN
                    RAISE EXCEPTION 'the probe % plants nothing and cannot be injected', v_value
                        USING ERRCODE = '22023';
                END IF;
            ELSIF v_arg.value_kind = 'client_state_kind' THEN
                IF NOT EXISTS (SELECT 1 FROM browser_client_state_kinds c
                                WHERE c.kind = v_value) THEN
                    RAISE EXCEPTION 'no client-state kind named %', v_value
                        USING ERRCODE = '42704';
                END IF;
            ELSIF v_arg.value_kind = 'message' THEN
                SELECT * INTO v_message FROM browser_messages WHERE message = v_value;
                IF NOT FOUND THEN
                    RAISE EXCEPTION 'no browser message named %', v_value
                        USING ERRCODE = '42704';
                END IF;
            END IF;

            IF v_arg.value_kind = 'url' THEN
                v_url := regexp_match(v_value,
                    '^(https?)://([^/:?#]+)(?::([0-9]+))?([^?#]*)');
                SELECT s.scope_class INTO v_class
                  FROM programs pr
                  CROSS JOIN LATERAL scope_class_of(
                        pr.id, pr.scope_version, lower(v_url[2]),
                        coalesce(v_url[3]::integer,
                                 CASE lower(v_url[1]) WHEN 'https' THEN 443 ELSE 80 END),
                        coalesce(nullif(v_url[4], ''), '/'),
                        coalesce(nullif(v_url[4], ''), '/'),
                        lower(v_url[1]), 'request') s
                 WHERE pr.id = p;
                IF coalesce(v_class, 'denied') NOT IN ('target', 'egress_support') THEN
                    RAISE EXCEPTION 'step % navigates outside the current scope', v_ordinal
                        USING ERRCODE = '42501',
                              HINT = 'the door would refuse it; the mission is refused instead';
                END IF;
            END IF;
        END LOOP;

        IF v_action.action = 'send_message'
           AND (v_previous_action IS DISTINCT FROM 'read_client_state'
                OR v_previous_kind IS DISTINCT FROM 'message_listeners') THEN
            RAISE EXCEPTION 'send_message immediately follows a message_listeners inventory'
                USING ERRCODE = '23514',
                      HINT = 'read client state kind message_listeners in the preceding step';
        END IF;

        IF v_action.submits AND NOT ('POST' = ANY (v_methods)) THEN
            v_methods := array_append(v_methods, 'POST');
        END IF;
        v_lines := array_append(v_lines,
            rk2_browser_digest_line(v_ordinal, v_action.action, v_args,
                                    ARRAY(SELECT jsonb_object_keys(v_args))));
        v_outcomes := CASE WHEN v_action.action = 'probe'
                           THEN v_probe.outcome_keys
                           ELSE v_action.outcome_keys END;
        v_plan := v_plan || jsonb_build_object(
            'ordinal', v_ordinal,
            'action', v_action.action,
            'arguments', v_args,
            'outcome_keys', to_jsonb(v_outcomes),
            'javascript', CASE WHEN v_action.action = 'probe'
                               THEN v_probe.javascript END,
            'payload', CASE WHEN v_action.action = 'inject'
                            THEN v_probe.payload END,
            'verdicts', CASE WHEN v_action.action = 'probe'
                             THEN to_jsonb(v_probe.verdicts) END,
            'message_body', CASE WHEN v_action.action = 'send_message'
                                 THEN v_message.body END);
        v_previous_action := v_action.action;
        v_previous_kind := CASE WHEN v_action.action = 'read_client_state'
                                THEN v_args ->> 'kind' END;
    END LOOP;

    INSERT INTO tool_runs
        (program_id, agent_run_id, task_id, tool, args, status, transport)
    VALUES
        (p, v_run.id, v_run.task_id, rk2_browser_tool(),
         jsonb_build_object('identity_slot', p_identity_slot,
                            'methods', to_jsonb(v_methods),
                            'steps', jsonb_array_length(p_steps)),
         'running', 'runtime')
    RETURNING id, label INTO v_id, v_label;

    INSERT INTO browser_runs (tool_run_id, program_id, plan_sha256)
    VALUES (v_id, p,
            encode(digest(array_to_string(v_lines, E'\n'), 'sha256'), 'hex'));

    INSERT INTO browser_steps
        (tool_run_id, ordinal, program_id, action, arguments, outcome_keys)
    SELECT v_id, (s ->> 'ordinal')::integer, p, s ->> 'action',
           s -> 'arguments', ARRAY(SELECT jsonb_array_elements_text(s -> 'outcome_keys'))
      FROM jsonb_array_elements(v_plan) AS s;

    RETURN jsonb_build_object(
        'tool_run_id', v_id,
        'tool_run', v_label,
        'plan_sha256', (SELECT b.plan_sha256 FROM browser_runs b WHERE b.tool_run_id = v_id),
        'identity_slot', p_identity_slot,
        'methods', to_jsonb(v_methods),
        'timeout_seconds', v_ceil.timeout_seconds,
        'step_timeout_ms', v_ceil.step_timeout_ms,
        'memory_mb', v_ceil.memory_mb,
        'cpu_quota', v_ceil.cpu_quota,
        'pids_limit', v_ceil.pids_limit,
        'max_artifact_bytes', v_ceil.max_artifact_bytes,
        'viewport_width', v_ceil.viewport_width,
        'viewport_height', v_ceil.viewport_height,
        'steps', v_plan);
END $fn$;


-- ---------------------------------------------------------------------------
-- 5. Record and digest against the schema frozen on the step
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION record_browser_step(
        p_tool_run_id uuid,
        p_ordinal     integer,
        p_outcome     jsonb,
        p_requests    integer DEFAULT 0)
RETURNS void
LANGUAGE plpgsql AS $fn$
DECLARE
    p        uuid := rk2_program_required();
    v_run    tool_runs%ROWTYPE;
    v_step   browser_steps%ROWTYPE;
    v_key    text;
BEGIN
    SELECT tr.* INTO v_run FROM tool_runs tr
      JOIN browser_runs b ON b.tool_run_id = tr.id
     WHERE tr.id = p_tool_run_id AND tr.program_id = p;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'tool run % is not a browser mission of this Program',
            p_tool_run_id USING ERRCODE = '23503';
    END IF;
    IF v_run.status <> 'running' THEN
        RAISE EXCEPTION 'browser mission % was already closed as %',
            v_run.label, v_run.status USING ERRCODE = '23514';
    END IF;
    SELECT * INTO v_step FROM browser_steps
     WHERE tool_run_id = p_tool_run_id AND ordinal = p_ordinal;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'this mission has no step %', p_ordinal USING ERRCODE = '23503';
    END IF;
    IF jsonb_typeof(p_outcome) <> 'object' THEN
        RAISE EXCEPTION 'the outcome of a step is an object' USING ERRCODE = '22023';
    END IF;
    FOR v_key IN SELECT jsonb_object_keys(p_outcome) LOOP
        IF NOT (v_key = ANY (v_step.outcome_keys)) THEN
            RAISE EXCEPTION '% has no outcome named %', v_step.action, v_key
                USING ERRCODE = '22023';
        END IF;
    END LOOP;
    FOREACH v_key IN ARRAY v_step.outcome_keys LOOP
        IF NOT (p_outcome ? v_key) THEN
            RAISE EXCEPTION '% must report %', v_step.action, v_key
                USING ERRCODE = '22023';
        END IF;
        IF NOT rk2_browser_outcome_word(p_outcome -> v_key) THEN
            RAISE EXCEPTION 'the outcome % is not a canonical value', v_key
                USING ERRCODE = '22023',
                      HINT = 'an outcome is a boolean, an integer below 100000, or a lowercase word';
        END IF;
    END LOOP;
    IF v_step.action = 'probe'
       AND NOT EXISTS (SELECT 1 FROM browser_probes b
                        WHERE b.probe = v_step.arguments ->> 'probe'
                          AND (p_outcome ->> 'verdict') = ANY (b.verdicts)) THEN
        RAISE EXCEPTION 'the probe % does not return the verdict %',
            v_step.arguments ->> 'probe', coalesce(p_outcome ->> 'verdict', '<none>')
            USING ERRCODE = '22023';
    END IF;
    INSERT INTO browser_step_results
        (tool_run_id, ordinal, program_id, outcome, network_requests)
    VALUES (p_tool_run_id, p_ordinal, p, p_outcome, coalesce(p_requests, 0));
END $fn$;

CREATE OR REPLACE FUNCTION browser_run_digest(p_tool_run_id uuid) RETURNS text
LANGUAGE sql STABLE AS $fn$
    SELECT encode(digest(string_agg(l.line, E'\n' ORDER BY l.ordinal), 'sha256'), 'hex')
      FROM (SELECT r.ordinal,
                   rk2_browser_digest_line(r.ordinal, s.action, r.outcome,
                                           s.outcome_keys) AS line
              FROM browser_step_results r
              JOIN browser_steps s
                ON s.tool_run_id = r.tool_run_id AND s.ordinal = r.ordinal
             WHERE r.tool_run_id = p_tool_run_id) l;
$fn$;


-- The existing standing check is replaced only where the registry widened:
-- probe/step schemas are now separate, and the two new registries must remain
-- unreachable from the model's connection.
CREATE OR REPLACE FUNCTION check_browser_runs()
RETURNS TABLE (problem text, detail text)
LANGUAGE sql STABLE AS $fn$
    SELECT 'requests_without_receipts'::text,
           tr.label || ': ' || sum(r.network_requests) || ' request(s), ' ||
           (SELECT count(*) FROM receipts x WHERE x.tool_run_id = tr.id) || ' receipt(s)'
      FROM browser_runs b
      JOIN tool_runs tr ON tr.id = b.tool_run_id
      JOIN browser_step_results r ON r.tool_run_id = b.tool_run_id
     GROUP BY tr.id, tr.label
    HAVING sum(r.network_requests) >
           (SELECT count(*) FROM receipts x WHERE x.tool_run_id = tr.id)
UNION ALL
    SELECT 'loaded_document_without_a_receipt', tr.label
      FROM browser_runs b
      JOIN tool_runs tr ON tr.id = b.tool_run_id
      JOIN browser_steps s ON s.tool_run_id = b.tool_run_id AND s.action = 'navigate'
      JOIN browser_step_results r
        ON r.tool_run_id = s.tool_run_id AND r.ordinal = s.ordinal
     WHERE r.outcome ->> 'document_loaded' = 'true'
       AND NOT EXISTS (SELECT 1 FROM receipts x WHERE x.tool_run_id = tr.id)
UNION ALL
    SELECT 'probe_reads_stored_credentials', b.probe
      FROM browser_probes b
     WHERE b.javascript ~* '(document\s*\.\s*cookie|localStorage|sessionStorage|indexedDB)'
UNION ALL
    SELECT 'action_outside_the_digest', a.action
      FROM browser_actions a
     WHERE cardinality(a.outcome_keys) = 0
UNION ALL
    SELECT 'probe_outside_the_digest', p.probe
      FROM browser_probes p
     WHERE cardinality(p.outcome_keys) = 0 OR NOT ('verdict' = ANY (p.outcome_keys))
UNION ALL
    SELECT 'outcome_keys_disagree_with_the_step',
           r.tool_run_id::text || ' step ' || r.ordinal
      FROM browser_step_results r
      JOIN browser_steps s
        ON s.tool_run_id = r.tool_run_id AND s.ordinal = r.ordinal
     WHERE (SELECT array_agg(k ORDER BY k) FROM jsonb_object_keys(r.outcome) k)
           IS DISTINCT FROM (SELECT array_agg(k ORDER BY k) FROM unnest(s.outcome_keys) k)
UNION ALL
    SELECT 'outcome_value_outside_the_vocabulary',
           r.tool_run_id::text || ' step ' || r.ordinal || ' ' || e.key
      FROM browser_step_results r
      CROSS JOIN LATERAL jsonb_each(r.outcome) AS e(key, value)
     WHERE NOT rk2_browser_outcome_word(e.value)
UNION ALL
    SELECT 'verdict_outside_its_probe',
           r.tool_run_id::text || ' step ' || r.ordinal
      FROM browser_step_results r
      JOIN browser_steps s
        ON s.tool_run_id = r.tool_run_id AND s.ordinal = r.ordinal
      JOIN browser_probes b ON b.probe = s.arguments ->> 'probe'
     WHERE s.action = 'probe'
       AND NOT ((r.outcome ->> 'verdict') = ANY (b.verdicts))
UNION ALL
    SELECT 'digest_disagrees_with_its_steps', tr.label
      FROM browser_runs b
      JOIN tool_runs tr ON tr.id = b.tool_run_id
     WHERE b.result_digest IS NOT NULL
       AND b.result_digest IS DISTINCT FROM browser_run_digest(b.tool_run_id)
UNION ALL
    SELECT 'closed_mission_without_a_digest', tr.label
      FROM browser_runs b
      JOIN tool_runs tr ON tr.id = b.tool_run_id
     WHERE tr.status = 'success' AND b.result_digest IS NULL
UNION ALL
    SELECT 'mission_open_past_its_timeout', tr.label
      FROM browser_runs b
      JOIN tool_runs tr ON tr.id = b.tool_run_id
      CROSS JOIN rk2_browser_ceilings() c
     WHERE tr.status = 'running'
       AND tr.started_at < now() - make_interval(secs => c.timeout_seconds * 2)
UNION ALL
    SELECT 'ceilings_not_singleton', count(*)::text
      FROM browser_ceilings
    HAVING count(*) <> 1
UNION ALL
    SELECT 'registry_reachable_by_agent', table_name || '.' || privilege_type
      FROM information_schema.table_privileges
     WHERE grantee = 'rk2_state'
       AND table_name IN ('browser_actions','browser_action_arguments',
                          'browser_argument_kinds','browser_probes',
                          'browser_client_state_kinds','browser_messages',
                          'browser_ceilings')
UNION ALL
    SELECT 'browser_verb_reachable', p.proname || ' by ' || r.rolname
      FROM pg_proc p
      CROSS JOIN (VALUES ('rk2_state'),('rk2_proxy')) AS r(rolname)
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.proname IN ('rk2_browser_ceilings','open_browser_run',
                         'record_browser_step','close_browser_run',
                         'browser_run_digest')
       AND has_function_privilege(r.rolname, p.oid, 'EXECUTE')
$fn$;

COMMENT ON FUNCTION check_browser_runs() IS
    'Browser mission accounting, closed outcome schemas, credential-safe '
    'owner probes, stable digests, closure, ceilings and registry isolation.';



-- ===========================================================================
-- The Skill registry follows the file, for the reason tickets 87, 91, 92 and
-- 99 each gave: `skills.source_sha256` and `skill_dependencies.sha256` are a
-- copy of what is on disk, and the copy is only worth having because
-- `CleanCreationTest` compares it against `skill.SKILLS`. `SKILL.md` gained the
-- two new actions, their limits and the sixth untrusted channel, so its digest
-- moves. The version moves with it because a Skill's version is the digest over
-- its dependencies' digests, and `browser-evidence` owns one file.
-- ===========================================================================

UPDATE skill_dependencies
   SET sha256 = '2bd89d68d635be315c870de85e6a1007ec819c0ebcf38d7d3d1fbc07c138ea26'
 WHERE skill_name = 'browser-evidence'
   AND kind = 'instruction'
   AND path = 'SKILL.md';

UPDATE skills
   SET source_sha256 = '2bd89d68d635be315c870de85e6a1007ec819c0ebcf38d7d3d1fbc07c138ea26',
       version       = 'ed4b8fce0ca80c16777d3cfbb18ff66d24ec010299e772f921313f806f7192aa'
 WHERE name = 'browser-evidence';

-- An UPDATE that matched nothing is a digest recorded for a row that is not
-- there, which is the one failure mode a copy of the disk has.
DO $$
DECLARE n integer;
BEGIN
    SELECT count(*) INTO n FROM skills
     WHERE name = 'browser-evidence'
       AND source_sha256 = '2bd89d68d635be315c870de85e6a1007ec819c0ebcf38d7d3d1fbc07c138ea26'
       AND version = 'ed4b8fce0ca80c16777d3cfbb18ff66d24ec010299e772f921313f806f7192aa';
    IF n <> 1 THEN
        RAISE EXCEPTION 'ticket 99: the browser-evidence skill row did not move';
    END IF;

    SELECT count(*) INTO n FROM skill_dependencies
     WHERE skill_name = 'browser-evidence'
       AND kind = 'instruction'
       AND path = 'SKILL.md'
       AND sha256 = '2bd89d68d635be315c870de85e6a1007ec819c0ebcf38d7d3d1fbc07c138ea26';
    IF n <> 1 THEN
        RAISE EXCEPTION 'ticket 99: the browser-evidence instruction digest did not move';
    END IF;
END $$;
