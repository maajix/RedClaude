-- ---------------------------------------------------------------------------
-- 20261002T000000Z__an_exchange_names_the_transcripts_it_filed.sql
--                                                                  (ticket 106)
--
-- `hold_receipt_transcripts()` has given a Program a label for both agent-visible
-- halves of every exchange since ticket 06, in the same transaction the Receipt
-- is written in, and nothing has ever handed either label back. The Agent gets
-- the Receipt label out of the door's own answer header and no more, so a run
-- that has just fetched a JavaScript bundle holds a name for the RECORD of the
-- fetch and no name for the BYTES -- which is the argument every offline tool
-- that takes an `artifact` kind is waiting for.
--
-- This file is the lookup that closes it: a Receipt label the child already
-- holds, resolved to the two Artifact labels the trigger wrote beside it.
--
-- WHY A VERB RATHER THAN A QUERY IN THE SUPERVISOR.
--
-- Because the scoping is the whole of the statement and it is not the scoping
-- the supervisor's connection has. `rk2_runtime`'s row level security policy is
-- `USING (true)` on every Program-scoped table (`0022_hooks_and_receipts.sql`,
-- section 9), so a Receipt label read on that connection with no Program
-- predicate is a read across every Program in the installation, and a label is
-- a small integer with a two-letter prefix -- `R7` exists in most of them. The
-- predicate has to be there, it has to be `rk2_program_required()` rather than
-- an argument, and written in Python it would be a predicate a later caller
-- could forget. Written here it is the only way to call the thing.
--
-- SECURITY INVOKER, for ticket 102's reason. The caller is `rk2_runtime`, which
-- already holds SELECT on both tables read below; a definer wrapper would hand
-- the runtime a privilege it does not need and, worse, would run the read as
-- the owner, for whom the policy above does not apply at all.
--
-- WHAT IT MUST NOT DO, AND DOES NOT.
--
-- It must not widen what a label may point at. The two joins are on
-- `request_agent_sha` and `response_agent_sha` -- the Agent's own halves -- and
-- never on `request_wire_sha` or `response_wire_sha`, which are the sealed,
-- credential-bearing ones. Handing back a label for a wire hash would be
-- exactly the reachability `check_wire_artifact_secrecy` rule 3 refuses, and the
-- trigger has never made such a reference for that reason. This function makes
-- no reference at all: it reads the ones that already exist.


-- ===========================================================================
-- 1. The Receipt label a child holds, resolved to the labels beside it
-- ===========================================================================

CREATE FUNCTION receipt_transcript_labels(p_receipt text) RETURNS jsonb
LANGUAGE sql STABLE AS $fn$
    SELECT coalesce(
        (SELECT jsonb_build_object(
                    'receipt_label',     r.label,
                    'request_artifact',  req.label,
                    'response_artifact', res.label)
           FROM receipts r
           -- `kind = 'runtime'` because that is the kind the transcript trigger
           -- writes, and the unique key is (program_id, sha256, kind): the same
           -- bytes held a second time as `tool_output` are a different holding
           -- with a different label, and an exchange's transcript is not that.
           LEFT JOIN artifact_references req
                  ON req.program_id = r.program_id
                 AND req.sha256 = r.request_agent_sha
                 AND req.kind = 'runtime'
           LEFT JOIN artifact_references res
                  ON res.program_id = r.program_id
                 AND res.sha256 = r.response_agent_sha
                 AND res.kind = 'runtime'
          WHERE r.program_id = rk2_program_required()
            AND r.label = btrim(coalesce(p_receipt, ''))),
        -- A name this Program holds no Receipt for answers with a null receipt
        -- label rather than with no row, so that a caller reading the document
        -- reads the same three keys either way. The two states are still
        -- distinguishable and the difference matters: a blocked exchange writes
        -- a Receipt that names no transcript at all -- `write_blocked_receipt`
        -- cannot name one, because registering them is what failed -- and that
        -- is a Receipt label with two null Artifacts, not a missing Receipt.
        jsonb_build_object('receipt_label', NULL,
                           'request_artifact', NULL,
                           'response_artifact', NULL));
$fn$;

COMMENT ON FUNCTION receipt_transcript_labels(text) IS
    'Ticket 106. The two Artifact labels `hold_receipt_transcripts()` wrote for '
    'one Receipt of this Program: the agent-visible request transcript and the '
    'agent-visible response transcript, named separately because which half a '
    'label points at is part of the answer. Scoped by `rk2_program_required()` '
    'and never by an argument. Answers a null receipt label for a name this '
    'Program does not hold, and null Artifacts for a Receipt that names no '
    'agent-visible transcript.';

REVOKE ALL ON FUNCTION receipt_transcript_labels(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION receipt_transcript_labels(text) TO rk2_runtime;

-- 066's registry, which is what makes the grant above a declaration rather than
-- a fact somebody would have to go and measure. `check_runtime_privileges`
-- refuses a verb the runtime can execute that no row here names.
INSERT INTO runtime_verb_surface (verb, added_by, note) VALUES
    ('receipt_transcript_labels(text)',
     '106',
     'names the two agent-visible transcripts of one exchange, so that the answer `mcp__rk2__http_request` gives carries a handle to the bytes and not only to the record of fetching them');


-- ===========================================================================
-- 2. What this migration claims, asserted
-- ===========================================================================
-- Four claims, and none of them is "the function exists".
--
-- The first is the grant, without which the supervisor holds a verb it cannot
-- call. The second and third are the two properties this file could lose
-- silently: a join moved onto a wire hash would still answer a label, and that
-- label would still resolve, so the failure would look exactly like success --
-- and a scoping predicate dropped for an argument would answer every Program's
-- Receipts to whichever one asked. The fourth is what the whole ticket rests
-- on: the labels are not minted here, they are read, and if the trigger that
-- writes them stops firing there is nothing left to read.

DO $$
DECLARE
    v_body   text;
    v_answer jsonb;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_proc
         WHERE proname = 'receipt_transcript_labels'
           AND has_function_privilege('rk2_runtime', oid, 'EXECUTE')
    ) THEN
        RAISE EXCEPTION 'ticket 106: the runtime cannot name an exchange''s transcripts';
    END IF;

    -- Comments stripped, because the header above names the wire columns in
    -- order to say they are not read, and an assertion that a name is absent
    -- has to be an assertion about the code.
    SELECT regexp_replace(p.prosrc, '--[^' || chr(10) || ']*', '', 'g') INTO v_body
      FROM pg_proc p
      JOIN pg_namespace ns ON ns.oid = p.pronamespace AND ns.nspname = 'public'
     WHERE p.proname = 'receipt_transcript_labels';

    IF v_body ~ 'request_wire_sha' OR v_body ~ 'response_wire_sha' THEN
        RAISE EXCEPTION
            'ticket 106: a transcript label would point at sealed, credential-bearing bytes';
    END IF;
    IF v_body !~ 'request_agent_sha' OR v_body !~ 'response_agent_sha' THEN
        RAISE EXCEPTION 'ticket 106: the two agent-visible halves are not both read';
    END IF;
    IF v_body !~ 'rk2_program_required' THEN
        RAISE EXCEPTION 'ticket 106: a Receipt label would resolve across Programs';
    END IF;

    -- The scoping, exercised rather than read: with no Program bound the verb
    -- refuses instead of answering, which is `rk2_program_required()` doing the
    -- one thing an argument could not have been trusted to do.
    PERFORM set_config('rk2.program_id', '', false);
    BEGIN
        PERFORM receipt_transcript_labels('R1');
        RAISE EXCEPTION 'ticket 106: a Receipt label resolved with no Program bound';
    EXCEPTION WHEN insufficient_privilege THEN
        NULL;
    END;

    -- And the answer's shape, on a name no Program holds. Three keys either
    -- way, so a caller reads a null rather than branching on a missing row.
    PERFORM set_config('rk2.program_id', gen_random_uuid()::text, false);
    v_answer := receipt_transcript_labels('R1');
    IF v_answer IS NULL
       OR NOT (v_answer ? 'receipt_label')
       OR NOT (v_answer ? 'request_artifact')
       OR NOT (v_answer ? 'response_artifact')
       OR v_answer ->> 'receipt_label' IS NOT NULL THEN
        RAISE EXCEPTION
            'ticket 106: an unheld Receipt label answered %', coalesce(v_answer::text, 'nothing');
    END IF;
    PERFORM set_config('rk2.program_id', '', false);

    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
         WHERE tgrelid = 'receipts'::regclass
           AND tgname = 'receipts_hold_transcripts'
           AND tgenabled = 'A'
    ) THEN
        RAISE EXCEPTION
            'ticket 106: nothing writes the labels this verb reads back';
    END IF;
END $$;
