-- ---------------------------------------------------------------------------
-- 20260928T030000Z__an_arrival_has_a_name_the_agent_can_cite.sql
--                                                                   (ticket 98)
--
-- `v_evidence` names the record behind every Observation an agent reads, except
-- one. `receipt_label` and `tool_run_label` were registered when the view was
-- built; ticket 14 added a third `provenance_kind` and nothing added a third
-- column, so an Observation derived from an out-of-band arrival reads as
-- `provenance_kind = 'callback'` and two nulls -- a claim whose evidence the
-- agent is told exists and cannot name. It is the citation half of the same
-- gap the mint verb fixes at the other end: ticket 98 makes a step able to
-- plant a canary, and this file makes the arrival it produces citable.
--
-- WHY A FUNCTION AND NOT A JOIN.
--
-- Because the obvious shape is refused, and the refusal is right. `v_evidence`
-- is `security_invoker`, so a `LEFT JOIN callback_interactions` in it reads as
-- `rk2_state` and needs `rk2_state` to hold a column grant, and the way a
-- column grant is issued here is a `state_read_surface` row -- which arm (c) of
-- `check_callback_admission` refuses outright, for either callback table, in
-- any column. That arm is not an obstacle to work around: `observed_host` is
-- the name the arrival came in on, which IS the correlator, and a Program's
-- planted canaries are not something every child gets to read off the evidence
-- surface merely because one of them is cited.
--
-- So the label is reached by a `SECURITY DEFINER` function that takes the
-- interaction the Observation already names and answers its label or nothing.
-- One column of one row, chosen by the caller's own Program -- which is what
-- the table's row policy would have said, restated here because a definer does
-- not inherit it. The table stays off the surface; the name comes off it.


-- ===========================================================================
-- 1. The third citation column
-- ===========================================================================

-- CREATE OR REPLACE rather than a drop, which is what keeps this a column
-- addition: the ten existing columns keep their names, their types and their
-- order, and the new one is appended, so nothing that selects from this view by
-- name has to be rebuilt. A drop would take `v_evidence`'s grants with it.
CREATE FUNCTION callback_interaction_label(p_interaction uuid) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
    -- The Program clause is the whole of the definer's authority. Without it
    -- this function would answer any Program's arrival to any caller holding a
    -- uuid, which is the one thing `callback_interactions_rk2_state` exists to
    -- prevent and the one thing a definer turns off. With it the answer is the
    -- label of an arrival of the caller's own Program, or nothing -- and
    -- nothing is also the honest answer for an Observation with no arrival
    -- behind it, so the two cases need no distinction here.
    SELECT ci.label FROM callback_interactions ci
     WHERE ci.id = p_interaction AND ci.program_id = rk2_program();
$fn$;

COMMENT ON FUNCTION callback_interaction_label(uuid) IS
    'Ticket 98. The label of one out-of-band arrival of the calling Program, for '
    '`v_evidence` to cite it by. A definer because `callback_interactions` is '
    'off the agent read surface and stays off it: what an agent may have is the '
    'name of the arrival, never observed_host, which is the correlator.';

REVOKE ALL ON FUNCTION callback_interaction_label(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION callback_interaction_label(uuid) TO rk2_state;


CREATE OR REPLACE VIEW v_evidence WITH (security_invoker = true) AS
    SELECT hy.label AS hypothesis_label, NULL::text AS finding_label,
           o.label AS observation_label, he.polarity, he.role,
           o.kind, o.summary, o.provenance_kind,
           r.label AS receipt_label, tr.label AS tool_run_label,
           callback_interaction_label(o.callback_interaction_id) AS callback_label
      FROM hypothesis_evidence he
      JOIN hypotheses hy ON hy.id = he.hypothesis_id
      JOIN observations o ON o.id = he.observation_id
      LEFT JOIN receipts  r  ON r.id  = o.receipt_id
      LEFT JOIN tool_runs tr ON tr.id = o.tool_run_id
    UNION ALL
    SELECT NULL::text, f.label, o.label, NULL::text, 'finding'::text,
           o.kind, o.summary, o.provenance_kind,
           r.label, tr.label,
           callback_interaction_label(o.callback_interaction_id)
      FROM finding_evidence fe
      JOIN findings f ON f.id = fe.finding_id
      JOIN observations o ON o.id = fe.observation_id
      LEFT JOIN receipts  r  ON r.id  = o.receipt_id
      LEFT JOIN tool_runs tr ON tr.id = o.tool_run_id;


-- ===========================================================================
-- 2. And the grants the invoker needs to reach it
-- ===========================================================================

-- Two rows and not four. The view is `security_invoker`, so everything it
-- selects by name has to be selectable by `rk2_state`: the new view column, and
-- the Observation column the function is passed. Registering them is how a
-- column grant is issued here -- `apply_state_grants` issues it and
-- `check_state_grants` refuses a relation-level one -- rather than a GRANT
-- written by hand, which would be a privilege the surface register does not
-- know about. Neither callback table gets a row, which is arm (c) of
-- `check_callback_admission` and is asserted again below.
INSERT INTO state_read_surface (table_name, column_name, added_by) VALUES
    ('v_evidence', 'callback_label', '98'),
    ('observations', 'callback_interaction_id', '98')
ON CONFLICT DO NOTHING;

SELECT apply_state_grants();


-- ===========================================================================
-- 3. What this migration claims, asserted
-- ===========================================================================

DO $$
DECLARE v_missing text;
BEGIN
    -- Both halves of the promise the register makes, in the words the file that
    -- built this view used: the column exists and the role that runs the view
    -- may select it. Either half alone is a door that was never in the wall.
    SELECT string_agg(format('%s.%s', s.table_name, s.column_name), ', '
                      ORDER BY s.table_name, s.column_name)
      INTO v_missing
      FROM state_read_surface s
     WHERE s.added_by = '98'
       AND NOT has_column_privilege('rk2_state', format('public.%I', s.table_name),
                                    s.column_name, 'SELECT');
    IF v_missing IS NOT NULL THEN
        RAISE EXCEPTION 'ticket 98: rk2_state cannot read %', v_missing;
    END IF;

    -- The thing that would have to stay true. An Observation whose provenance
    -- is an arrival has a name on this view now, and the name comes off the
    -- interaction; a later file that dropped the join would put the agent back
    -- where ticket 98 found it, reading a provenance word and two nulls.
    IF NOT EXISTS (
        SELECT 1 FROM pg_attribute
         WHERE attrelid = 'v_evidence'::regclass
           AND attname = 'callback_label' AND NOT attisdropped
    ) THEN
        RAISE EXCEPTION 'ticket 98: the evidence view names no arrival';
    END IF;

    -- And what stays off the surface, which is the arm this file was rewritten
    -- around. `observed_host` is the correlator, and a register row for either
    -- callback table would hand every child the names this Program has planted
    -- -- including the ones other Tasks planted, which is a canary learned from
    -- somewhere other than the run that minted it. Asserted here as well as in
    -- `check_callback_admission` because this is the file that had a reason to
    -- want one.
    IF EXISTS (
        SELECT 1 FROM state_read_surface
         WHERE table_name IN ('callback_interactions', 'callback_correlators')
    ) THEN
        RAISE EXCEPTION 'ticket 98: an arrival is citable by name, not readable by content';
    END IF;

    -- The definer is the whole of how the name gets out, so the privilege it
    -- needs and the privilege it must not have are both stated. `rk2_state`
    -- executes it; nothing else does, because every other role that could want
    -- an arrival's label can already read the table it comes from.
    IF NOT EXISTS (
        SELECT 1 FROM pg_proc
         WHERE proname = 'callback_interaction_label'
           AND has_function_privilege('rk2_state', oid, 'EXECUTE')
    ) THEN
        RAISE EXCEPTION 'ticket 98: the role that runs the evidence view cannot name an arrival';
    END IF;
END $$;
