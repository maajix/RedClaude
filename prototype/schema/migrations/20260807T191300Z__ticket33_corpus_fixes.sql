-- ===========================================================================
-- ticket 33 -- what consolidation found
-- ===========================================================================
-- Fourteen migrations were each written against a schema that ended at their
-- own last statement. Applied as a corpus they leave five holes, and four of
-- them are the same hole: a migration establishes an invariant by sweeping the
-- tables that exist when it runs, and every table added afterwards silently
-- misses it.
--
-- So this migration does two different things, and the second is the point:
--
--   1. It repairs the four instances. (Sections A-C.)
--   2. It converts each swept invariant into a function the *runner* calls at
--      the end of every run, plus a check that fails the run if the invariant
--      does not hold. (Sections D-F.) After this, a migration 029 that adds a
--      table gets its RLS policy without asking, and cannot hand `rk2_state` a
--      column without a registry row, and cannot make a program unpurgeable.
--      The thing that was true once is now true at the end of every `up`.
--
-- The name for the pattern is in `./migrate.sh`: a finalizer is an end-of-run
-- invariant, not a one-shot. `attach_event_triggers()` was already one. This
-- migration adds `apply_state_rls()` and `apply_state_grants()` to the set and
-- gives all of them a checker, so the invariant is *asserted*, not assumed.
-- ===========================================================================

SET client_min_messages = warning;

-- ===========================================================================
-- A -- every table is classified, and classified once
-- ===========================================================================
-- 79 tables, 16 emitters, and 31 tables that no migration ever placed on
-- either side of the line. `check_event_coverage()` reported all 31 the moment
-- the corpus was assembled -- which is the checker doing its job, and is also
-- why the corpus could not go green until they were decided.
--
-- Two of the exempt rows were wrong rather than missing: 016 listed `receipts`
-- and `tool_runs` as `undecided` and a later migration gave them emit configs,
-- so they were classified twice. The emit config wins; the exempt rows go.

DELETE FROM event_table_exempt
 WHERE table_name IN (SELECT table_name FROM event_table_config);

-- Two new exempt kinds. `undecided` was the honest label for a table whose
-- classification was charged to a ticket; this is that ticket, so it has to
-- produce the labels rather than keep the placeholder.
--
--   `covered`  -- the row is written in the same transaction as a row that
--                 emits, and the emitting row names it. Reading the event and
--                 following it reaches this row, so a second event about the
--                 same fact would be a duplicate, not a record.
--   `audit`    -- an append-only trail of a runtime action. The row *is* the
--                 record; an event about it would say the same thing twice and
--                 would put a second copy of the trail in a table an agent's
--                 read surface deliberately excludes.
ALTER TABLE event_table_exempt DROP CONSTRAINT event_table_exempt_exempt_kind_check;
ALTER TABLE event_table_exempt ADD CONSTRAINT event_table_exempt_exempt_kind_check
    CHECK (exempt_kind IN ('bookkeeping','reference','derived','log','covered','audit','undecided'));

-- The eight rows 016 left `undecided`. Seven are child rows of an emitter;
-- `programs` is the operator's own declaration.
UPDATE event_table_exempt SET exempt_kind = 'covered', owner_ticket = '33',
       reason = 'written with the row that emits and named by it; the emitting event is the record'
 WHERE table_name IN ('artifacts','test_run_receipts','finding_evidence',
                      'hypothesis_evidence','finding_hypotheses',
                      'hypothesis_near_matches','hypothesis_retest_triggers')
   AND exempt_kind = 'undecided';

UPDATE event_table_exempt SET exempt_kind = 'reference', owner_ticket = '33',
       reason = 'the operator scope declaration, created and purged through the control surface, never by the loop; every event already carries program_id'
 WHERE table_name = 'programs' AND exempt_kind = 'undecided';

-- The entity subtype tables. Each row is the 1:1 extension of an `entities`
-- row, written in the same statement, and `entity.created` / `entity.updated`
-- name that row. A second event per subtype would double-count one entity.
UPDATE event_table_exempt SET exempt_kind = 'covered', owner_ticket = '33',
       reason = '1:1 extension of an entities row; entity.created/updated is the record'
 WHERE table_name IN ('applications','domains','endpoints','hosts','identities',
                      'parameters','services','technologies')
   AND exempt_kind = 'undecided';

UPDATE event_table_exempt SET exempt_kind = 'reference', owner_ticket = '33',
       reason = 'scheduler configuration; the ranking inputs, changed only by migration or operator, and scheduler.ranked records what they produced'
 WHERE table_name IN ('scheduler_lanes','scheduler_weights') AND exempt_kind = 'undecided';

UPDATE event_table_exempt SET exempt_kind = 'derived', owner_ticket = '33',
       reason = 'recomputable from the observations that produced it'
 WHERE table_name = 'surface_fingerprints' AND exempt_kind = 'undecided';

INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    -- 017 program isolation: the registries the isolation checker reads
    ('program_global_tables',   'reference',   'isolation registry, changed only by migration', '35'),
    ('cross_program_exempt_fks','reference',   'isolation registry, changed only by migration', '35'),
    -- 018 vocabularies
    ('observation_kinds',       'reference',   'vocabulary, changed only by migration', '27'),
    ('property_classes',        'reference',   'vocabulary, changed only by migration', '27'),
    ('property_class_families', 'reference',   'vocabulary, changed only by migration', '27'),
    ('property_class_vulnerability_classes','reference','vocabulary mapping, changed only by migration', '27'),
    -- 019 role to kind
    ('roles',                   'reference',   'agent role catalogue, changed only by migration', '34'),
    ('role_task_kinds',         'reference',   'role to task-kind mapping, changed only by migration', '34'),
    ('task_kinds',              'reference',   'task-kind vocabulary, changed only by migration', '34'),
    ('skills',                  'reference',   'skill catalogue, changed only by migration', '34'),
    -- 020 state access
    ('digest_facts',            'derived',     'recomputed from rows that emit; a stale digest is regenerated, not resumed', '12'),
    ('task_slate',              'derived',     'the materialised ranking; recomputable from tasks and the weights', '08'),
    -- 021 scope policy
    ('program_scope_versions',  'reference',   'the operator scope document; append-only and named by every receipt, so the receipt event carries the version', '26'),
    ('program_scope_rules',     'reference',   'the rules of a scope version; immutable with it', '26'),
    -- 022 hooks and receipts
    ('risk_classes',            'reference',   'risk vocabulary, changed only by migration', '13'),
    ('tool_risk_classes',       'reference',   'tool to risk-class mapping, changed only by migration', '13'),
    ('call_risk_rules',         'reference',   'hook decision table, changed only by migration', '13'),
    ('artifact_seal',           'covered',     'the seal over an artifact, written with the tool_run that produced it', '13'),
    -- 023 scheduler
    ('validation_queue',        'derived',     'work still to do; rebuilt from the rows that emit, which is what resume does', '08'),
    ('report_queue',            'derived',     'work still to do; rebuilt from findings, which emit', '11'),
    -- 024 secrets
    ('secret_kek',              'bookkeeping', 'key material; never epistemic state and never in an event', '15'),
    ('secret_dek',              'bookkeeping', 'key material; never epistemic state and never in an event', '15'),
    ('secret_access_log',       'audit',       'the access trail is the record; an event would copy it into a table agents can read', '15'),
    -- 025 transport claims
    ('interception_cas',        'reference',   'the CA set the proxy may present, changed only by migration or operator', '24'),
    ('transport_makeability',   'reference',   'what a transport claim can be made of, changed only by migration', '24'),
    -- 026 human control surface
    ('verdicts',                'audit',       'the human answer to a pending_decision; decision.answered is the event, this row is its content', '28'),
    ('proposals',               'audit',       'the runtime record of having received a proposal; the commit it becomes is what emits', '28'),
    ('proposal_drops',          'audit',       'a proposal that failed provenance; agent.refused is the event, this row is its content', '28'),
    ('decision_notifications',  'audit',       'outbound notification attempts; decision.requested is the event', '28'),
    ('notification_channels',   'reference',   'operator channel config, changed only by migration or operator', '28'),
    ('redaction_failure',       'audit',       'a redaction that did not hold; the row is the record and must not be re-emitted into a readable table', '28'),
    -- 033: this migration's own registry (section D)
    ('state_read_surface',      'reference',   'the agent read surface, changed only by migration', '33');

-- ===========================================================================
-- B -- immutability that does not block the purge
-- ===========================================================================
-- 013 already solved this: `reject_mutation_unless_purging()` raises on UPDATE
-- and on DELETE, except a DELETE while `app.purging` is on. 021 wrote a fresh
-- guard function instead of reusing it, so a program that has ever had a scope
-- version cannot be purged -- and a program with no scope version is a program
-- nothing may be sent to, so in practice: no program can be purged.
--
-- This is the second time the defect has shipped. Ticket 07 fixed it once in
-- 013 and 011 reintroduced it; 021 reintroduced it again. Fixing it a third
-- time is not the interesting half -- section F is.

DROP TRIGGER scope_versions_immutable ON program_scope_versions;
CREATE TRIGGER scope_versions_immutable
    BEFORE UPDATE OR DELETE ON program_scope_versions
    FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_purging();
ALTER TABLE program_scope_versions ENABLE ALWAYS TRIGGER scope_versions_immutable;

DROP FUNCTION scope_versions_are_immutable();

-- ===========================================================================
-- C -- a session is unbound, not deleted
-- ===========================================================================
-- `agent_sessions` is a curated emitter: `session.bound` names the row as its
-- subject. `resume_program()` and `park_for_human()` both DELETE the row, so
-- every resume and every park leaves `session.bound` events pointing at
-- nothing -- which `check_event_log_integrity()` reports as `event_without_row`
-- and which is exactly the accounting the log exists to provide.
--
-- The deletion was reaching for the right thing: after a resume the binding
-- must not resolve a hook call to a finished run. That is a *predicate*, not a
-- deletion. `unbound_at` says it, the partial unique index keeps "one live
-- binding per (program, SDK session, SDK agent)" true, and the row survives to
-- account for its event.
--
-- Runtime contract change: hook resolution must select on
-- `unbound_at IS NULL`. Recorded in the ticket-13 answer's terms in the
-- ticket-33 answer.

ALTER TABLE agent_sessions ADD COLUMN unbound_at timestamptz;

ALTER TABLE agent_sessions
    DROP CONSTRAINT agent_sessions_program_id_session_id_sdk_agent_id_key;
CREATE UNIQUE INDEX agent_sessions_live_binding_idx
    ON agent_sessions (program_id, session_id, sdk_agent_id)
 WHERE unbound_at IS NULL;

COMMENT ON COLUMN agent_sessions.unbound_at IS
  'Set instead of deleting the row: the row is the subject of a session.bound event, and deleting it orphans the event. Hook resolution must filter on unbound_at IS NULL.';

-- Both functions are long and neither is this ticket's to rewrite, so the
-- statement is rewritten in place and the migration asserts it hit exactly the
-- two definitions it expected. A textual patch that silently matched nothing
-- would be worse than no patch; this one fails the migration.
DO $$
DECLARE r record; n integer := 0; src text; patched text;
BEGIN
    FOR r IN SELECT p.oid, p.proname FROM pg_proc p
              JOIN pg_namespace ns ON ns.oid = p.pronamespace
             WHERE ns.nspname = 'public'
               AND p.prosrc LIKE '%DELETE FROM agent_sessions%'
    LOOP
        src := pg_get_functiondef(r.oid);
        patched := replace(src,
            'DELETE FROM agent_sessions s',
            'UPDATE agent_sessions s SET unbound_at = now()');
        -- the WHERE clauses already select the rows to unbind; only rows still
        -- live may be unbound, or a second resume would re-stamp them
        patched := replace(patched,
            'UPDATE agent_sessions s SET unbound_at = now() WHERE s.agent_run_id = tr.agent_run_id;',
            'UPDATE agent_sessions s SET unbound_at = now() WHERE s.agent_run_id = tr.agent_run_id AND s.unbound_at IS NULL;');
        patched := replace(patched,
            'WHERE r.id = s.agent_run_id AND r.finished_at IS NOT NULL);',
            'WHERE r.id = s.agent_run_id AND r.finished_at IS NOT NULL) AND s.unbound_at IS NULL;');
        IF patched = src THEN
            RAISE EXCEPTION 'ticket 33: agent_sessions patch did not apply to %', r.proname;
        END IF;
        EXECUTE patched;
        n := n + 1;
    END LOOP;
    IF n <> 2 THEN
        RAISE EXCEPTION 'ticket 33: expected 2 functions deleting agent_sessions, patched %', n;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace ns ON ns.oid = p.pronamespace
                WHERE ns.nspname = 'public' AND p.prosrc LIKE '%DELETE FROM agent_sessions%') THEN
        RAISE EXCEPTION 'ticket 33: a function still deletes agent_sessions rows';
    END IF;
END $$;

-- ===========================================================================
-- D -- the agent read surface is a registry, not a grant
-- ===========================================================================
-- 020 wrote `GRANT SELECT ON entities, ..., receipts, ... TO rk2_state` -- 26
-- relation-level grants. A relation grant is not a list of columns, it is a
-- subscription to whatever columns the table ever grows. 021 added
-- `programs.scope_version` and `receipts.scope_version`, 025 added three more
-- receipt columns, and every one of them reached the agent-facing connection
-- without anybody deciding it should. 022 and 025 both noticed for their own
-- table and re-granted by name, which fixes two tables and leaves the rule
-- unstated.
--
-- The rule, stated: **rk2_state holds column grants only.** The readable
-- surface is the contents of `state_read_surface`, and a column that is not a
-- row in that table is not readable however the handler is written. Adding a
-- column is then a schema change; publishing it to the agent is a second,
-- separate change that shows up in a diff as a row.
--
-- The seed is the surface the corpus already exposes -- this migration changes
-- *how* the surface is held, not what is in it today. What it changes is the
-- next migration.

CREATE TABLE state_read_surface (
    table_name  text NOT NULL,
    column_name text NOT NULL,
    added_by    text NOT NULL DEFAULT '33',
    PRIMARY KEY (table_name, column_name)
);

COMMENT ON TABLE state_read_surface IS
  'The agent-facing read surface, column by column. rk2_state holds no relation-level grant: this table is the grant. Enforced by check_state_grants(), applied by apply_state_grants().';

INSERT INTO state_read_surface (table_name, column_name, added_by)
SELECT c.relname, a.attname, '33-seed'
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
  JOIN pg_attribute a ON a.attrelid = c.oid
 WHERE n.nspname = 'public' AND c.relkind = 'r'
   AND a.attnum > 0 AND NOT a.attisdropped
   AND has_column_privilege('rk2_state', c.oid, a.attnum, 'SELECT');

-- Now take the relation grants away. After this statement rk2_state holds no
-- table-level privilege on anything in `public`.
DO $$
DECLARE t text;
BEGIN
    FOR t IN SELECT c.relname FROM pg_class c
              JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname = 'public' AND c.relkind IN ('r','v','m')
             ORDER BY c.relname
    LOOP
        EXECUTE format('REVOKE ALL ON TABLE public.%I FROM rk2_state', t);
    END LOOP;
END $$;

-- Additive, idempotent, and deliberately *not* a revoke: the runner grants what
-- the registry names and the checker refuses anything held beyond it. A
-- finalizer that revoked would silently undo an over-grant instead of failing
-- the run, and an over-grant is precisely the thing that has to be seen.
CREATE FUNCTION apply_state_grants() RETURNS integer
LANGUAGE plpgsql AS $$
DECLARE r record; n integer := 0;
BEGIN
    FOR r IN
        SELECT s.table_name, string_agg(quote_ident(s.column_name), ', ' ORDER BY s.column_name) AS cols
          FROM state_read_surface s
          JOIN pg_class c ON c.relname = s.table_name
          JOIN pg_namespace ns ON ns.oid = c.relnamespace AND ns.nspname = 'public'
          JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = s.column_name
                             AND a.attnum > 0 AND NOT a.attisdropped
         WHERE NOT has_column_privilege('rk2_state', c.oid, a.attnum, 'SELECT')
         GROUP BY s.table_name
    LOOP
        EXECUTE format('GRANT SELECT (%s) ON public.%I TO rk2_state', r.cols, r.table_name);
        n := n + 1;
    END LOOP;
    RETURN n;
END $$;

CREATE FUNCTION check_state_grants()
RETURNS TABLE (problem text, object text, detail text)
LANGUAGE sql STABLE AS $$
    -- 1. any relation-level privilege at all. has_table_privilege ignores
    --    column grants, so a true here is exactly the 020 shape.
    SELECT 'state_holds_relation_grant', c.relname,
           'rk2_state holds relation-level ' || p.priv || '; the read surface is state_read_surface'
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      CROSS JOIN (VALUES ('SELECT'),('INSERT'),('UPDATE'),('DELETE'),
                         ('TRUNCATE'),('REFERENCES'),('TRIGGER')) AS p(priv)
     WHERE n.nspname = 'public' AND c.relkind IN ('r','v','m','p')
       AND has_table_privilege('rk2_state', c.oid, p.priv)
  UNION ALL
    -- 2. any write privilege, at column level
    SELECT 'state_holds_write_grant', c.relname || '.' || a.attname,
           'rk2_state holds ' || p.priv || '; the agent connection writes nothing'
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
      CROSS JOIN (VALUES ('INSERT'),('UPDATE'),('REFERENCES')) AS p(priv)
     WHERE n.nspname = 'public' AND c.relkind IN ('r','v','m','p')
       AND has_column_privilege('rk2_state', c.oid, a.attnum, p.priv)
  UNION ALL
    -- 3. readable without a registry row -- what a new column would be
    SELECT 'state_reads_unregistered_column', c.relname || '.' || a.attname,
           'readable by rk2_state with no state_read_surface row'
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
      JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
     WHERE n.nspname = 'public' AND c.relkind IN ('r','v','m','p')
       AND has_column_privilege('rk2_state', c.oid, a.attnum, 'SELECT')
       AND NOT EXISTS (SELECT 1 FROM state_read_surface s
                        WHERE s.table_name = c.relname AND s.column_name = a.attname)
  UNION ALL
    -- 4. registered and not granted -- the finalizer did not run
    SELECT 'state_missing_registered_column', s.table_name || '.' || s.column_name,
           'state_read_surface names it but rk2_state cannot read it; run migrate.sh up'
      FROM state_read_surface s
      JOIN pg_class c ON c.relname = s.table_name
      JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
      JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = s.column_name
                         AND a.attnum > 0 AND NOT a.attisdropped
     WHERE NOT has_column_privilege('rk2_state', c.oid, a.attnum, 'SELECT')
  UNION ALL
    -- 5. registry rows that name nothing -- a rename or a typo
    SELECT 'state_surface_names_missing_object', s.table_name || '.' || s.column_name,
           'state_read_surface row with no such table or column'
      FROM state_read_surface s
     WHERE NOT EXISTS (
        SELECT 1 FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
          JOIN pg_attribute a ON a.attrelid = c.oid AND a.attname = s.column_name
                             AND a.attnum > 0 AND NOT a.attisdropped
         WHERE c.relname = s.table_name)
$$;

-- ===========================================================================
-- E -- RLS coverage is an end-of-run invariant
-- ===========================================================================
-- 020 swept every table that then had a `program_id` and gave each one RLS and
-- two policies. 021 through 026 added twelve more program-scoped tables. They
-- are covered today only because each of those migrations happened to repeat
-- the sweep -- six copies of the same loop, and the seventh author is the
-- defect. `apply_state_rls()` is that loop, once, called by the runner after
-- the last migration; `check_rls_coverage()` is what makes forgetting visible
-- instead of silent.

CREATE FUNCTION apply_state_rls() RETURNS integer
LANGUAGE plpgsql AS $$
DECLARE t text; n integer := 0;
BEGIN
    FOR t IN
        SELECT c.relname FROM pg_class c
          JOIN pg_namespace ns ON ns.oid = c.relnamespace
         WHERE ns.nspname = 'public' AND c.relkind = 'r'
           AND EXISTS (SELECT 1 FROM pg_attribute a
                        WHERE a.attrelid = c.oid AND a.attname = 'program_id'
                          AND a.attnum > 0 AND NOT a.attisdropped)
           AND c.relname NOT IN (SELECT table_name FROM program_global_tables)
         ORDER BY c.relname
    LOOP
        IF NOT (SELECT relrowsecurity FROM pg_class c
                 JOIN pg_namespace ns ON ns.oid = c.relnamespace
                WHERE ns.nspname = 'public' AND c.relname = t) THEN
            EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
            n := n + 1;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_policy p WHERE p.polrelid = format('public.%I', t)::regclass
                        AND p.polname = t || '_rk2_state') THEN
            EXECUTE format(
                'CREATE POLICY %I ON public.%I AS PERMISSIVE FOR ALL TO rk2_state '
                'USING (program_id = rk2_program()) WITH CHECK (program_id = rk2_program())',
                t || '_rk2_state', t);
            n := n + 1;
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_policy p WHERE p.polrelid = format('public.%I', t)::regclass
                        AND p.polname = t || '_rk2_runtime') THEN
            EXECUTE format(
                'CREATE POLICY %I ON public.%I AS PERMISSIVE FOR ALL TO rk2_runtime '
                'USING (true) WITH CHECK (true)', t || '_rk2_runtime', t);
            n := n + 1;
        END IF;
    END LOOP;
    RETURN n;
END $$;

CREATE FUNCTION check_rls_coverage()
RETURNS TABLE (problem text, object text, detail text)
LANGUAGE sql STABLE AS $$
    WITH scoped AS (
        SELECT c.oid, c.relname, c.relrowsecurity
          FROM pg_class c
          JOIN pg_namespace ns ON ns.oid = c.relnamespace
         WHERE ns.nspname = 'public' AND c.relkind = 'r'
           AND EXISTS (SELECT 1 FROM pg_attribute a
                        WHERE a.attrelid = c.oid AND a.attname = 'program_id'
                          AND a.attnum > 0 AND NOT a.attisdropped)
           AND c.relname NOT IN (SELECT table_name FROM program_global_tables)
    )
    SELECT 'rls_disabled', s.relname, 'program-scoped table with row level security off'
      FROM scoped s WHERE NOT s.relrowsecurity
  UNION ALL
    SELECT 'rls_policy_missing', s.relname, 'no policy ' || s.relname || '_rk2_state'
      FROM scoped s
     WHERE NOT EXISTS (SELECT 1 FROM pg_policy p
                        WHERE p.polrelid = s.oid AND p.polname = s.relname || '_rk2_state')
  UNION ALL
    SELECT 'rls_policy_missing', s.relname, 'no policy ' || s.relname || '_rk2_runtime'
      FROM scoped s
     WHERE NOT EXISTS (SELECT 1 FROM pg_policy p
                        WHERE p.polrelid = s.oid AND p.polname = s.relname || '_rk2_runtime')
  UNION ALL
    -- The inverse mistake: scoping a shared table *by program*. 017 says a
    -- program_global_table is shared across programs and has no program_id to
    -- key on, so a policy calling rk2_program() there either never matches or
    -- matches a column that does not mean what it says. Note this is not the
    -- same as having a policy at all -- `artifacts` deliberately has one, and
    -- it scopes by reachability through artifact_refs, which is the shape 020
    -- reached for precisely because program_id was unavailable.
    SELECT 'rls_global_table_scoped_by_program', c.relname,
           'policy ' || p.polname || ' on a program_global_table calls rk2_program()'
      FROM pg_class c
      JOIN pg_namespace ns ON ns.oid = c.relnamespace AND ns.nspname = 'public'
      JOIN pg_policy p ON p.polrelid = c.oid
     WHERE c.relname IN (SELECT table_name FROM program_global_tables)
       AND coalesce(pg_get_expr(p.polqual, p.polrelid), '') LIKE '%rk2_program()%'
  UNION ALL
    -- RLS is off for the table owner unless FORCE is set, and rk2_owner is not
    -- a connection anything runs on; but a superuser-owned scoped table would
    -- read across programs for rk2_state too, so name it
    SELECT 'rls_table_owner_bypasses', s.relname,
           'owned by ' || pg_get_userbyid(c.relowner) || ', not rk2_owner'
      FROM scoped s JOIN pg_class c ON c.oid = s.oid
     WHERE pg_get_userbyid(c.relowner) <> 'rk2_owner'
$$;

-- ===========================================================================
-- F -- a purge that a later migration cannot block
-- ===========================================================================
-- Section B fixed the third instance of one defect. This is what makes a fourth
-- impossible to ship quietly: every BEFORE DELETE row trigger on a
-- program-scoped table must run a function that consults `app.purging`. 013's
-- `reject_mutation_unless_purging()` does; 021's replacement did not, and
-- nothing said so.

CREATE FUNCTION check_purge_reachability()
RETURNS TABLE (problem text, object text, detail text)
LANGUAGE sql STABLE AS $$
    SELECT 'delete_trigger_not_purge_aware',
           c.relname || '.' || t.tgname,
           'BEFORE DELETE trigger runs ' || p.proname || '(), whose body never reads app.purging; a program carrying a row here cannot be purged'
      FROM pg_trigger t
      JOIN pg_class c ON c.oid = t.tgrelid
      JOIN pg_namespace ns ON ns.oid = c.relnamespace AND ns.nspname = 'public'
      JOIN pg_proc p ON p.oid = t.tgfoid
     WHERE NOT t.tgisinternal
       AND (t.tgtype & 2) = 2          -- BEFORE
       AND (t.tgtype & 8) = 8          -- DELETE
       AND (t.tgtype & 1) = 1          -- ROW
       AND EXISTS (SELECT 1 FROM pg_attribute a
                    WHERE a.attrelid = c.oid AND a.attname = 'program_id'
                      AND a.attnum > 0 AND NOT a.attisdropped)
       AND p.prosrc NOT LIKE '%app.purging%'
$$;

-- ===========================================================================
-- G -- the tables 017's own checker refuses, which nothing was running
-- ===========================================================================
-- Consolidation's own finding, and it is not one of the four the ticket named:
-- `check_program_isolation()` reports six problems on the assembled corpus.
-- Nobody saw them because 017 asserts its rule *inside migration 017* and no
-- later migration re-asserts it. Five tables added after 017 are neither
-- program-scoped nor declared global, and one program-scoped table has a
-- non-uuid unique namespace.
--
-- Five are genuinely global and just never said so:
INSERT INTO program_global_tables (table_name, reason) VALUES
    ('secret_kek',         'root key material; one per installation, not per program'),
    ('secret_dek',         'data keys, keyed by (scope_kind, scope_id); the scope is the program when it is one'),
    ('artifact_seal',      'seals a content-addressed artifact, and artifacts are themselves global'),
    ('redaction_failure',  'names an artifact sha, and artifacts are global; the row must survive a program purge because it records that a redaction did not hold'),
    ('event_table_exempt', 'corpus-wide emission policy'),
    ('state_read_surface', 'corpus-wide read surface');

-- And the sixth: `secret_access_log` is program-scoped and its primary key is
-- a bigserial. 017's rule 4 says a unique namespace on a program-scoped table
-- must be keyed by program_id or by a uuid, because every id in this schema is
-- a uuidv7 and a sequence is a second, global namespace living inside a scoped
-- table. The table is empty at migration time and nothing references it.
ALTER TABLE secret_access_log DROP CONSTRAINT secret_access_log_pkey;
ALTER TABLE secret_access_log DROP COLUMN id;
ALTER TABLE secret_access_log ADD COLUMN id uuid NOT NULL DEFAULT uuidv7();
ALTER TABLE secret_access_log ADD PRIMARY KEY (id);

-- Same class, different registry: 024 added three foreign keys with a delete
-- action and registered none of them, so ticket 07's rule ("no FK outside
-- purge_cascade_edges may cascade") had three exceptions nothing declared.
-- Each action is the right one; what was missing is the declaration, and with
-- it the sentence saying what a purge leaves behind.
INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('artifact_seal',     'sha256',
     'ON DELETE CASCADE to artifacts: a seal describes one blob and is meaningless without it'),
    ('redaction_failure', 'artifact_sha',
     'ON DELETE SET NULL: the artifact may go, the record that a redaction did not hold may not'),
    ('secret_access_log', 'program_id',
     'ON DELETE SET NULL: a program purge forgets whose access it was and keeps that an access happened');

-- ===========================================================================
-- H -- every checker in the corpus runs at the end of every run
-- ===========================================================================
-- The four defects in this ticket, and the six isolation problems above, share
-- one cause: a migration writes an assertion, calls it once inside itself, and
-- nothing calls it again. Twelve such checkers exist across the corpus --
-- ticket 06's receipt integrity, 07's event log integrity, 08's scheduler
-- closure, 12's state access, 13's hook provenance, 24's transport claims, 28's
-- control surface, 34's role/kind mapping, 35's program isolation, and the
-- three this migration adds. Nine of them had no caller after their own
-- migration committed.
--
-- This is the registry, and `./migrate.sh up` runs all of it after the last
-- migration. A check that is registered is a check that keeps being true.

CREATE TABLE standing_checks (
    name         text PRIMARY KEY,
    query        text NOT NULL,   -- returns zero rows exactly when it holds
    owner_ticket text NOT NULL,
    note         text NOT NULL
);

COMMENT ON TABLE standing_checks IS
  'Every invariant the corpus asserts, run at the end of every migrate.sh up. A migration that adds a check_ function and no row here fails check_state_grants''s sibling rule below.';

INSERT INTO standing_checks (name, query, owner_ticket, note) VALUES
    ('event_coverage',     'SELECT * FROM check_event_coverage()', '07',
     'every table emits or is classified exempt, and exactly one of the two'),
    ('event_log_integrity','SELECT * FROM check_event_log_integrity(NULL)', '07',
     'every event has its row and every row of an emitting table has its event'),
    ('program_isolation',  'SELECT * FROM check_program_isolation()', '35',
     'no cross-program foreign key, no unscoped table, no global unique namespace'),
    ('role_kind_mapping',  'SELECT * FROM check_role_kind_mapping()', '34',
     'every role maps to task kinds that exist and every task kind has a role'),
    ('state_access',       'SELECT * FROM check_state_access()', '12',
     'the agent connection reads what it should and nothing else'),
    ('hook_provenance',    'SELECT * FROM check_hook_provenance()', '13',
     'every receipt traces to a hook call and every hook call to a session'),
    ('scheduler_closure',  'SELECT * FROM check_scheduler_closure()', '08',
     'no task is unreachable and no lane is starved by construction'),
    ('transport_claims',   'SELECT * FROM check_transport_claims(NULL)', '24',
     'every transport claim is makeable from what the proxy actually saw'),
    ('control_surface',    'SELECT * FROM check_control_surface()', '28',
     'every pending decision is answerable and every answer closes exactly once'),
    ('receipt_integrity',  'SELECT * FROM check_receipt_integrity(NULL, interval ''1 hour'')', '06',
     'no receipt is open past the horizon and no observation cites one that is'),
    ('rls_coverage',       'SELECT * FROM check_rls_coverage()', '33',
     'every program-scoped table has RLS and both policies'),
    ('state_grants',       'SELECT * FROM check_state_grants()', '33',
     'rk2_state holds column grants only, and exactly the registered ones'),
    ('purge_reachability', 'SELECT * FROM check_purge_reachability()', '33',
     'no BEFORE DELETE trigger on a scoped table can block a purge'),
    ('role_catalogue',     'SELECT * FROM check_role_catalogue() WHERE NOT ok', '33',
     'six roles, and none of the model-reachable ones can become rk2_human');

CREATE FUNCTION run_standing_checks()
RETURNS TABLE (name text, problems bigint, detail text)
LANGUAGE plpgsql STABLE AS $$
DECLARE r record; n bigint; d text;
BEGIN
    FOR r IN SELECT s.name, s.query FROM standing_checks s ORDER BY s.name LOOP
        EXECUTE format('SELECT count(*), left(coalesce(string_agg(x::text, ''; ''), ''''), 240) FROM (%s) x', r.query)
           INTO n, d;
        name := r.name; problems := n; detail := d;
        RETURN NEXT;
    END LOOP;
END $$;

CREATE FUNCTION assert_standing_checks() RETURNS void
LANGUAGE plpgsql AS $$
DECLARE r record; n integer := 0;
BEGIN
    FOR r IN SELECT * FROM run_standing_checks() WHERE problems > 0 LOOP
        RAISE WARNING 'standing check % FAILED (% problem(s)): %', r.name, r.problems, r.detail;
        n := n + 1;
    END LOOP;
    IF n > 0 THEN
        RAISE EXCEPTION 'standing checks: % of % failing', n, (SELECT count(*) FROM standing_checks)
          USING HINT = 'SELECT * FROM run_standing_checks()';
    END IF;
END $$;

-- The rule that keeps the registry honest. A migration 029 that writes
-- `check_foo()` and forgets the row gets told, at the end of the very run that
-- introduced it. Trigger functions are excluded by return type, and the two
-- parameterised checks the runner supplies arguments to are named here rather
-- than in a table because they are the runner's, not the corpus's.
CREATE FUNCTION check_check_registration()
RETURNS TABLE (problem text, object text, detail text)
LANGUAGE sql STABLE AS $$
    SELECT 'check_function_not_registered', p.proname,
           'a check_ function with no standing_checks row; register it or it stops being true'
      FROM pg_proc p
      JOIN pg_namespace n ON n.oid = p.pronamespace AND n.nspname = 'public'
     WHERE p.proname LIKE 'check\_%'
       AND p.prorettype <> 'trigger'::regtype
       AND p.proname NOT IN ('check_server_baseline','check_runtime_connection',
                             'check_check_registration')
       AND NOT EXISTS (SELECT 1 FROM standing_checks s
                        WHERE s.query LIKE '%' || p.proname || '(%')
  UNION ALL
    SELECT 'registered_check_missing', s.name, 'standing_checks row naming no function'
      FROM standing_checks s
     WHERE NOT EXISTS (
        SELECT 1 FROM pg_proc p
          JOIN pg_namespace n ON n.oid = p.pronamespace AND n.nspname = 'public'
         WHERE s.query LIKE '%' || p.proname || '(%')
$$;

INSERT INTO standing_checks (name, query, owner_ticket, note) VALUES
    ('check_registration', 'SELECT * FROM check_check_registration()', '33',
     'every checker in the corpus is in this table');

INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('standing_checks', 'reference', 'the check registry, changed only by migration', '33');
INSERT INTO program_global_tables (table_name, reason) VALUES
    ('standing_checks', 'corpus-wide check registry');

-- Bring the two new invariants to true for the corpus as it stands. The runner
-- calls both again at the end of every run; calling them here is what makes
-- this migration self-contained if someone applies it by hand.
SELECT apply_state_rls();
SELECT apply_state_grants();

DO $$ BEGIN PERFORM assert_standing_checks(); END $$;
