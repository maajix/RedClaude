-- ===========================================================================
-- 020_state_access.sql  --  map ticket 12, the agent state-access interface.
--
-- Ticket 35 gave the schema *write-side* isolation: every program-scoped row
-- carries `program_id`, and every foreign key between two of them carries it on
-- both sides, so a row cannot be written into the wrong program. Nothing in the
-- schema constrains a SELECT. `check_program_isolation()` is entirely about
-- constraints; a plain `SELECT * FROM findings` still returns every program's
-- rows. Read-side isolation was nobody's ticket. It is this one's, because this
-- interface is the only thing an agent reads through.
--
-- Four mechanisms, in order of how hard they are to get around:
--
--   1. ROW LEVEL SECURITY on all 35 program-scoped tables, keyed on a GUC the
--      runtime sets per connection. A handler that forgets its WHERE clause
--      returns nothing rather than another program's rows. Fails closed: with
--      the GUC unset the predicate is NULL and no row matches.
--   2. Two database roles. `rk2_state` is the connection the agent-facing MCP
--      handlers hold; it has SELECT on the read surface and INSERT on the
--      staging tables and *nothing else*. "LLM proposes, runtime commits" stops
--      being a convention: the connection the proposal arrives on has no
--      privilege to write a canonical row. `rk2_runtime` (ticket 07) keeps the
--      commit privileges and never serves an agent call.
--   3. Column-level privilege. `identities.secret_ref` is not granted to
--      `rk2_state` at all, so selecting it raises `permission denied` inside
--      Postgres. Ticket 06 says the column "is never selectable by an
--      agent-facing view"; a view can be edited, a grant is checked per query.
--   4. Two RLS predicates that are not about the program: `receipts` hides
--      lane `proxy_internal` from `rk2_state` (ticket 06: not citable, so not
--      readable), and the global `artifacts` table is reachable only through
--      the program-scoped rows that reference the hash (ticket 11's
--      `artifact_refs` bridge, built here as a view over the referencing rows
--      so it cannot drift from them).
--
-- Also here: the seven relations ticket 11's tool contracts name that no
-- migration ever created. 11 states they are "the thing to migrate, not a
-- suggestion".
-- ===========================================================================

SET client_min_messages = warning;

-- ---------------------------------------------------------------------------
-- A -- the program GUC
-- ---------------------------------------------------------------------------
-- `rk2.program_id` is set by the runtime on the connection, from the session
-- config that started the query. There is no tool argument that reaches it:
-- ticket 11's R18/R-PROGRAM refuse a program identifier anywhere in a tool
-- input tree, and every inputSchema is `additionalProperties: false`, which
-- mcp 1.29.0 validates before the handler body runs.
CREATE FUNCTION rk2_program() RETURNS uuid
LANGUAGE sql STABLE AS $$
    SELECT nullif(current_setting('rk2.program_id', true), '')::uuid
$$;

COMMENT ON FUNCTION rk2_program() IS
    'The session program. NULL when unset, which makes every RLS policy false.';

-- ---------------------------------------------------------------------------
-- B -- the relations ticket 11 names and no migration created
-- ---------------------------------------------------------------------------
-- All program-scoped, all following ticket 35's four rules: `program_id` on the
-- table, `program_id` last in every composite FK, no global unique namespace,
-- `programs` cascade registered in `purge_cascade_edges` and every other FK
-- left NO ACTION so nothing narrower than a whole program can be deleted.

INSERT INTO label_prefixes (kind, prefix) VALUES ('proposals', 'PR')
    ON CONFLICT DO NOTHING;

-- A proposal is the entire write surface of an executing role. It is raw model
-- output plus the provenance labels it cites -- never a canonical row.
CREATE TABLE proposals (
    id           uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id   uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    label        text NOT NULL,
    agent_run_id uuid NOT NULL,
    task_id      uuid NOT NULL,
    payload      jsonb NOT NULL,
    status       text NOT NULL DEFAULT 'staged'
                 CHECK (status IN ('staged','promoted','rejected','superseded')),
    completion   text NOT NULL
                 CHECK (completion IN ('complete','partial','unproven')),
    created_at   timestamptz NOT NULL DEFAULT now(),
    promoted_at  timestamptz,
    UNIQUE (program_id, label),
    UNIQUE (id, program_id),
    FOREIGN KEY (agent_run_id, program_id) REFERENCES agent_runs (id, program_id),
    FOREIGN KEY (task_id, program_id)      REFERENCES tasks (id, program_id),
    CHECK (status <> 'promoted' OR promoted_at IS NOT NULL)
);

-- Every element the runtime refused, with the reason. Ticket 08 made the same
-- move for suppressed hypotheses: a silent drop is indistinguishable from a
-- thing the agent never proposed, and ticket 16 cannot grade what left no row.
CREATE TABLE proposal_drops (
    proposal_id  uuid NOT NULL,
    program_id   uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    ordinal      integer NOT NULL,
    element_path text NOT NULL,
    reason       text NOT NULL
                 CHECK (reason IN ('no_such_receipt','receipt_other_program',
                                   'receipt_proxy_internal','receipt_other_run',
                                   'no_such_tool_run','no_such_label',
                                   'label_other_program','no_provenance')),
    cited        text,
    PRIMARY KEY (proposal_id, ordinal),
    FOREIGN KEY (proposal_id, program_id) REFERENCES proposals (id, program_id)
);

-- The orchestrator's request into the validator session. One label, nothing
-- else -- ticket 11's blindness mechanism 1, expressed as a table so that the
-- absence of a reasoning column is a schema fact.
CREATE TABLE validation_queue (
    id           uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id   uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    finding_id   uuid NOT NULL,
    state        text NOT NULL DEFAULT 'queued'
                 CHECK (state IN ('queued','running','done')),
    requested_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (program_id, finding_id),
    FOREIGN KEY (finding_id, program_id) REFERENCES findings (id, program_id)
);

CREATE TABLE verdicts (
    id                   uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id           uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    finding_id           uuid NOT NULL,
    verdict              text NOT NULL
                         CHECK (verdict IN ('confirmed','refuted','insufficient')),
    failed_assertion_ids text[] NOT NULL DEFAULT '{}',
    created_at           timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (finding_id, program_id) REFERENCES findings (id, program_id)
);

CREATE TABLE report_queue (
    id           uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id   uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    state        text NOT NULL DEFAULT 'queued'
                 CHECK (state IN ('queued','running','done')),
    requested_at timestamptz NOT NULL DEFAULT now()
);

-- `tasks.pending_decision_id` has existed since migration 011 with no table
-- behind it and no foreign key -- found while writing this. The column is
-- given its referent here.
CREATE TABLE pending_decisions (
    id            uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id    uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    task_id       uuid NOT NULL,
    question_code text NOT NULL
                  CHECK (question_code IN ('scope_ambiguous','destructive_action',
                                           'third_party_impact','credential_needed',
                                           'policy_unclear')),
    question      text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    answered_at   timestamptz,
    answer        text,
    UNIQUE (id, program_id),
    FOREIGN KEY (task_id, program_id) REFERENCES tasks (id, program_id)
);

ALTER TABLE tasks
    ADD CONSTRAINT tasks_pending_decision_fk
    FOREIGN KEY (pending_decision_id, program_id)
    REFERENCES pending_decisions (id, program_id);

-- The five candidates ticket 08's runtime offers. `claim_task` refuses a label
-- that is not on the current slate, so the model picks from the runtime's list
-- rather than naming a task it reasoned its way to.
CREATE TABLE task_slate (
    slate_id   uuid NOT NULL DEFAULT uuidv7(),
    program_id uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    task_id    uuid NOT NULL,
    ordinal    integer NOT NULL CHECK (ordinal BETWEEN 1 AND 5),
    offered_at timestamptz NOT NULL DEFAULT now(),
    consumed   boolean NOT NULL DEFAULT false,
    PRIMARY KEY (slate_id, ordinal),
    FOREIGN KEY (task_id, program_id) REFERENCES tasks (id, program_id)
);

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('proposals',        'program_id', 'staging output of one program''s runs'),
    ('proposal_drops',   'program_id', 'same'),
    ('validation_queue', 'program_id', 'same'),
    ('verdicts',         'program_id', 'same'),
    ('report_queue',     'program_id', 'same'),
    ('pending_decisions','program_id', 'same'),
    ('task_slate',       'program_id', 'same')
ON CONFLICT DO NOTHING;

-- ---------------------------------------------------------------------------
-- C -- the agent-facing role
-- ---------------------------------------------------------------------------
-- [ticket 33 consolidation] the CREATE ROLE block moved to `./migrate.sh
-- provision`: rk2_migrate has no CREATEROLE and must not get it. Refused by
-- ./migrate.sh lint.

-- The commit connection. 016 and 017 granted `ALL TABLES IN SCHEMA public`,
-- which binds the tables that existed then, not the seven this migration adds.
-- Re-granting here is what makes `submit_mission_result` able to stage a row
-- at all, and it is the only connection that can.
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO rk2_runtime;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO rk2_runtime;

GRANT USAGE ON SCHEMA public TO rk2_state;

-- Read surface. Deliberately enumerated: a table absent from this list is
-- unreadable by any handler, however the handler is written.
GRANT SELECT ON
    entities, applications, domains, endpoints, hosts, services, technologies,
    parameters, relationships, hypotheses, hypothesis_evidence,
    hypothesis_near_matches, observations, receipts, tool_runs, tests,
    test_runs, test_run_receipts, findings, finding_evidence,
    finding_hypotheses, tasks, task_slate, artifacts, vulnerability_classes,
    programs
TO rk2_state;

-- `identities` minus one column. Not a view, not a redaction: a grant, checked
-- by the executor on every query.
GRANT SELECT (entity_id, program_id, slot_name, class, tenant_entity_id,
              acquired_at, invalidated_at)
    ON identities TO rk2_state;

-- The agent-facing connection has **no write privilege at all**, not even on
-- the staging tables. An agent's call *is* the proposal; the `proposals` row is
-- the runtime's record of having received one, written on the runtime
-- connection after the provenance check. Granting INSERT here would have been
-- the intuitive shape and it is the wrong one: it would put the boundary back
-- inside handler code, where a bug reaches a table, instead of in the
-- privilege system, where a bug reaches an error.
GRANT EXECUTE ON FUNCTION rk2_program() TO rk2_state;

-- Not granted, and each absence is load-bearing: `events` (the log is the
-- runtime's, and an agent reading it would see other roles' turns),
-- `agent_runs` (another agent's mission packet and token counts),
-- `identity_leases`, `label_counters`, `scheduler_lanes`, `scheduler_weights`
-- (the ranking inputs -- an agent that can read the weights can aim at them),
-- `validation_queue`, `verdicts`, `pending_decisions` (write-only channels;
-- ticket 11 requires `park_for_human` not to re-enter any agent's context),
-- and every `*_transitions`, `*_embeddings`, `suppressed_writes`,
-- `surface_fingerprints`, `hypothesis_retest_triggers` table.

-- ---------------------------------------------------------------------------
-- D -- row level security
-- ---------------------------------------------------------------------------
-- One policy per program-scoped table for `rk2_state`, plus a permissive
-- catch-all for `rk2_runtime`, which is the commit connection and is scoped by
-- the constraints ticket 35 built rather than by RLS. The owner (migrations)
-- bypasses RLS, which is why `check_state_access()` below asserts the policies
-- exist rather than trusting that they were written.
DO $$
DECLARE
    t text;
BEGIN
    FOR t IN
        SELECT c.relname FROM pg_class c
         WHERE c.relkind = 'r'
           AND c.relnamespace = 'public'::regnamespace
           AND EXISTS (SELECT 1 FROM pg_attribute a
                        WHERE a.attrelid = c.oid AND a.attname = 'program_id'
                          AND a.attnum > 0 AND NOT a.attisdropped)
           AND c.relname NOT IN (SELECT table_name FROM program_global_tables)
         ORDER BY c.relname
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format(
            'CREATE POLICY %I ON %I AS PERMISSIVE FOR ALL TO rk2_state '
            'USING (program_id = rk2_program()) '
            'WITH CHECK (program_id = rk2_program())',
            t || '_rk2_state', t);
        EXECUTE format(
            'CREATE POLICY %I ON %I AS PERMISSIVE FOR ALL TO rk2_runtime '
            'USING (true) WITH CHECK (true)', t || '_rk2_runtime', t);
    END LOOP;
END $$;

-- `receipts` gets a second, restrictive policy. Ticket 06: a `proxy_internal`
-- receipt is not citable, and the database already refuses an observation that
-- cites one. Serving it for reading would let an agent compose a claim it
-- cannot save. RESTRICTIVE means it ANDs with the program policy instead of
-- ORing, so no later permissive policy can re-open it.
CREATE POLICY receipts_no_proxy_internal ON receipts
    AS RESTRICTIVE FOR ALL TO rk2_state
    USING (lane <> 'proxy_internal');

-- ---------------------------------------------------------------------------
-- E -- the bridge, and the agent-facing projections
-- ---------------------------------------------------------------------------
-- `artifact_refs` is a view, not a table. A table would need a write path on
-- every producer and would then be able to disagree with the rows it indexes;
-- a view over the referencing columns cannot. Every source relation is itself
-- RLS-scoped for `rk2_state`, so the bridge is program-scoped without naming
-- the program.
CREATE VIEW artifact_refs WITH (security_invoker = true) AS
    SELECT program_id, request_agent_sha  AS sha256, 'receipt_request'::text  AS ref_kind, label AS ref_label FROM receipts WHERE request_agent_sha  IS NOT NULL
    UNION ALL
    SELECT program_id, response_agent_sha AS sha256, 'receipt_response'::text AS ref_kind, label AS ref_label FROM receipts WHERE response_agent_sha IS NOT NULL;

GRANT SELECT ON artifact_refs TO rk2_state, rk2_runtime;

-- `artifacts` is a `program_global_table` -- content-addressed and refcounted
-- across programs (ticket 35), so it has no `program_id` to scope on and a bare
-- hash lookup would cross programs. Reachability is scoped instead: a hash is
-- visible only if a row *of this program* references it, and only if the blob
-- is agent-visible. This is ticket 11's `artifact_refs` bridge, as a policy
-- rather than as a join a handler has to remember.
ALTER TABLE artifacts ENABLE ROW LEVEL SECURITY;

CREATE POLICY artifacts_rk2_runtime ON artifacts
    AS PERMISSIVE FOR ALL TO rk2_runtime USING (true) WITH CHECK (true);

CREATE POLICY artifacts_rk2_state ON artifacts
    AS PERMISSIVE FOR SELECT TO rk2_state
    USING (
        visibility = 'agent_visible'
        AND NOT encrypted
        AND purged_at IS NULL
        AND EXISTS (SELECT 1 FROM artifact_refs r WHERE r.sha256 = artifacts.sha256)
    );

-- Every agent-facing projection is `security_invoker`, so the caller's RLS
-- applies rather than the view owner's. A `security_definer` view here would
-- be the whole design's hole: the owner is the migration role, which bypasses
-- RLS, so a definer view returns every program's rows no matter what the
-- policies say. `check_state_access()` asserts the flag.

CREATE VIEW v_surface WITH (security_invoker = true) AS
    SELECT e.label, e.type, e.in_scope, e.first_seen_at, e.last_seen_at,
           coalesce(ep.method || ' ' || ep.path_template,
                    h.hostname, h.address::text, d.fqdn, a.base_url,
                    s.protocol || '/' || s.port, t.name, i.slot_name,
                    e.dedup_key) AS descriptor,
           i.class AS identity_class
      FROM entities e
      LEFT JOIN endpoints    ep ON ep.entity_id = e.id
      LEFT JOIN hosts        h  ON h.entity_id  = e.id
      LEFT JOIN domains      d  ON d.entity_id  = e.id
      LEFT JOIN applications a  ON a.entity_id  = e.id
      LEFT JOIN services     s  ON s.entity_id  = e.id
      LEFT JOIN technologies t  ON t.entity_id  = e.id
      LEFT JOIN identities   i  ON i.entity_id  = e.id;

CREATE VIEW v_hypotheses WITH (security_invoker = true) AS
    SELECT hy.label, hy.status, hy.property_class, hy.statement,
           subj.label AS subject_label,
           ia.label AS identity_a_label, ib.label AS identity_b_label,
           hy.created_at
      FROM hypotheses hy
      LEFT JOIN entities subj ON subj.id = hy.subject_entity_id
      LEFT JOIN entities ia   ON ia.id   = hy.identity_a_entity_id
      LEFT JOIN entities ib   ON ib.id   = hy.identity_b_entity_id;

CREATE VIEW v_evidence WITH (security_invoker = true) AS
    SELECT hy.label AS hypothesis_label, NULL::text AS finding_label,
           o.label AS observation_label, he.polarity, he.role,
           o.kind, o.summary, o.provenance_kind,
           r.label AS receipt_label, tr.label AS tool_run_label
      FROM hypothesis_evidence he
      JOIN hypotheses hy ON hy.id = he.hypothesis_id
      JOIN observations o ON o.id = he.observation_id
      LEFT JOIN receipts  r  ON r.id  = o.receipt_id
      LEFT JOIN tool_runs tr ON tr.id = o.tool_run_id
    UNION ALL
    SELECT NULL::text, f.label, o.label, NULL::text, 'finding'::text,
           o.kind, o.summary, o.provenance_kind,
           r.label, tr.label
      FROM finding_evidence fe
      JOIN findings f ON f.id = fe.finding_id
      JOIN observations o ON o.id = fe.observation_id
      LEFT JOIN receipts  r  ON r.id  = o.receipt_id
      LEFT JOIN tool_runs tr ON tr.id = o.tool_run_id;

CREATE VIEW v_receipts WITH (security_invoker = true) AS
    SELECT r.label, r.lane, r.decision, r.reason, r.method, r.scheme, r.host,
           r.port, r.path, r.status_code, r.ts_arrival, r.waited_ms,
           i.label AS identity_label,
           r.request_agent_sha, r.response_agent_sha
      FROM receipts r
      LEFT JOIN entities i ON i.id = r.identity_entity_id;

CREATE VIEW v_artifacts WITH (security_invoker = true) AS
    SELECT a.sha256, a.byte_size, a.content_type,
           (SELECT count(*) FROM artifact_refs r WHERE r.sha256 = a.sha256) AS ref_count
      FROM artifacts a;

-- The validator's packet. `PACKET_COLUMNS` in ticket 11 is a Python column
-- allowlist over a dict; this is the same allowlist one layer lower, so a new
-- column on `findings` is invisible to the validator session even if the
-- Python list is edited wrongly.
CREATE VIEW v_validation_packet WITH (security_invoker = true) AS
    SELECT f.label AS finding_label, f.status, f.class_id,
           subj.label AS subject_label,
           hy.label AS hypothesis_label, hy.statement, hy.property_class,
           t.label AS test_label, t.spec, t.spec_sha256,
           tr.outcome AS runtime_replay_outcome, tr.assertion_results,
           tr.lane AS replay_lane
      FROM findings f
      LEFT JOIN entities subj ON subj.id = f.subject_entity_id
      LEFT JOIN finding_hypotheses fh ON fh.finding_id = f.id
      LEFT JOIN hypotheses hy ON hy.id = fh.hypothesis_id
      LEFT JOIN tests t ON t.hypothesis_id = hy.id
      LEFT JOIN test_runs tr ON tr.id = f.validated_by_test_run_id;

GRANT SELECT ON v_surface, v_hypotheses, v_evidence, v_receipts, v_artifacts,
                v_validation_packet
    TO rk2_state, rk2_runtime;

-- ---------------------------------------------------------------------------
-- F -- the model as queries
-- ---------------------------------------------------------------------------
-- Same shape as ticket 35's `check_program_isolation()`: the rules are stated
-- once, as SQL that returns the violations, and the migration refuses to finish
-- while any row comes back. Applying 020 is the proof that 020 holds.
CREATE FUNCTION check_state_access()
RETURNS TABLE (rule text, obj text, detail text)
LANGUAGE sql STABLE AS $$
    -- 1. every program-scoped table has RLS enabled
    SELECT 'rls_disabled', c.relname, 'no row level security'
      FROM pg_class c
     WHERE c.relkind = 'r' AND c.relnamespace = 'public'::regnamespace
       AND EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid = c.oid
                     AND a.attname = 'program_id' AND a.attnum > 0 AND NOT a.attisdropped)
       AND c.relname NOT IN (SELECT table_name FROM program_global_tables)
       AND NOT c.relrowsecurity

    UNION ALL
    -- 2. and a policy that binds it to the session program for rk2_state
    SELECT 'rls_unbound', c.relname, 'no rk2_state policy on program_id'
      FROM pg_class c
     WHERE c.relkind = 'r' AND c.relnamespace = 'public'::regnamespace
       AND EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid = c.oid
                     AND a.attname = 'program_id' AND a.attnum > 0 AND NOT a.attisdropped)
       AND c.relname NOT IN (SELECT table_name FROM program_global_tables)
       AND NOT EXISTS (
             SELECT 1 FROM pg_policy p
              WHERE p.polrelid = c.oid
                AND 'rk2_state'::regrole = ANY (p.polroles)
                AND pg_get_expr(p.polqual, p.polrelid) LIKE '%rk2_program()%')

    UNION ALL
    -- 3. no agent-facing view may be security_definer
    SELECT 'view_definer', c.relname, 'security_invoker is not set'
      FROM pg_class c
     WHERE c.relkind = 'v' AND c.relnamespace = 'public'::regnamespace
       AND c.relname LIKE ANY (ARRAY['v\_%','artifact\_refs'])
       AND coalesce((SELECT option_value FROM pg_options_to_table(c.reloptions)
                      WHERE option_name = 'security_invoker'), 'false') <> 'true'

    UNION ALL
    -- 4. secret material is not selectable, by view or by grant
    SELECT 'secret_reachable', table_name || '.' || column_name, privilege_type
      FROM information_schema.column_privileges
     WHERE grantee = 'rk2_state' AND column_name = 'secret_ref'

    UNION ALL
    SELECT 'secret_in_view', c.relname, a.attname
      FROM pg_class c JOIN pg_attribute a ON a.attrelid = c.oid
     WHERE c.relkind = 'v' AND c.relnamespace = 'public'::regnamespace
       AND a.attnum > 0 AND a.attname = 'secret_ref'

    UNION ALL
    -- 5. no uuid ever crosses the boundary: ticket 06 says agents cite labels
    SELECT 'uuid_in_view', c.relname, a.attname
      FROM pg_class c
      JOIN pg_attribute a ON a.attrelid = c.oid
      JOIN pg_type ty ON ty.oid = a.atttypid
     WHERE c.relkind = 'v' AND c.relnamespace = 'public'::regnamespace
       AND c.relname LIKE 'v\_%'
       AND a.attnum > 0 AND NOT a.attisdropped AND ty.typname = 'uuid'

    UNION ALL
    -- 6. a proxy_internal receipt is not readable by the agent connection
    SELECT 'proxy_internal_readable', 'receipts', 'no restrictive lane policy'
     WHERE NOT EXISTS (
        SELECT 1 FROM pg_policy p
         WHERE p.polrelid = 'receipts'::regclass
           AND NOT p.polpermissive
           AND 'rk2_state'::regrole = ANY (p.polroles)
           AND pg_get_expr(p.polqual, p.polrelid) LIKE '%proxy_internal%')

    UNION ALL
    -- 7. the agent connection may not write a canonical row. This is
    --    "LLM proposes, runtime commits" as a privilege rather than as a rule
    --    somebody has to keep following.
    SELECT 'agent_can_write', table_name, privilege_type
      FROM information_schema.table_privileges
     WHERE grantee = 'rk2_state'
       AND privilege_type IN ('INSERT','UPDATE','DELETE','TRUNCATE')

    UNION ALL
    -- 8. and it may not read the log, the ranking inputs, or another run
    SELECT 'agent_reads_runtime_table', table_name, privilege_type
      FROM information_schema.table_privileges
     WHERE grantee = 'rk2_state'
       AND table_name IN ('events','agent_runs','scheduler_weights',
                          'scheduler_lanes','identity_leases','label_counters',
                          'suppressed_writes','validation_queue','verdicts',
                          'pending_decisions','report_queue')

    UNION ALL
    -- 9. ticket 35's rule, restated for the tables this migration adds: an FK
    --    between two program-scoped rows carries program_id on both sides.
    SELECT 'fk_without_program', c.relname, k.conname
      FROM pg_constraint k JOIN pg_class c ON c.oid = k.conrelid
      JOIN pg_class f ON f.oid = k.confrelid
     WHERE k.contype = 'f'
       AND c.relname IN ('proposals','proposal_drops','validation_queue',
                         'verdicts','report_queue','pending_decisions','task_slate')
       AND f.relname NOT IN (SELECT table_name FROM program_global_tables)
       AND NOT EXISTS (SELECT 1 FROM pg_attribute a
                        WHERE a.attrelid = c.oid AND a.attnum = k.conkey[array_length(k.conkey,1)]
                          AND a.attname = 'program_id');
$$;

DO $$
DECLARE
    n integer;
    v record;
BEGIN
    SELECT count(*) INTO n FROM check_state_access();
    IF n > 0 THEN
        FOR v IN SELECT * FROM check_state_access() LOOP
            RAISE WARNING 'state access violation: % % %', v.rule, v.obj, v.detail;
        END LOOP;
        RAISE EXCEPTION '020 refuses to finish: % state-access violations', n;
    END IF;
END $$;

-- 35's own model must still hold with seven new tables in it.
DO $$
DECLARE n integer;
BEGIN
    SELECT count(*) INTO n FROM check_program_isolation();
    IF n > 0 THEN
        RAISE EXCEPTION '020 broke ticket 35: % isolation violations', n;
    END IF;
END $$;
