-- ===========================================================================
-- Production harness 103 -- the composer's grant, corrected before it is wired
-- ===========================================================================
-- Ticket 103 wires six verbs downstream of a validated Finding, and one of the
-- six carries a second piece of work its own criterion got wrong. Criterion 5
-- says `compose_finding_report` "is owner-only, it has no grant to any role".
-- The absence of a `GRANT` line in
-- `20260820T000000Z__a_report_is_a_projection_of_what_holds.sql` is not the
-- absence of a grant, and the error is a wider surface rather than a narrower
-- one:
--
--   * that migration contains no `GRANT` and no `REVOKE` at all;
--   * `0029_roles_and_grants.sql:103-104` sets `ALTER DEFAULT PRIVILEGES FOR
--     ROLE rk2_owner IN SCHEMA public GRANT EXECUTE ON FUNCTIONS TO
--     rk2_runtime`, a standing rule over every function created after it;
--   * PostgreSQL's own default `EXECUTE` to `PUBLIC` was never revoked.
--
-- Measured off `pg_proc.proacl` the ACL reads
-- `{=X/rk2_owner,rk2_owner=X/rk2_owner,rk2_runtime=X/rk2_owner}` -- the leading
-- `=X/` is PUBLIC -- and `docs/research/wiring/23-database-wiring.md:679` had it
-- right as "PUBLIC, rk2_owner, rk2_runtime". Every sibling verb in this group
-- carries an explicit `REVOKE ALL ... FROM PUBLIC`
-- (`20260816T000000Z...:2015`, `:2018`, `:2019`; `20260817T000000Z...:1109`;
-- `20260818T000000Z...:911-912`). This one had none.
--
-- So the work is done in this order on purpose: the surface is narrowed here,
-- and only then is the verb served to a model. A Contract wired over a PUBLIC
-- grant would be a tool whose authority is wider than the roster describing it,
-- and the roster is the document every other check in this tree is written
-- against.

REVOKE ALL ON FUNCTION compose_finding_report(uuid, jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION compose_finding_report(uuid, jsonb) TO rk2_runtime;

COMMENT ON FUNCTION compose_finding_report(uuid, jsonb) IS
  'Ticket 42: write the impact and reproduction halves of a Finding, which 034 designed, made hard blockers of, and gave no writer. Takes the hunter''s judgement -- which effects, witnessed by which observations, described by which mechanism sentences citing which rows -- and lets 034''s own triggers rule on it, immediately rather than at commit. Replaces any previous composition. Returns the hard blockers that remain. Ticket 103 closed it to PUBLIC before serving it: it is the runtime''s, like every sibling verb in its group.';

-- 066's registry. A verb closed to PUBLIC and still executable by the runtime
-- needs a row saying why, and `check_runtime_privileges` is what would notice
-- if the grant above outlived the reason for it.
INSERT INTO runtime_verb_surface (verb, added_by, note) VALUES
    ('compose_finding_report(uuid, jsonb)',
     '103',
     'the writer of finding_effects and finding_chain_steps, which 034 designed, made hard report blockers of, and left with no writer; served as a Contract because which observation witnesses which effect is a judgement rather than a join');

-- ---------------------------------------------------------------------------
-- What this migration claims, asserted
-- ---------------------------------------------------------------------------
-- The point of the file is one bit of an ACL, so the file checks that bit
-- rather than trusting that the statement above meant what it said. Both
-- directions: PUBLIC cannot reach it and the runtime still can, because a
-- REVOKE that took the runtime's grant with it would break the Contract this
-- was written to make safe.

DO $$
BEGIN
    IF has_function_privilege('public',
            'compose_finding_report(uuid, jsonb)'::regprocedure, 'EXECUTE') THEN
        RAISE EXCEPTION 'compose_finding_report is still executable by PUBLIC';
    END IF;
    IF NOT has_function_privilege('rk2_runtime',
            'compose_finding_report(uuid, jsonb)'::regprocedure, 'EXECUTE') THEN
        RAISE EXCEPTION 'compose_finding_report is no longer executable by the runtime';
    END IF;
END $$;
