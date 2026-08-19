-- Ticket 64: the Playbook catalogue leaves the agent's read surface.
--
-- Decision 15 says human-only material is excluded from the model projection
-- "by structure rather than heading heuristics", and `playbook.Projection` is
-- that structure in Python: there is no field a provenance line, a review date,
-- a status or a trigger fact could occupy. One layer down the same sentence was
-- not true. 032 published the catalogue to `rk2_state` by sweeping
-- `pg_attribute` over seven relations, ticket 45 added `playbooks.provenance`
-- and three columns beside it to that publication, and `apply_state_grants()`
-- turns every such row into a real column grant. A model reaching a connection
-- with the state role could therefore select the provenance the projection
-- refuses to carry, the status and expiry the runtime already ruled on, and the
-- reasons a Playbook was chosen for it -- which is the relitigation the
-- projection's docstring says it exists to prevent.
--
-- Nothing reads the catalogue on that connection. `execution._playbooks` reads
-- the selection as the runtime and hands the child a projection; `evaluation`
-- reads it as the runtime too; no agent-facing view names any of these six
-- relations, and each of those views is `security_invoker`, so a view could not
-- reach them on the model's behalf either. The grants have had no reader since
-- 032 wrote them. What they had was reach.
--
-- So the publication goes, all six catalogue relations of it, and the
-- projection becomes the whole of what a selected Playbook hands a model.
-- `surface_facts` stays where it is: it is what the runtime computed about the
-- target, not what a maintainer wrote about a Playbook.
--
-- The revoke is written out because `apply_state_grants()` is additive by
-- design. Deleting the rows is what stops the next run from granting these
-- columns again; it is not what ends a grant the role already holds, and rule 3
-- of `check_state_grants()` -- readable with no registry row -- is what the
-- difference between the two would otherwise show up as.

DELETE FROM state_read_surface
 WHERE table_name IN ('playbooks', 'playbook_triggers', 'playbook_outputs',
                      'playbook_skills', 'playbook_evidence', 'playbook_selections');

DO $$
DECLARE r record;
BEGIN
    FOR r IN
        SELECT c.relname,
               string_agg(quote_ident(a.attname), ', ' ORDER BY a.attname) AS cols
          FROM pg_class c
          JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
          JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0
                             AND NOT a.attisdropped
         WHERE c.relname IN ('playbooks', 'playbook_triggers', 'playbook_outputs',
                             'playbook_skills', 'playbook_evidence',
                             'playbook_selections')
           AND has_column_privilege('rk2_state', c.oid, a.attnum, 'SELECT')
         GROUP BY c.relname
    LOOP
        -- Relation first: while one is held every column answers `true`, and a
        -- column revoke against a relation-level grant takes nothing away.
        EXECUTE format('REVOKE ALL ON TABLE public.%I FROM rk2_state', r.relname);
        EXECUTE format('REVOKE SELECT (%s) ON public.%I FROM rk2_state', r.cols, r.relname);
    END LOOP;
END $$;


-- The gate. Written as a check on privilege rather than on the registry: the
-- registry is what a diff shows, and this is what the role can actually do.
DO $$
DECLARE held text;
BEGIN
    SELECT string_agg(c.relname || '.' || a.attname, ', ' ORDER BY c.relname, a.attname)
      INTO held
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
      JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0
                         AND NOT a.attisdropped
     WHERE c.relname IN ('playbooks', 'playbook_triggers', 'playbook_outputs',
                         'playbook_skills', 'playbook_evidence', 'playbook_selections')
       AND has_column_privilege('rk2_state', c.oid, a.attnum, 'SELECT');
    IF held IS NOT NULL THEN
        RAISE EXCEPTION 'rk2_state can still read the Playbook catalogue: %', held;
    END IF;
END $$;
