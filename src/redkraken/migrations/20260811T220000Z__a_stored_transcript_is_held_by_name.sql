-- Origin: ticket 06, "Program-scoped artifacts", meeting ticket 09's proxy.
-- Every served exchange stores two agent-visible transcripts and registers both
-- in `artifacts`. What says a Program *holds* them is a row in
-- `artifact_references` -- that is where the label comes from, and `v_artifacts`
-- is built from that table alone -- and `record_proxy_exchange` wrote those rows
-- inside its `p_seals` block only.
--
-- So a Program held exactly the transcripts that happened to be one half of a
-- sealed pair. On a live rig after four exchanges:
--
--     artifacts: 12    artifact_references: 2
--     $ rk artifact audit
--       holdings: AF1 (64 bytes), AF2 (67 bytes)
--
-- The two held rows are request transcripts, held because the door had injected
-- a required header and sealed that transformation. The four response
-- transcripts -- 41077 bytes of target answer among them -- were stored, kept,
-- purge-protected and nameless. The bytes an operator ran the harness to obtain
-- were the ones with no label.
--
-- They were not unreachable: `artifact_refs` has arms for the receipt's own
-- `request_agent_sha` and `response_agent_sha`, so the row-level policy on
-- `artifacts` lets a caller that already knows the hash read them. That is the
-- distinction this fixes. Reachable by a hash the agent surface never hands out
-- is not the same as held: `rk artifact audit` lists holdings, `rk state` cites
-- labels, and §6's rule is that a hash is never an argument. An artifact with no
-- label is one the agent cannot ask for.
--
-- The fix is a trigger rather than another line in the writer, because the
-- writer forgetting is what happened. `record_proxy_exchange`,
-- `record_identity_proxy_exchange` and `write_allowed_receipt` all end at one
-- INSERT into `receipts`, and putting the reference there makes holding follow
-- from the record instead of from each writer remembering -- including the
-- writers a later ticket adds.
--
-- It cannot fail an insert that would have succeeded. The reference is made only
-- where the bytes are already registered, agent-visible, unencrypted and
-- unpurged; a receipt naming a hash with no artifact behind it writes no
-- reference and no error, which is the same row that is written today. What it
-- must not do is name a wire hash: those are the sealed, credential-bearing
-- halves, and a label pointing at one would be exactly the reachability
-- `check_wire_artifact_secrecy` rule 3 exists to refuse. The `WHERE` clause is
-- what keeps that true whatever a caller passes.

CREATE FUNCTION hold_receipt_transcripts() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
BEGIN
    INSERT INTO artifact_references(program_id, sha256, kind)
    SELECT DISTINCT NEW.program_id, t.sha256, 'runtime'
      FROM (VALUES (NEW.request_agent_sha), (NEW.response_agent_sha)) AS t(sha256)
      JOIN artifacts a ON a.sha256 = t.sha256
     WHERE t.sha256 IS NOT NULL
       AND a.visibility = 'agent_visible'
       AND NOT a.encrypted
       AND a.purged_at IS NULL
       -- Labels come from a BEFORE INSERT trigger, which runs before the
       -- conflict is detected and spends a counter on a row that is then
       -- discarded. Filtering here keeps `AF1, AF2, AF3` contiguous; the
       -- ON CONFLICT stays, because two concurrent exchanges over the same
       -- bytes would both pass this test.
       AND NOT EXISTS (SELECT 1 FROM artifact_references x
                        WHERE x.program_id = NEW.program_id
                          AND x.sha256 = t.sha256 AND x.kind = 'runtime')
    ON CONFLICT (program_id, sha256, kind) DO NOTHING;
    RETURN NULL;
END $fn$;

COMMENT ON FUNCTION hold_receipt_transcripts() IS
    'Gives the Program a label for the agent-visible transcripts its Receipt names. AFTER INSERT, so the reference exists exactly when the record does; never for wire or encrypted material.';

REVOKE ALL ON FUNCTION hold_receipt_transcripts() FROM PUBLIC;

-- AFTER, because the reference is a consequence of the record and not a
-- condition on it: a BEFORE trigger would write the holding for a row a later
-- constraint refuses. ENABLE ALWAYS, because every writer that reaches this
-- table is SECURITY DEFINER and would otherwise be running with `session_replica
-- tion_role` outside the trigger's reach.
CREATE TRIGGER receipts_hold_transcripts
    AFTER INSERT ON receipts
    FOR EACH ROW EXECUTE FUNCTION hold_receipt_transcripts();
ALTER TABLE receipts ENABLE ALWAYS TRIGGER receipts_hold_transcripts;


-- ===========================================================================
-- The transcripts already stored
-- ===========================================================================
-- Backfilled rather than left to the next exchange. The rows are evidence a
-- Program already paid for -- a request that was authorized, made and answered
-- -- and leaving them nameless would mean the fix reaches only material this
-- harness has not gathered yet. Same predicate as the trigger, so a backfilled
-- holding and a fresh one are the same statement.

SELECT set_actor('runtime', 'transcript holding backfill');

INSERT INTO artifact_references(program_id, sha256, kind)
SELECT DISTINCT r.program_id, t.sha256, 'runtime'
  FROM receipts r
  CROSS JOIN LATERAL (VALUES (r.request_agent_sha), (r.response_agent_sha))
    AS t(sha256)
  JOIN artifacts a ON a.sha256 = t.sha256
 WHERE t.sha256 IS NOT NULL
   AND a.visibility = 'agent_visible'
   AND NOT a.encrypted
   AND a.purged_at IS NULL
   AND NOT EXISTS (SELECT 1 FROM artifact_references x
                    WHERE x.program_id = r.program_id
                      AND x.sha256 = t.sha256 AND x.kind = 'runtime')
ON CONFLICT (program_id, sha256, kind) DO NOTHING;


-- ===========================================================================
-- The gate says which one it is
-- ===========================================================================
-- Re-created only for the last arm. Everything above it is verbatim from
-- `20260811T200000Z__a_refusal_names_a_label.sql`, which last wrote this check.
--
-- The arm reads receipts rather than the trigger, because a dropped trigger and
-- a writer that bypassed it produce the same defect and only one of them is
-- visible in `pg_trigger`. Stated as "stored and unheld": a hash with no
-- artifact behind it is not a violation -- nothing was kept, so there is nothing
-- to hold -- and a purged one is not either.

CREATE OR REPLACE FUNCTION check_capability_receipt_fence()
RETURNS TABLE(problem text, detail text) LANGUAGE sql STABLE AS $fn$
    SELECT 'proxy_can_insert_receipts', 'rk2_proxy has direct INSERT'
     WHERE has_table_privilege('rk2_proxy', 'receipts', 'INSERT')
    UNION ALL
    SELECT 'allowed_receipt_trigger_missing', 'trigger absent or not ENABLE ALWAYS'
     WHERE NOT EXISTS (SELECT 1 FROM pg_trigger
                        WHERE tgrelid = 'receipts'::regclass
                          AND tgname = 'receipts_allowed_capability' AND tgenabled = 'A')
    UNION ALL
    SELECT 'proxy_identity_writer_missing', 'rk2_proxy cannot execute the Identity fence'
     WHERE NOT has_function_privilege(
               'rk2_proxy',
               'authorize_identity_egress_request(text,text,text,text,integer,text,text)',
               'EXECUTE')
        OR NOT has_function_privilege(
               'rk2_proxy', 'authorize_identity_egress_address(text,text,text,integer,text)',
               'EXECUTE')
        OR NOT has_function_privilege('rk2_proxy', 'open_identity_slot(text,text)', 'EXECUTE')
        OR NOT has_function_privilege(
               'rk2_proxy', 'confirm_identity_slot_open(text,text,uuid,text)', 'EXECUTE')
        OR NOT has_function_privilege(
               'rk2_proxy',
               'record_identity_proxy_exchange(text,jsonb,jsonb,jsonb,text,bigint,jsonb)',
               'EXECUTE')
        OR NOT has_function_privilege(
               'rk2_proxy', 'ensure_proxy_wire_keying(text,bytea,bytea)', 'EXECUTE')
        OR NOT has_function_privilege(
               'rk2_proxy', 'write_blocked_receipt(uuid,jsonb,text)', 'EXECUTE')
    UNION ALL
    SELECT 'proxy_bypasses_identity_writer', 'rk2_proxy retains an unchecked writer'
     WHERE has_function_privilege('rk2_proxy', 'write_allowed_receipt(text,jsonb)', 'EXECUTE')
        OR has_function_privilege(
               'rk2_proxy', 'record_proxy_exchange(text,jsonb,jsonb)', 'EXECUTE')
        OR has_function_privilege(
               'rk2_proxy', 'record_proxy_exchange(text,jsonb,jsonb,jsonb)', 'EXECUTE')
        OR has_function_privilege(
               'rk2_proxy',
               'authorize_egress_request(text,text,text,text,integer,text,text,text)',
               'EXECUTE')
        OR has_function_privilege(
               'rk2_proxy', 'authorize_egress_address(text,text,text,integer,text)', 'EXECUTE')
        OR has_function_privilege('rk2_proxy', 'provision_identity_slot(uuid,text,bigint,jsonb)',
                                  'EXECUTE')
        OR has_table_privilege('rk2_proxy', 'identity_slots', 'SELECT')
    UNION ALL
    SELECT 'state_can_reach_identity_slots', 'the agent-facing role can reach slot state'
     WHERE has_table_privilege('rk2_state', 'identity_slots', 'SELECT')
        OR has_function_privilege('rk2_state', 'open_identity_slot(text,text)', 'EXECUTE')
        OR has_function_privilege(
               'rk2_state', 'provision_identity_slot(uuid,text,bigint,jsonb)', 'EXECUTE')
    UNION ALL
    SELECT 'unsealed_zero_byte_wire_artifact', a.sha256
      FROM artifacts a
     WHERE a.encrypted AND a.byte_size = 0 AND a.purged_at IS NULL
       AND NOT EXISTS (SELECT 1 FROM artifact_seal s WHERE s.sha256 = a.sha256)
    UNION ALL
    SELECT 'blocked_receipt_answers_with_a_row_id',
           'a refusal would name its record with something no label resolves'
     WHERE pg_get_function_result(
               'write_blocked_receipt(uuid,jsonb,text)'::regprocedure) <> 'text'
    UNION ALL
    SELECT 'stored_transcript_is_unheld',
           'no label in program ' || r.program_id::text || ' names ' || t.sha256
      FROM receipts r
      CROSS JOIN LATERAL (VALUES (r.request_agent_sha), (r.response_agent_sha))
        AS t(sha256)
      JOIN artifacts a ON a.sha256 = t.sha256
     WHERE t.sha256 IS NOT NULL
       AND a.visibility = 'agent_visible'
       AND NOT a.encrypted
       AND a.purged_at IS NULL
       AND NOT EXISTS (SELECT 1 FROM artifact_references x
                        WHERE x.program_id = r.program_id AND x.sha256 = t.sha256)
$fn$;

UPDATE standing_checks
   SET note = 'the proxy reaches Identity slots and allowed Receipts only through lease-gated writers; hunter reads and provisioning remain separate; every wire transformation is sealed; a refusal names a Receipt the agent can cite; a stored transcript is held by name'
 WHERE name = 'capability_receipt_fence';


DO $$
DECLARE n integer; d text;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger
                    WHERE tgrelid = 'receipts'::regclass
                      AND tgname = 'receipts_hold_transcripts' AND tgenabled = 'A') THEN
        RAISE EXCEPTION 'the holding trigger is absent or not ENABLE ALWAYS';
    END IF;
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_capability_receipt_fence();
    IF n > 0 THEN
        RAISE EXCEPTION 'capability receipt fence broken (% problems): %', n, d;
    END IF;
    SELECT count(*), string_agg(problem || ' ' || object || ': ' || detail, '; ')
      INTO n, d FROM check_wire_artifact_secrecy();
    IF n > 0 THEN
        RAISE EXCEPTION 'wire artifact secrecy broken (% problems): %', n, d;
    END IF;
END $$;
