-- ===========================================================================
-- Production harness 03 -- causal attribution, closed
-- ===========================================================================
-- Two questions this corpus answers everywhere else and left open in one place
-- each. Both are named regressions the promotion is required to close, and
-- both are cheap to state only because 021, 024 and 013 were corrected at
-- their own source rather than patched here.
--
--   Lane says WHO CAUSED a request. The prototype's proxy labelled replayed
--   traffic `agent`, so a Finding could rest on a receipt that no subagent
--   ever produced -- and nothing in the schema disagreed, because the lane was
--   whatever the writer typed. A test run already declares its own lane; this
--   migration makes the receipts it cites agree with it, at write time.
--
--   The actor context says WHO WROTE a row. 013 binds it to the writing
--   transaction; this migration asserts that the binding is still in the
--   emitter, so a later `CREATE OR REPLACE FUNCTION emit_event()` that drops
--   it fails the gate instead of quietly restoring session-wide attribution.
--
-- Neither is a new invariant. Both are the old invariants made checkable.
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- 1. A test run's receipts carry the test run's lane
-- ---------------------------------------------------------------------------
-- `proxy_internal` is exempt and that is deliberate: a transport measurement
-- taken during a run was caused by the proxy acting on its own behalf, not by
-- the party the run names, and 024 already refuses to let it back an
-- Observation on any other footing. What cannot happen is the confusion the
-- regression is about -- a receipt claiming the agent caused it inside a run
-- the runtime replayed, or the reverse.
CREATE FUNCTION enforce_test_run_receipt_lane() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE v_run_lane text; v_receipt_lane text;
BEGIN
    SELECT lane INTO v_run_lane   FROM test_runs WHERE id = NEW.test_run_id;
    SELECT lane INTO v_receipt_lane FROM receipts WHERE id = NEW.receipt_id;
    IF v_receipt_lane IN ('agent','replay') AND v_receipt_lane <> v_run_lane THEN
        RAISE EXCEPTION
            'test run % is lane=%, so it cannot cite a lane=% receipt: the '
            'party that caused the request is not the party that ran the test',
            NEW.test_run_id, v_run_lane, v_receipt_lane
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $fn$;

REVOKE ALL ON FUNCTION enforce_test_run_receipt_lane() FROM PUBLIC;

CREATE TRIGGER test_run_receipts_lane_agrees
    BEFORE INSERT OR UPDATE ON test_run_receipts
    FOR EACH ROW EXECUTE FUNCTION enforce_test_run_receipt_lane();
ALTER TABLE test_run_receipts ENABLE ALWAYS TRIGGER test_run_receipts_lane_agrees;

-- ---------------------------------------------------------------------------
-- 2. The standing check
-- ---------------------------------------------------------------------------
-- Three of these four problems can only appear if something above was removed,
-- which is the point: a constraint nobody asserts is a constraint a later
-- migration can drop in one line and nobody reads the diff.
CREATE FUNCTION check_causal_attribution()
RETURNS TABLE (problem text, subject text, detail text)
LANGUAGE sql STABLE AS $fn$
    -- 1. The Lane vocabulary itself. CONTEXT.md closes it at three values, and
    --    the prototype's fourth and fifth ('control', 'transport') are what
    --    made citability turn on the wrong question.
    SELECT 'lane_vocabulary_unconstrained', 'receipts.lane',
           'receipts_lane_check is missing'
     WHERE NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'receipts'::regclass AND conname = 'receipts_lane_check')

  UNION ALL
    SELECT 'lane_vocabulary_widened', 'receipts.lane', pg_get_constraintdef(c.oid)
      FROM pg_constraint c
     WHERE c.conrelid = 'receipts'::regclass AND c.conname = 'receipts_lane_check'
       AND pg_get_constraintdef(c.oid) <>
           'CHECK ((lane = ANY (ARRAY[''agent''::text, ''replay''::text, ''proxy_internal''::text])))'

  UNION ALL
    -- 2. Rows, not shapes: a cited receipt whose lane contradicts the run that
    --    cites it. Empty while the trigger above is attached and enabled.
    SELECT 'test_run_receipt_off_lane', tr.id::text,
           'run lane=' || tr.lane || ' cites receipt lane=' || r.lane
      FROM test_run_receipts trr
      JOIN test_runs tr ON tr.id = trr.test_run_id
      JOIN receipts  r  ON r.id  = trr.receipt_id
     WHERE r.lane IN ('agent','replay') AND r.lane <> tr.lane

  UNION ALL
    -- 3. The emitter still binds the actor to the writing transaction. Text of
    --    the function body, because that is where the binding lives; a
    --    redefinition that drops it is exactly the regression.
    SELECT 'emitter_actor_context_unbound', 'emit_event',
           'the emitter does not compare app.actor_xact against the current transaction'
     WHERE NOT EXISTS (
        SELECT 1 FROM pg_proc p
          JOIN pg_namespace n ON n.oid = p.pronamespace AND n.nspname = 'public'
         WHERE p.proname = 'emit_event'
           AND p.prosrc LIKE '%app.actor_xact%'
           AND p.prosrc LIKE '%pg_current_xact_id()%')
$fn$;

REVOKE ALL ON FUNCTION check_causal_attribution() FROM PUBLIC;

INSERT INTO standing_checks (name, query, owner_ticket, note) VALUES
 ('causal_attribution', 'SELECT * FROM check_causal_attribution()', 'PH2-03',
  'Lane names one of three causing parties, a test run and its receipts agree on which, and the event emitter attributes a write to the transaction that made it');

COMMENT ON FUNCTION check_causal_attribution() IS
    'Closes RK-REG-002 and asserts the RK-REG-004 binding: who caused a '
    'request, and who wrote the row down, are both answerable from the row.';
