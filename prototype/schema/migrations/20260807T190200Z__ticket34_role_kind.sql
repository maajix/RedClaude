-- ---------------------------------------------------------------------------
-- 019_ticket34_role_kind.sql   (ticket 34)
--
-- GENERATED FILE. Source: `prototype/agent-roster/roles.yaml` at 2fc3354 (ticket 11's
-- roster), compiled by `prototype/role-kind/gen_019.py`. Edit the roster, not
-- this file; `prototype/role-kind/run_all.sh` regenerates it and fails if the
-- committed copy differs, so the schema and the roster cannot drift.
--
-- The schema carried two vocabularies for one thing -- `agent_runs.role` and
-- `tasks.kind` -- with nothing joining them, so every role could execute every
-- kind and the cost window had to group by kind alone. Both vocabularies become
-- tables, the mapping becomes a third with `UNIQUE (kind)` on it, and three
-- foreign keys make a run's kind the intersection of what its role was granted
-- and what its task actually is.
-- ---------------------------------------------------------------------------

-- ===========================================================================
-- 1. The two vocabularies, as tables, and the mapping between them
-- ===========================================================================

CREATE TABLE roles (
    role                     text PRIMARY KEY,
    runs_as                  text NOT NULL
                             CHECK (runs_as IN ('session','subagent','renderer')),
    invocable_by             text[] NOT NULL,
    -- true iff the roster gives this role at least one task kind. It is the
    -- schema's way of saying "the orchestrator picks tasks, it never holds one".
    executes_tasks           boolean NOT NULL,
    -- concurrency is a property of the agent, not of the lane (ticket 34, D1)
    max_concurrent           smallint NOT NULL CHECK (max_concurrent >= 1),
    clamp_to_identity_leases boolean NOT NULL,
    UNIQUE (role, executes_tasks),
    UNIQUE (role, runs_as),
    -- a renderer holds no session and drives no identity
    CHECK (runs_as <> 'renderer' OR NOT clamp_to_identity_leases)
);

COMMENT ON TABLE roles IS
  'The six roles of ticket 11''s roster, compiled from roles.yaml. Global: one roster for the harness, so a program cannot grant a role something another program forbids.';

INSERT INTO roles (role, runs_as, invocable_by, executes_tasks,
                   max_concurrent, clamp_to_identity_leases) VALUES
    ('orchestrator', 'session', ARRAY['runtime']::text[], false, 1, false),
    ('recon', 'subagent', ARRAY['orchestrator']::text[], true, 1, false),
    ('web_hunter', 'subagent', ARRAY['orchestrator']::text[], true, 2, true),
    ('js_analyst', 'subagent', ARRAY['orchestrator']::text[], true, 2, false),
    ('validator', 'session', ARRAY['runtime']::text[], true, 1, false),
    ('reporter', 'renderer', ARRAY['runtime']::text[], true, 1, false);

CREATE TABLE task_kinds (
    kind text PRIMARY KEY
);

COMMENT ON TABLE task_kinds IS
  'The task-kind vocabulary of ticket 08. A kind exists because a role executes it: this table is generated from the roster''s task_kinds lists, so a kind nobody can run cannot be added by accident.';

INSERT INTO task_kinds (kind) VALUES ('recon'), ('hunt'), ('analyze'), ('validate'), ('report');

CREATE TABLE role_task_kinds (
    role text NOT NULL REFERENCES roles(role),
    kind text NOT NULL REFERENCES task_kinds(kind),
    PRIMARY KEY (role, kind),
    -- The mapping is injective, and that is the load-bearing part: one kind is
    -- executed by exactly one role, so a lane cap and an agent cap are the same
    -- number and the cost window's "(role, kind)" grouping is well defined.
    UNIQUE (kind)
);

COMMENT ON TABLE role_task_kinds IS
  'role -> task kind. Total on the kind side (every kind has a role), injective (no kind has two), and empty for the orchestrator, which is the picker rather than a player.';

INSERT INTO role_task_kinds (role, kind) VALUES
    ('recon', 'recon'),
    ('web_hunter', 'hunt'),
    ('js_analyst', 'analyze'),
    ('validator', 'validate'),
    ('reporter', 'report');

INSERT INTO program_global_tables (table_name, reason) VALUES
    ('roles',           'the agent roster is compiled from one roles.yaml for the whole harness; a per-program roster would let one program grant a role a kind another forbids'),
    ('task_kinds',      'the scheduler''s task vocabulary, one per harness like transition_rules'),
    ('role_task_kinds', 'the mapping between the two; global for the same reason both sides are');

-- ===========================================================================
-- 2. `tasks.kind` stops being a CHECK and becomes a citation
-- ===========================================================================

ALTER TABLE tasks DROP CONSTRAINT tasks_kind_check;
ALTER TABLE tasks ADD CONSTRAINT tasks_kind_fk
    FOREIGN KEY (kind) REFERENCES task_kinds(kind);

-- referenced by agent_runs below; `id` alone is already unique, the other two
-- columns are here so a run can cite the task AND its kind AND its program in
-- one key, which is what pins a run's kind to the task it actually served.
ALTER TABLE tasks ADD CONSTRAINT tasks_id_kind_program_key
    UNIQUE (id, kind, program_id);

-- ===========================================================================
-- 3. `agent_runs.role` stops being a CHECK, and a run acquires a kind
-- ===========================================================================

-- ticket 32 (D16) found `agent_runs_role_check` rejecting role='hunt'. It also
-- said 'hunter' where the roster says 'web_hunter'; the roster wins.
ALTER TABLE agent_runs DROP CONSTRAINT agent_runs_role_check;
UPDATE agent_runs SET role = 'web_hunter' WHERE role = 'hunter';
ALTER TABLE agent_runs ADD CONSTRAINT agent_runs_role_fk
    FOREIGN KEY (role) REFERENCES roles(role);

ALTER TABLE agent_runs
    ADD COLUMN kind    text,
    ADD COLUMN runs_as text,
    -- not a column the runtime may set: a run executes a task iff it has one
    ADD COLUMN executes_tasks boolean
        GENERATED ALWAYS AS (task_id IS NOT NULL) STORED;

UPDATE agent_runs a SET kind = t.kind FROM tasks t WHERE t.id = a.task_id;
UPDATE agent_runs a SET runs_as = r.runs_as FROM roles r WHERE r.role = a.role;
ALTER TABLE agent_runs ALTER COLUMN runs_as SET NOT NULL;

-- (a) the kind must be one this role was granted.
ALTER TABLE agent_runs ADD CONSTRAINT agent_runs_role_kind_fk
    FOREIGN KEY (role, kind) REFERENCES role_task_kinds(role, kind);

-- (b) the kind must be the kind of the task actually served, and stay it: this
--     is NO ACTION, so rewriting `tasks.kind` under a live run is refused too.
--     program_id rides last so conkey[1] stays task_id for ticket 35's rule 3.
ALTER TABLE agent_runs ADD CONSTRAINT agent_runs_task_kind_fk
    FOREIGN KEY (task_id, kind, program_id)
    REFERENCES tasks (id, kind, program_id);

-- (c) (a) is MATCH SIMPLE, so a NULL kind would skip it. These two close that:
--     a role that executes tasks must have one, and a role that does not may
--     never have one -- which is the orchestrator staying outside the
--     vocabulary it picks from, as a constraint rather than as a convention.
ALTER TABLE agent_runs ADD CONSTRAINT agent_runs_kind_with_task
    CHECK ((task_id IS NULL) = (kind IS NULL));
ALTER TABLE agent_runs ADD CONSTRAINT agent_runs_executes_tasks_fk
    FOREIGN KEY (role, executes_tasks) REFERENCES roles(role, executes_tasks);

-- (d) a run cannot claim a shape its role does not have.
ALTER TABLE agent_runs ADD CONSTRAINT agent_runs_runs_as_fk
    FOREIGN KEY (role, runs_as) REFERENCES roles(role, runs_as);

-- ticket 11: the reporter is not an agent -- model:null, max_turns:0. A render
-- still needs a run row (the lane, the cost window and the event log all key on
-- one), so 'none' is the model of a role that has none, and a renderer that
-- spent tokens is a contradiction the schema refuses rather than a line in a doc.
ALTER TABLE agent_runs DROP CONSTRAINT agent_runs_effort_check;
ALTER TABLE agent_runs ADD CONSTRAINT agent_runs_effort_check
    CHECK (effort IN ('none','low','medium','high','xhigh','max'));
ALTER TABLE agent_runs ADD CONSTRAINT agent_runs_renderer_has_no_model
    CHECK ((runs_as = 'renderer') = (model = 'none' AND effort = 'none'));
ALTER TABLE agent_runs ADD CONSTRAINT agent_runs_renderer_spends_nothing
    CHECK (runs_as <> 'renderer'
           OR coalesce(input_tokens, 0) + coalesce(output_tokens, 0) = 0);

-- Ergonomics with teeth. The runtime writes a run's role and the task it
-- serves; the kind is derived rather than restated, and `runs_as` with it. The
-- trigger only fills a NULL, so a caller that states a kind is still checked by
-- both foreign keys above -- and ticket 06's lesson holds: a trigger is
-- forgeable from inside another trigger, a foreign key is not.
CREATE OR REPLACE FUNCTION agent_runs_derive_role_columns() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    IF NEW.kind IS NULL AND NEW.task_id IS NOT NULL THEN
        SELECT t.kind INTO NEW.kind FROM tasks t WHERE t.id = NEW.task_id;
    END IF;
    IF NEW.runs_as IS NULL THEN
        SELECT r.runs_as INTO NEW.runs_as FROM roles r WHERE r.role = NEW.role;
        -- A role outside the roster has no `runs_as` to derive, and the column
        -- is NOT NULL: without this the caller would be told about a null
        -- constraint rather than about the roster. Same refusal, named.
        IF NOT FOUND THEN
            RAISE EXCEPTION USING ERRCODE = 'foreign_key_violation',
                MESSAGE = format(
                    'agent_runs_role_fk: role %L is not in the roster',
                    NEW.role);
        END IF;
    END IF;
    RETURN NEW;
END $fn$;

CREATE TRIGGER agent_runs_derive_role_columns
    BEFORE INSERT ON agent_runs
    FOR EACH ROW EXECUTE FUNCTION agent_runs_derive_role_columns();

-- ===========================================================================
-- 4. Lanes: `max_slots` was the agent cap written down a second time
-- ===========================================================================

-- ticket 08 gave every lane its own max_slots and three of the five disagreed
-- with ticket 11's per-role concurrency cap (hunt 4 vs web_hunter 2, recon 2 vs
-- recon 1, validate 2 vs validator 1). With an injective mapping the two are one
-- number, so the lane stops carrying it. `min_slots` stays: an entitlement is
-- genuinely a property of the lane and it is what bounds starvation.
ALTER TABLE scheduler_lanes DROP COLUMN max_slots;
ALTER TABLE scheduler_lanes DROP CONSTRAINT scheduler_lanes_kind_check;
ALTER TABLE scheduler_lanes ADD CONSTRAINT scheduler_lanes_kind_fk
    FOREIGN KEY (kind) REFERENCES task_kinds(kind);
ALTER TABLE scheduler_lanes ADD CONSTRAINT scheduler_lanes_min_slots_nonneg
    CHECK (min_slots >= 0);

CREATE VIEW lane_capacity AS
    SELECT l.program_id, l.kind, m.role, l.min_slots,
           r.max_concurrent AS max_slots,
           r.clamp_to_identity_leases
      FROM scheduler_lanes l
      JOIN role_task_kinds m ON m.kind = l.kind
      JOIN roles r           ON r.role = m.role;

COMMENT ON VIEW lane_capacity IS
  'What the scheduler reads instead of scheduler_lanes. max_slots is the mapped role''s max_concurrent, so a lane cannot admit more work than the roster admits agents.';

-- ticket 11's `concurrency.global_subagents`: a cap across lanes, which a
-- per-kind table cannot express at all. It is policy, so it rides with the
-- other scheduler policy numbers and versions with them.
-- The DEFAULT stays: it is the roster's number, and a weights row written
-- without one should inherit the roster rather than fail.
ALTER TABLE scheduler_weights
    ADD COLUMN max_concurrent_subagents smallint NOT NULL DEFAULT 3
        CHECK (max_concurrent_subagents >= 1);

-- ===========================================================================
-- 5. The mapping as something a later migration has to survive
-- ===========================================================================

CREATE OR REPLACE FUNCTION check_role_kind_mapping()
RETURNS TABLE (problem text, detail text) LANGUAGE sql STABLE AS $fn$
    -- (a) totality on the kind side: a kind nobody may execute is a task the
    --     scheduler can create and never staff.
    SELECT 'kind_with_no_role'::text, k.kind
      FROM task_kinds k
     WHERE NOT EXISTS (SELECT 1 FROM role_task_kinds m WHERE m.kind = k.kind)
UNION ALL
    -- (b) injectivity, asserted rather than inherited from the unique index, so
    --     dropping the index is not enough to reopen the hole quietly.
    SELECT 'kind_with_two_roles', kind
      FROM role_task_kinds GROUP BY kind HAVING count(*) > 1
UNION ALL
    -- (c) `executes_tasks` agrees with the mapping it summarises.
    SELECT 'executes_tasks_disagrees_with_mapping', r.role
      FROM roles r
     WHERE r.executes_tasks
           <> EXISTS (SELECT 1 FROM role_task_kinds m WHERE m.role = r.role)
UNION ALL
    -- (d) every kind has a default lane, or the claim query silently skips it.
    SELECT 'kind_with_no_default_lane', k.kind
      FROM task_kinds k
     WHERE NOT EXISTS (SELECT 1 FROM scheduler_lanes l
                        WHERE l.kind = k.kind AND l.program_id IS NULL)
UNION ALL
    -- (e) an entitlement above the agent cap is a lane promising slots the
    --     roster will not spawn.
    SELECT 'lane_min_above_role_cap',
           coalesce(c.program_id::text, 'default') || ' ' || c.kind
      FROM lane_capacity c
     WHERE c.min_slots > c.max_slots
UNION ALL
    -- (f) belt and braces on the two foreign keys above: a run's kind is its
    --     task's kind, and only a role granted that kind holds it.
    SELECT 'run_kind_disagrees_with_task', a.id::text
      FROM agent_runs a JOIN tasks t ON t.id = a.task_id
     WHERE a.kind IS DISTINCT FROM t.kind
UNION ALL
    SELECT 'run_kind_not_granted_to_role', a.id::text
      FROM agent_runs a
     WHERE a.kind IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM role_task_kinds m
                        WHERE m.role = a.role AND m.kind = a.kind)
$fn$;

DO $$
DECLARE v text;
BEGIN
    SELECT string_agg(problem || ' ' || detail, '; ' ORDER BY problem, detail)
      INTO v FROM check_role_kind_mapping();
    IF v IS NOT NULL THEN
        RAISE EXCEPTION 'role/kind mapping is not closed after 019: %', v;
    END IF;
    RAISE NOTICE 'role/kind: check_role_kind_mapping() is silent';
END $$;

-- ticket 35's obligation: the isolation model still holds after this migration.
DO $$
DECLARE v text;
BEGIN
    SELECT string_agg(problem || ' ' || detail, '; ' ORDER BY problem, detail)
      INTO v FROM check_program_isolation();
    IF v IS NOT NULL THEN
        RAISE EXCEPTION 'program isolation is not closed after 019: %', v;
    END IF;
    RAISE NOTICE 'role/kind: check_program_isolation() is still silent';
END $$;

-- ticket 07's obligation: every trigger fires under session_replication_role.
DO $$
DECLARE r record;
BEGIN
    FOR r IN SELECT c.relname AS tbl, t.tgname
               FROM pg_trigger t
               JOIN pg_class c ON c.oid = t.tgrelid
              WHERE NOT t.tgisinternal
                AND c.relnamespace = 'public'::regnamespace
                AND t.tgenabled <> 'A'
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ALWAYS TRIGGER %I', r.tbl, r.tgname);
    END LOOP;
END $$;

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO rk2_runtime;
GRANT SELECT ON lane_capacity TO rk2_runtime;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO rk2_runtime;
