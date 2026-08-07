-- ===========================================================================
-- The migration nobody should write, written on purpose.
--
-- run_all.sh pass 8 copies this into migrations/ under a real timestamp name,
-- runs `./migrate.sh up`, and expects the run to end red. It is the only proof
-- that the standing checks are load-bearing: each one has to name its own
-- breakage in the same run that introduced it.
--
-- Four holes, one per invariant the corpus asserts:
--
--   1. a program-scoped table with no RLS and no policies
--        -> healed by apply_state_rls() in the finalizer, so rls_coverage is
--           expected to be SILENT. That is the point of a finalizer: the
--           author did not have to know.
--   2. no event_table_config and no event_table_exempt row for either table
--        -> event_coverage names both
--   3. a table with no program_id and no program_global_tables row
--        -> program_isolation names it
--   4. a BEFORE DELETE trigger whose function never reads app.purging
--        -> purge_reachability names it: any program with a row here would be
--           unpurgeable, which is the defect 021 shipped
--   5. a relation-level GRANT to rk2_state
--        -> state_grants names it: the 020 shape, which quietly subscribes the
--           agent connection to every column the table ever grows
-- ===========================================================================

CREATE TABLE drift_probe_scoped (
    id         uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    note       text
);

CREATE TABLE drift_probe_global (
    key   text PRIMARY KEY,
    value text
);

CREATE FUNCTION drift_probe_is_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'drift_probe_scoped is append-only';
END $$;

CREATE TRIGGER drift_probe_immutable
    BEFORE UPDATE OR DELETE ON drift_probe_scoped
    FOR EACH ROW EXECUTE FUNCTION drift_probe_is_immutable();

GRANT SELECT ON drift_probe_scoped TO rk2_state;
