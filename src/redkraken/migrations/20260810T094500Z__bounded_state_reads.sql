-- ===========================================================================
-- Production harness 05 -- bounded reads by label, and no way to name another
-- Program
-- ===========================================================================
-- 020 built the agent-facing read surface and 033 turned it into a per-column
-- registry. What neither did was let anything use it: `rk2_state` holds no
-- CONNECT privilege on the database, so the role the whole isolation design
-- exists for has never opened a session. An access boundary nothing has ever
-- crossed is a claim, not a control.
--
-- Crossing it turns up the second defect. `programs` is a
-- `program_global_table` -- it has no `program_id` of its own, so the RLS
-- finalizer skips it -- and 020 nevertheless granted `rk2_state` SELECT on it.
-- The agent connection could therefore enumerate every Program on the
-- installation by slug, name and scope policy. Ticket 05 asks for the opposite
-- property in as many words: an unknown label and another Program's label must
-- be indistinguishable, and a role holding the Program registry can tell them
-- apart by construction. The registry leaves the read surface here.
--
-- What replaces it is a read keyed by the only identifier an agent ever sees.
-- `v_records` is one relation over the eight labelled record kinds the agent
-- may read, and it answers with a label, a revision, a digest and the record
-- itself:
--
--   * the revision is `max(events.seq)` for that row. The event log already
--     records every change to every canonical row, so a per-record revision
--     needs no new column and no new writer; `rk2_revision()` is that lookup
--     and it is deliberately not `SECURITY DEFINER`, so row level security on
--     `events` scopes it to the session's own Program like everything else.
--     ADR-0001 governs what this may be: the record itself is read from the
--     rows, never rebuilt from the log, and what the log answers is only "has
--     this row changed since you last looked". It does make the completeness
--     that ADR turns on load-bearing for an agent-facing number -- pruning the
--     log would walk revisions backwards -- which is the same invariant the
--     replay test already exists to hold.
--   * the digest is sha256 over the record's own jsonb text, so the digest a
--     compact read reports and the digest of the full record fetched by that
--     label are the same value computed once, in one place.
--
-- Three columns of `events` become readable to make the revision possible --
-- `seq`, `subject_table`, `subject_id`, and nothing else. 020's rule 8 refuses
-- an `events` grant, but it reads `information_schema.table_privileges`, which
-- does not list column grants, so it would not have noticed. That loophole is
-- closed in the same migration that uses it: `check_state_isolation()` names
-- the three columns as the whole allowlist, and a fourth one becoming readable
-- fails the gate.
--
-- Free-form jsonb -- `tests.spec`, `tool_runs.args`, `entities.metadata` -- is
-- not in the projection. Their hashes are. A record built only from columns the
-- corpus shapes is a record that cannot carry a uuid out to a model by
-- accident, and the large payload is what §11 of the spec says to fetch by
-- stable identifier rather than embed.
-- ===========================================================================


-- ---------------------------------------------------------------------------
-- 1. The agent connection can open a session
-- ---------------------------------------------------------------------------
-- Same shape as 029 for the other three roles and 040 for the proxy: the
-- database name is not knowable when the file is written, so it is read back
-- from the session applying it.

DO $$
BEGIN
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO rk2_state', current_database());
END $$;


-- ---------------------------------------------------------------------------
-- 2. The Program registry leaves the agent read surface
-- ---------------------------------------------------------------------------
-- The registry row goes with the grant. `apply_state_grants()` is additive from
-- `state_read_surface`, so deleting the rows is what stops the finalizer
-- handing the privilege straight back, and `check_state_grants()` rule 3 fails
-- the gate if anything grants it without registering it again.
--
-- The consequence is deliberate and worth stating: the agent connection cannot
-- read its own Program's slug, name or scope policy either. Those are policy an
-- operator wrote, they are compiled into what the runtime puts in a Mission
-- packet, and a role that can read one Program's row from `programs` is a role
-- whose isolation rests on a WHERE clause rather than on a privilege.

DELETE FROM state_read_surface WHERE table_name = 'programs';
REVOKE ALL ON TABLE programs FROM rk2_state;


-- ---------------------------------------------------------------------------
-- 3. Revisions, from the log that already records every change
-- ---------------------------------------------------------------------------
-- Not `SECURITY DEFINER`, and that is the whole of its isolation: the function
-- body reads `events`, `events` is program-scoped with the policy the finalizer
-- wrote, and a definer function here would answer with the owner's view of the
-- log -- every Program's revisions, through a function the agent may call.
--
-- `coalesce(..., 0)` rather than NULL: a row whose table is exempt from event
-- emission has no revision to report, and 0 says "no recorded change" in the
-- same type as every other answer.

CREATE FUNCTION rk2_revision(p_table text, p_id uuid) RETURNS bigint
LANGUAGE sql STABLE PARALLEL SAFE AS $$
    SELECT coalesce(max(seq), 0)
      FROM events
     WHERE subject_table = p_table AND subject_id = p_id
$$;

COMMENT ON FUNCTION rk2_revision(text, uuid) IS
    'The revision of one canonical row: max(events.seq) for it, under the caller''s own row level security.';

-- Timestamps rendered in UTC, explicitly. `to_jsonb(timestamptz)` renders
-- through the session `TimeZone`, which would make a digest depend on who is
-- asking rather than on what the record says.

CREATE FUNCTION rk2_instant(p_at timestamptz) RETURNS text
LANGUAGE sql STABLE PARALLEL SAFE AS $$
    SELECT to_char(p_at AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
$$;

COMMENT ON FUNCTION rk2_instant(timestamptz) IS
    'One instant as UTC text, so a record digest does not depend on the session time zone.';

-- One definition of what an entity is called. 020 wrote this coalesce inside
-- `v_surface`; restating it here would put two answers to "what is this row" in
-- front of the same model, free to drift by one subtype the day a subtype is
-- added. `v_surface` is rewritten below to call it, so there is one.
--
-- Keyed by the row's id and not by its label. Labels collide across Programs by
-- design -- that collision is what ticket 05 exists to hold through -- so a
-- shared definition reached by label would be the one join in this file where a
-- foreign row could answer.
--
-- Invoker rights, like everything else on this surface: the joins read tables
-- row level security scopes, and a definer version would resolve an entity of
-- any Program for whoever could name one.

CREATE FUNCTION rk2_descriptor(p_entity_id uuid) RETURNS text
LANGUAGE sql STABLE AS $$
    SELECT coalesce(ep.method || ' ' || ep.path_template,
                    h.hostname, h.address::text, d.fqdn, a.base_url,
                    s.protocol || '/' || s.port::text, t.name, i.slot_name,
                    e.dedup_key)
      FROM entities e
      LEFT JOIN endpoints    ep ON ep.entity_id = e.id
      LEFT JOIN hosts        h  ON h.entity_id  = e.id
      LEFT JOIN domains      d  ON d.entity_id  = e.id
      LEFT JOIN applications a  ON a.entity_id  = e.id
      LEFT JOIN services     s  ON s.entity_id  = e.id
      LEFT JOIN technologies t  ON t.entity_id  = e.id
      LEFT JOIN identities   i  ON i.entity_id  = e.id
     WHERE e.id = p_entity_id
$$;

COMMENT ON FUNCTION rk2_descriptor(uuid) IS
    'What one entity is called, from whichever subtype row it has. The one definition; v_surface and v_records both call it.';

CREATE OR REPLACE VIEW v_surface WITH (security_invoker = true) AS
    SELECT e.label, e.type, e.in_scope, e.first_seen_at, e.last_seen_at,
           rk2_descriptor(e.id) AS descriptor,
           i.class AS identity_class
      FROM entities e
      LEFT JOIN identities i ON i.entity_id = e.id;


-- ---------------------------------------------------------------------------
-- 4. The record projection
-- ---------------------------------------------------------------------------
-- `security_invoker`, like every agent-facing view: the owner is the migration
-- role, which bypasses row level security, so a definer view here returns every
-- Program's rows however good the policies are. 020's `check_state_access()`
-- rule 3 asserts the flag and rule 5 asserts that no column of a `v_` view is a
-- uuid.
--
-- Every reference to another row is carried as that row's label. An agent cites
-- labels; a uuid in this projection would be a second, unlabelled namespace
-- reaching the model.

CREATE VIEW v_records WITH (security_invoker = true) AS
SELECT r.kind,
       r.label,
       r.revision,
       encode(sha256(convert_to(r.record::text, 'utf8')), 'hex') AS digest,
       r.record
  FROM (
    SELECT 'entity'::text AS kind, e.label,
           rk2_revision('entities', e.id) AS revision,
           jsonb_build_object(
               'kind', 'entity',
               'label', e.label,
               'type', e.type,
               'in_scope', e.in_scope,
               'descriptor', rk2_descriptor(e.id),
               'identity_class', i.class,
               'scope_class', e.scope_class,
               'scope_tier', e.scope_tier,
               'first_seen_at', rk2_instant(e.first_seen_at),
               'last_seen_at', rk2_instant(e.last_seen_at)) AS record
      FROM entities e
      LEFT JOIN identities i ON i.entity_id = e.id

    UNION ALL
    SELECT 'hypothesis', hy.label,
           rk2_revision('hypotheses', hy.id),
           jsonb_build_object(
               'kind', 'hypothesis',
               'label', hy.label,
               'status', hy.status,
               'property_class', hy.property_class,
               'statement', hy.statement,
               'subject_label', subj.label,
               'identity_a_label', ia.label,
               'identity_b_label', ib.label,
               'superseded_by_label', sup.label,
               'observed_fingerprint', hy.observed_fingerprint,
               'status_changed_at', rk2_instant(hy.status_changed_at),
               'created_at', rk2_instant(hy.created_at))
      FROM hypotheses hy
      LEFT JOIN entities subj ON subj.id = hy.subject_entity_id
      LEFT JOIN entities ia   ON ia.id   = hy.identity_a_entity_id
      LEFT JOIN entities ib   ON ib.id   = hy.identity_b_entity_id
      LEFT JOIN hypotheses sup ON sup.id = hy.superseded_by

    UNION ALL
    SELECT 'observation', o.label,
           rk2_revision('observations', o.id),
           jsonb_build_object(
               'kind', 'observation',
               'label', o.label,
               'observation_kind', o.kind,
               'summary', o.summary,
               'provenance_kind', o.provenance_kind,
               'subject_label', subj.label,
               'receipt_label', rc.label,
               'tool_run_label', tr.label,
               'observed_at', rk2_instant(o.observed_at))
      FROM observations o
      LEFT JOIN entities  subj ON subj.id = o.subject_entity_id
      LEFT JOIN receipts  rc   ON rc.id   = o.receipt_id
      LEFT JOIN tool_runs tr   ON tr.id   = o.tool_run_id

    UNION ALL
    SELECT 'receipt', rc.label,
           rk2_revision('receipts', rc.id),
           jsonb_build_object(
               'kind', 'receipt',
               'label', rc.label,
               'lane', rc.lane,
               'purpose', rc.purpose,
               'decision', rc.decision,
               'reason', rc.reason,
               'method', rc.method,
               'scheme', rc.scheme,
               'host', rc.host,
               'port', rc.port,
               'path', rc.path,
               'status_code', rc.status_code,
               'identity_label', idn.label,
               'tool_run_label', tr.label,
               'scope_class', rc.scope_class,
               'intercepted', rc.intercepted,
               'transport_citable', rc.transport_citable,
               'request_agent_sha', rc.request_agent_sha,
               'response_agent_sha', rc.response_agent_sha,
               'waited_ms', rc.waited_ms,
               'ts_arrival', rk2_instant(rc.ts_arrival))
      FROM receipts rc
      LEFT JOIN entities  idn ON idn.id = rc.identity_entity_id
      LEFT JOIN tool_runs tr  ON tr.id  = rc.tool_run_id

    UNION ALL
    SELECT 'tool_run', tr.label,
           rk2_revision('tool_runs', tr.id),
           jsonb_build_object(
               'kind', 'tool_run',
               'label', tr.label,
               'tool', tr.tool,
               'status', tr.status,
               'decision', tr.decision,
               'decision_reason', tr.decision_reason,
               'risk_class', tr.risk_class,
               'transport', tr.transport,
               'mcp_server', tr.mcp_server,
               'task_label', tk.label,
               'args_sha256', tr.args_sha256,
               'result_sha256', tr.result_sha256,
               'started_at', rk2_instant(tr.started_at),
               'finished_at', rk2_instant(tr.finished_at))
      FROM tool_runs tr
      LEFT JOIN tasks tk ON tk.id = tr.task_id

    UNION ALL
    SELECT 'task', tk.label,
           rk2_revision('tasks', tk.id),
           jsonb_build_object(
               'kind', 'task',
               'label', tk.label,
               'task_kind', tk.kind,
               'status', tk.status,
               'subject_label', subj.label,
               'hypothesis_label', hy.label,
               'finding_label', f.label,
               'skill_name', tk.skill_name,
               'priority', tk.priority,
               'expected_information_gain', tk.expected_information_gain,
               'potential_impact', tk.potential_impact,
               'novelty', tk.novelty,
               'estimated_cost', tk.estimated_cost,
               'confidence_of_execution', tk.confidence_of_execution,
               'attempts', tk.attempts,
               'abandoned_reason', tk.abandoned_reason,
               'created_at', rk2_instant(tk.created_at),
               'claimed_at', rk2_instant(tk.claimed_at),
               'finished_at', rk2_instant(tk.finished_at))
      FROM tasks tk
      LEFT JOIN entities   subj ON subj.id = tk.subject_entity_id
      LEFT JOIN hypotheses hy   ON hy.id   = tk.hypothesis_id
      LEFT JOIN findings   f    ON f.id    = tk.finding_id

    UNION ALL
    SELECT 'test', ts.label,
           rk2_revision('tests', ts.id),
           jsonb_build_object(
               'kind', 'test',
               'label', ts.label,
               'hypothesis_label', hy.label,
               'supersedes_label', prev.label,
               'spec_sha256', ts.spec_sha256,
               'created_at', rk2_instant(ts.created_at))
      FROM tests ts
      LEFT JOIN hypotheses hy ON hy.id = ts.hypothesis_id
      LEFT JOIN tests prev ON prev.id = ts.supersedes_test_id

    UNION ALL
    SELECT 'finding', f.label,
           rk2_revision('findings', f.id),
           jsonb_build_object(
               'kind', 'finding',
               'label', f.label,
               'status', f.status,
               'class_id', f.class_id,
               'title', f.title,
               'severity', f.severity,
               'cvss_vector', f.cvss_vector,
               'subject_label', subj.label,
               'duplicate_of_label', dup.label,
               'external_ref', f.external_ref,
               'validated_run_outcome', f.validated_run_outcome,
               'status_changed_at', rk2_instant(f.status_changed_at),
               'reported_at', rk2_instant(f.reported_at),
               'created_at', rk2_instant(f.created_at))
      FROM findings f
      LEFT JOIN entities subj ON subj.id = f.subject_entity_id
      LEFT JOIN findings dup  ON dup.id  = f.duplicate_of_finding_id
  ) r;

COMMENT ON VIEW v_records IS
    'Every labelled record this Program holds, with its revision and a digest of itself. The only identifier is the label.';


-- ---------------------------------------------------------------------------
-- 5. What the agent connection may read to make that work
-- ---------------------------------------------------------------------------
-- Enumerated, per column, like everything else on this surface. `program_id` is
-- absent from the `events` rows on purpose: row level security scopes the
-- lookup without the querying role having to read the column it scopes on.

INSERT INTO state_read_surface (table_name, column_name, added_by) VALUES
    ('events',    'seq',           'ph2-05'),
    ('events',    'subject_table', 'ph2-05'),
    ('events',    'subject_id',    'ph2-05'),
    ('v_records', 'kind',          'ph2-05'),
    ('v_records', 'label',         'ph2-05'),
    ('v_records', 'revision',      'ph2-05'),
    ('v_records', 'digest',        'ph2-05'),
    ('v_records', 'record',        'ph2-05');


-- ---------------------------------------------------------------------------
-- 6. The three rules, as a query that returns the violations
-- ---------------------------------------------------------------------------

CREATE FUNCTION check_state_isolation()
RETURNS TABLE (problem text, object text, detail text)
LANGUAGE sql STABLE AS $$
    -- 1. the Program registry is not readable by the agent connection, at any
    --    granularity. A role holding this table can tell an unknown label from
    --    another Program's label by asking a second question.
    SELECT 'state_reads_program_registry', 'programs', p.priv
      FROM (VALUES ('SELECT'),('INSERT'),('UPDATE'),('DELETE'),
                   ('TRUNCATE'),('REFERENCES'),('TRIGGER')) AS p(priv)
     WHERE has_table_privilege('rk2_state', 'programs'::regclass, p.priv)
  UNION ALL
    SELECT 'state_reads_program_registry', 'programs.' || a.attname, 'SELECT'
      FROM pg_attribute a
     WHERE a.attrelid = 'programs'::regclass AND a.attnum > 0 AND NOT a.attisdropped
       AND has_column_privilege('rk2_state', a.attrelid, a.attnum, 'SELECT')

  UNION ALL
    -- 2. 020's rule 8 restated at column granularity, which is where it has a
    --    hole: `information_schema.table_privileges` does not list column
    --    grants, so a per-column grant on the log would pass it unseen. Three
    --    columns of `events` are the whole allowlist and they are what
    --    `rk2_revision()` reads.
    SELECT 'state_reads_runtime_column', c.relname || '.' || a.attname,
           'readable by rk2_state; the log, the ranking inputs and other runs are not the agent''s'
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
      JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
     WHERE c.relname IN ('events','agent_runs','scheduler_weights','scheduler_lanes',
                         'identity_leases','label_counters','suppressed_writes',
                         'validation_queue','verdicts','pending_decisions','report_queue')
       AND has_column_privilege('rk2_state', c.oid, a.attnum, 'SELECT')
       AND (c.relname, a.attname) NOT IN
           (VALUES ('events','seq'), ('events','subject_table'), ('events','subject_id'))

  UNION ALL
    -- 3. both functions `v_records` is built from run as their caller. As
    --    `SECURITY DEFINER` either would answer with the owner's view of the
    --    tables it reads, which is every Program's.
    SELECT 'state_bridge_definer', p.proname, 'SECURITY DEFINER; it would read across Programs'
      FROM pg_proc p
      JOIN pg_namespace n ON n.oid = p.pronamespace AND n.nspname = 'public'
     WHERE p.proname IN ('rk2_revision', 'rk2_descriptor') AND p.prosecdef
  UNION ALL
    SELECT 'state_bridge_missing', f.name, 'no such function; v_records cannot be built'
      FROM (VALUES ('rk2_revision'), ('rk2_descriptor')) AS f(name)
     WHERE NOT EXISTS (
        SELECT 1 FROM pg_proc p
          JOIN pg_namespace n ON n.oid = p.pronamespace AND n.nspname = 'public'
         WHERE p.proname = f.name)
$$;

INSERT INTO standing_checks (name, query, owner_ticket, note) VALUES
    ('state_isolation', 'SELECT * FROM check_state_isolation()', 'ph2-05',
     'the agent connection cannot enumerate Programs, cannot read the log beyond the three columns a revision needs, and builds every record under its own row level security');


-- ---------------------------------------------------------------------------
-- 7. Bring the invariants to true for the corpus as it stands
-- ---------------------------------------------------------------------------
-- The runner calls it again at the end of every run. Calling it here is what
-- makes the grants above real inside the transaction that registers them, and
-- what makes this file self-contained if someone applies it by hand.
--
-- `assert_standing_checks()` is deliberately not called. This is the last file
-- in the corpus, so it runs before the finalizers rather than between two
-- migrations, and three of the registered checks describe invariants those
-- finalizers establish. The gate runs all of them afterwards; what is asserted
-- here is this file's own rule, which depends on nothing later.

SELECT apply_state_grants();

DO $$
DECLARE n integer; v record;
BEGIN
    SELECT count(*) INTO n FROM check_state_isolation();
    IF n > 0 THEN
        FOR v IN SELECT * FROM check_state_isolation() LOOP
            RAISE WARNING 'state isolation violation: % % %', v.problem, v.object, v.detail;
        END LOOP;
        RAISE EXCEPTION 'ph2-05 refuses to finish: % state-isolation violation(s)', n;
    END IF;
END $$;
