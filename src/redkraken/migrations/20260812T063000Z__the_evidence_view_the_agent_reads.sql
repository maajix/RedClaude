-- ===========================================================================
-- Production harness 19 -- the evidence view returns to the read surface, and
-- three views that never had a reader leave it
-- ===========================================================================
-- 020 built six agent-facing views and granted `rk2_state` SELECT on each.
-- 030 turned relation grants into a per-column registry: section D revoked
-- every relation-level grant the role held on relkind 'r', 'v' and 'm', and
-- seeded `state_read_surface` from `relkind = 'r'` only. Tables kept their
-- privileges through the registry; views lost theirs and got no registry row,
-- so all six became unreadable to the one role that exists to read them. The
-- artifact migration noticed for `v_artifacts` and re-registered it. Nobody
-- noticed for the rest, because ticket 05 records the reason: "the six
-- agent-facing v_* views 020 built ... still have no reader anywhere in the
-- harness", and it left the question of which survive to this ticket.
--
-- This is that answer, and it is two answers.
--
-- `v_evidence` survives and is registered. It is the one shape `v_records` does
-- not carry: an evidence edge is a Hypothesis or a Finding, an Observation, a
-- polarity and a role, and there is no single row it is a projection of. The
-- packet's evidence section reads it, so from this migration on the grant and
-- the reader arrive together instead of one preceding the other by two tickets.
--
-- `v_surface`, `v_hypotheses` and `v_receipts` do not survive. `v_records`
-- answers all three -- entity, hypothesis and receipt are three of its kinds --
-- and it answers them with the revision and digest a bounded read has to report
-- and those views have no column for. Keeping them would leave three relations
-- that look like the agent read surface, are not granted to the agent role, and
-- return a record shape no handler serves. A view nobody reads was cheaper than
-- a view removed from under a ticket that wanted it; this is the ticket, and it
-- does not want them.
--
-- `v_validation_packet` is untouched and stays off the surface. It is the
-- validator's read, `validate.judge` is not a group this runtime serves yet,
-- and the role that will read it is not `rk2_state`. Registering it here would
-- be a grant issued for a handler that does not exist.
-- ===========================================================================


-- ---------------------------------------------------------------------------
-- 1. The three superseded projections
-- ---------------------------------------------------------------------------
-- No dependents: nothing in the corpus and nothing in the harness selects from
-- any of them, which is why `DROP VIEW` rather than `DROP VIEW ... CASCADE` --
-- a cascade here would be permission to remove something this file has not
-- accounted for.

DROP VIEW v_surface;
DROP VIEW v_hypotheses;
DROP VIEW v_receipts;

-- Registry rows for a relation that no longer exists fail `check_state_grants`
-- rule 5. 030 never wrote one for these three, so this deletes nothing today;
-- it is here so that the file is correct applied to a database where an earlier
-- hand-repair did write them.
DELETE FROM state_read_surface
 WHERE table_name IN ('v_surface', 'v_hypotheses', 'v_receipts');


-- ---------------------------------------------------------------------------
-- 2. The evidence view, column by column
-- ---------------------------------------------------------------------------
-- Every column, because every column is a label, a vocabulary term or a
-- summary, and the view carries no uuid and no free-form payload by
-- construction. It is `security_invoker`, so this grant only opens what the
-- caller may already read through the base tables: `hypothesis_evidence`,
-- `hypotheses`, `findings`, `finding_evidence`, `observations`, `receipts` and
-- `tool_runs` are each registered, each row-level-scoped to
-- `rk2_program()`, and the view inherits both facts rather than restating them.

INSERT INTO state_read_surface (table_name, column_name, added_by) VALUES
    ('v_evidence', 'hypothesis_label',  'ph2-19'),
    ('v_evidence', 'finding_label',     'ph2-19'),
    ('v_evidence', 'observation_label', 'ph2-19'),
    ('v_evidence', 'polarity',          'ph2-19'),
    ('v_evidence', 'role',              'ph2-19'),
    ('v_evidence', 'kind',              'ph2-19'),
    ('v_evidence', 'summary',           'ph2-19'),
    ('v_evidence', 'provenance_kind',   'ph2-19'),
    ('v_evidence', 'receipt_label',     'ph2-19'),
    ('v_evidence', 'tool_run_label',    'ph2-19');

SELECT apply_state_grants();


-- ---------------------------------------------------------------------------
-- 3. The gate
-- ---------------------------------------------------------------------------
-- Both directions. A registered column the role cannot read is the defect this
-- file exists to fix, and a surviving view is what stops the drop above from
-- being written as three lines and believed.

DO $$
DECLARE missing text;
BEGIN
    SELECT string_agg(s.column_name, ', ' ORDER BY s.column_name) INTO missing
      FROM state_read_surface s
     WHERE s.table_name = 'v_evidence'
       AND NOT has_column_privilege('rk2_state', 'public.v_evidence', s.column_name, 'SELECT');
    IF missing IS NOT NULL THEN
        RAISE EXCEPTION 'rk2_state cannot read v_evidence columns: %', missing;
    END IF;

    IF EXISTS (
        SELECT 1 FROM pg_views
         WHERE schemaname = 'public'
           AND viewname IN ('v_surface', 'v_hypotheses', 'v_receipts'))
    THEN
        RAISE EXCEPTION 'a superseded agent view is still defined';
    END IF;
END $$;
