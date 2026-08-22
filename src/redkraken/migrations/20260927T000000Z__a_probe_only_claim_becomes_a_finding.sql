-- ---------------------------------------------------------------------------
-- 20260927T000000Z__a_probe_only_claim_becomes_a_finding.sql
--                                                                  (ticket 116)
--
-- 93 found decision 15 contradicting 025 at `observations` and repaired it
-- there. The identical contradiction sits one table further on, at
-- `finding_evidence`, and was outside 93's scope: `reject_non_agent_evidence`
-- refuses a cited Observation whose Receipt is on a Lane outside
-- `('agent','replay')`, and the only Receipt a `probe_only` transport class is
-- allowed to rest on is on `proxy_internal` by constraint. So the Observation
-- that 93 made writable is still the Observation a Finding may not cite.
--
-- Follow one class end to end and the shape is the same one 93 described.
-- `transport_evidence_guard` (`0025_transport_claims.sql:361-390`) requires a
-- `supports` row on a `probe_only` class to cite a
-- `transport_parameters_observed` Observation. `transport_observation_guard`
-- requires that Observation to cite a `transport_citable` Receipt.
-- The generated expression behind `transport_citable` requires
-- `purpose = 'transport_measurement'`, and
-- `receipts_transport_measurement_shape` puts that purpose on `proxy_internal`.
-- Then `reject_non_agent_evidence` refuses to put the Observation into
-- `finding_evidence`. The only Observation that can support the hypothesis is
-- the only Observation that cannot be the Finding's evidence, so the claim
-- reaches `supported` and stops there for good.
--
-- Two of the five classes `transport_makeability` seeds are affected, and they
-- are the two the table already calls `probe_only`: `transport.tls_configuration`
-- and `transport.certificate_trust` (`0025_transport_claims.sql:203-233`).
-- `transport.header_policy` is `agent_ok` and rests on an agent-lane Receipt
-- that was never refused; `transport.request_framing` and
-- `transport.datagram_transport` are `unmakeable` and `transport_finding_guard`
-- stops them at the Finding for a reason of its own. Nothing here changes for
-- those three.
--
-- DECISION 15 KEEPS EVERYTHING IT WAS FOR, IN 93'S TERMS.
--
-- What the proxy does on its own account -- a token it fetched, a preflight, a
-- redirect it followed for itself -- is still not evidence and still not a
-- citation, because none of it is a measurement and none of it is citable. The
-- one thing that changes is the case 025 built the column for: a Receipt whose
-- `transport_citable` is true is the door reporting a handshake it took on
-- purpose, under a Tool run opened to say so, and it is the only evidence this
-- design can produce for a `probe_only` class.
--
-- Read off `transport_citable` rather than off `purpose`, for 93's reason. The
-- generated column is the one nobody can write, so what these two guards admit
-- is exactly the set the rest of 025 admits, and a later migration that widened
-- `purpose` would not widen this.
--
-- NARROWED, NOT LIFTED, AND NOT REWRITTEN INTO 93'S EXACT PREDICATE.
--
-- 93's guard reads `r.lane = 'proxy_internal' AND NOT r.transport_citable`
-- (`20260923T000000Z__...:481`) because that was the whole of the rule it was
-- narrowing. The rule here says more than one thing: `coalesce(v_lane,
-- 'missing') NOT IN ('agent','replay')` also refuses an Observation that claims
-- `receipt` provenance and resolves to no Receipt at all, and it refuses by
-- naming the two Lanes somebody asked for rather than by naming the one Lane
-- nobody did. Replacing the predicate with 93's would drop the first and would
-- admit a fourth Lane the day one is added. So the citability clause is added
-- to the rule instead of replacing it, and what the two spellings admit is the
-- same set: `transport_citable` implies `purpose = 'transport_measurement'`,
-- which `receipts_transport_measurement_shape` implies is on `proxy_internal`.
--
-- WHERE THE NEGATIVE CONTROL LIVES, WHICH IS NOT AT THIS TABLE ANY MORE.
--
-- The case decision 15 was written for cannot reach `reject_non_agent_evidence`
-- at all, and has not been able to since 93 shipped. That guard reads a Receipt
-- through an Observation, `observations_provenance_record_check` requires a
-- `receipt` provenance to name one, and 93's `reject_proxy_internal_evidence`
-- already refuses a `proxy_internal` Receipt that is not citable at the
-- `observations` INSERT. So the door's own housekeeping never becomes an
-- Observation, and the arm narrowed below is reachable only by an Observation
-- written before 93 applied. The refusal that is still live is the sibling's:
-- `finding_chain_step_citations` carries a `receipt_id` of its own, so a chain
-- step can still try to cite a fetched token directly, and section 2 still says
-- no to it.
--
-- The transition guard is not touched here either, and 93 already said why:
-- `enforce_finding_transition` asks about the Receipt a TRANSITION cites, which
-- `requires_test_linked_receipt` pins to one the validating Test run produced,
-- and a measurement is never that. Its `proxy_internal` refusal stays exactly
-- as it is. What a measurement backs is the EVIDENCE, and the promotion rests
-- on it transitively.
--
-- Depends on 0025 (the citability column, the three transport guards and the
-- two probe-only classes), 0034 (the two guards below and the three triggers
-- that carry them), 20260815T120000Z (the bodies replaced below) and
-- 20260923T000000Z (the same narrowing one table down, and the writer that
-- makes a citable Receipt exist at all). A new file rather than an edit to any
-- of them: a recorded migration whose file has changed is schema drift and
-- `rk db migrate` refuses the whole corpus for it.
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- 1. The Receipt behind a cited Observation
-- ===========================================================================

-- 20260815T120000Z's body with the citability clause added and everything else
-- left where it was, including the two-Lane message: an operator reading a
-- refusal wants to be told what a citation may rest on, and "a transport
-- measurement" is the third answer rather than a replacement for the first two.
CREATE OR REPLACE FUNCTION reject_non_agent_evidence() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE v_lane text; v_kind text; v_obs uuid; v_citable boolean;
BEGIN
    v_obs := (to_jsonb(NEW) ->> TG_ARGV[0])::uuid;
    IF v_obs IS NULL THEN RETURN NEW; END IF;

    SELECT o.provenance_kind, r.lane, r.transport_citable
      INTO v_kind, v_lane, v_citable
      FROM observations o LEFT JOIN receipts r ON r.id = o.receipt_id
     WHERE o.id = v_obs;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'ungrounded: observation % does not exist', v_obs;
    END IF;
    -- `coalesce` on the citability for the same reason the Lane has one: the
    -- LEFT JOIN answers NULL for an Observation whose `receipt_id` is NULL, and
    -- a three-valued NOT would let that row through the arm that exists to
    -- catch it.
    IF v_kind = 'receipt'
       AND coalesce(v_lane, 'missing') NOT IN ('agent', 'replay')
       AND NOT coalesce(v_citable, false) THEN
        RAISE EXCEPTION
            'ungrounded: observation % is backed by a % receipt that measured nothing; evidence may cite the agent and replay lanes and a transport measurement',
            v_obs, coalesce(v_lane, 'missing');
    END IF;
    RETURN NEW;
END $fn$;

COMMENT ON FUNCTION reject_non_agent_evidence() IS
    'A cited Observation exists and, if it rests on a Receipt, rests on one '
    'somebody asked for: the agent''s own traffic, a Test the harness replayed, '
    'or the unintercepted handshake the door took on purpose. What this '
    'refuses is the proxy on its own account -- a `proxy_internal` Receipt that '
    'measured nothing -- and the reason the check is at INSERT is 005''s: a '
    'citation resolved at scoring time is a Finding discarded after the work.';


-- ===========================================================================
-- 2. The Receipt a chain step cites directly
-- ===========================================================================

-- Its sibling, narrowed with it and for the reason 20260815T120000Z gives for
-- widening them together: 034 attached both to `finding_chain_step_citations`,
-- this one reading the cited Receipt and the one above reading the Receipt
-- behind a cited Observation, so leaving it alone would make one table answer
-- two different ways about one measurement -- admissible cited through the
-- Observation it produced, inadmissible cited directly. No `coalesce` on the
-- citability here, because there is nothing for it to be NULL from: the Receipt
-- is found by primary key under a `FOUND` check, and 025's expression cannot
-- answer NULL -- `purpose`, `intercepted` and `decision` are all NOT NULL, and
-- the three wire columns are compared with `IS`.
CREATE OR REPLACE FUNCTION reject_non_agent_citation() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE v_lane text; v_citable boolean;
BEGIN
    IF NEW.receipt_id IS NOT NULL THEN
        SELECT lane, transport_citable INTO v_lane, v_citable
          FROM receipts WHERE id = NEW.receipt_id;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'ungrounded: receipt % does not exist', NEW.receipt_id;
        END IF;
        IF v_lane NOT IN ('agent', 'replay') AND NOT v_citable THEN
            RAISE EXCEPTION
                'ungrounded: receipt % is on the % lane and measured nothing; a report may cite the agent and replay lanes and a transport measurement',
                NEW.receipt_id, v_lane;
        END IF;
    END IF;
    RETURN NEW;
END $fn$;

COMMENT ON FUNCTION reject_non_agent_citation() IS
    'A cited Receipt exists and is one somebody asked for: the agent''s own '
    'traffic, a Test the harness replayed, or the unintercepted handshake the '
    'door took on purpose. The same rule as `reject_non_agent_evidence`, read '
    'off the Receipt rather than through an Observation.';


-- ===========================================================================
-- 3. What this migration claims, asserted
-- ===========================================================================

-- The claim is not about either guard on its own -- each was reasonable on its
-- own, which is how the pair went four migrations without being noticed -- so
-- asserting the bodies would assert the half that was never in doubt. What is
-- asserted instead is the path: one `transport_measurement` Receipt, the
-- `transport_parameters_observed` Observation that cites it, the `supports` row
-- that rests on that, and the Finding that cites it as evidence. Every guard
-- named in the header fires on the way through, and the row that gets to the
-- end is the row that could not be written before this file.
--
-- Written and then rolled back, because it is an assertion and not state: the
-- inner block is a subtransaction, the sentinel at the bottom of it unwinds
-- every write, and a real refusal carries a different SQLSTATE and leaves.
--
-- The cost of asserting it this way is that this file now depends on the shape
-- of `tests`, `test_runs` and `findings` at their birth, none of which it owns.
-- That is deliberate and it is the point: a later migration that made this
-- fixture unbuildable would be one that had moved the path this ticket exists
-- to open, and a corpus that refuses to apply is how that gets said.
DO $$
DECLARE
    v_program uuid; v_entity uuid; v_hypothesis uuid;
    v_tool_run uuid; v_receipt uuid; v_variant uuid; v_control uuid;
    v_test uuid; v_run uuid; v_finding uuid;
    v_spec jsonb := '{
      "preconditions": [{"kind": "identity_leased", "detail": "the operator slot is leased"}],
      "setup": [],
      "actions": [
        {"ordinal": 1, "role": "baseline", "kind": "request", "method": "GET",
         "url": "https://ticket116.invalid/a"},
        {"ordinal": 2, "role": "variant", "kind": "request", "method": "GET",
         "url": "https://ticket116.invalid/b"},
        {"ordinal": 3, "role": "control", "kind": "request", "method": "GET",
         "url": "https://ticket116.invalid/c"}],
      "assertions": [
        {"id": "the-variant-is-served", "kind": "status_equals", "action": 2,
         "status": 200}],
      "cleanup": []}'::jsonb;
BEGIN
    BEGIN
        INSERT INTO programs (slug, name)
        VALUES ('ticket-116-proof', 'ticket 116 proof')
        RETURNING id INTO v_program;
        INSERT INTO program_scope_versions (program_id, version, policy, policy_sha256)
        VALUES (v_program, 1, '{}'::jsonb, repeat('0', 64));
        INSERT INTO entities (program_id, type, label, dedup_key)
        VALUES (v_program, 'technology', 'ticket-116', 'tech:ticket-116')
        RETURNING id INTO v_entity;
        INSERT INTO hypotheses (program_id, subject_entity_id, property_class,
                                statement, status)
        VALUES (v_program, v_entity, 'transport.tls_configuration',
                'the target negotiates a version below what it advertises',
                'supported')
        RETURNING id INTO v_hypothesis;

        -- The measurement, in the shape 93's writer files it: its own Tool run,
        -- unintercepted, chain- and hostname-verified, on the Lane the shape
        -- constraint puts it on and nowhere else.
        INSERT INTO tool_runs (program_id, tool, args, status, started_at, transport)
        VALUES (v_program, 'rk2.transport_measurement',
                jsonb_build_object('scheme', 'https',
                                   'host', 'ticket116.invalid', 'port', 443),
                'success', clock_timestamp(), 'runtime')
        RETURNING id INTO v_tool_run;
        INSERT INTO receipts (
            program_id, tool_run_id, lane, decision, purpose, reason, method,
            scheme, host, port, path, ts_arrival, ts_egress, scope_version,
            scope_class, intercepted, wire_tls_version, wire_cipher, wire_alpn,
            wire_chain_verified, wire_hostname_verified)
        VALUES (
            v_program, v_tool_run, 'proxy_internal', 'allowed',
            'transport_measurement', 'ticket 116 proof', 'GET', 'https',
            'ticket116.invalid', 443, '/', clock_timestamp(), clock_timestamp(),
            1, 'target', false, 'TLSv1.2', 'ECDHE-RSA-AES128-GCM-SHA256',
            'http/1.1', true, true)
        RETURNING id INTO v_receipt;
        IF NOT (SELECT transport_citable FROM receipts WHERE id = v_receipt) THEN
            RAISE EXCEPTION
                'ticket 116: an unintercepted verified measurement is not citable';
        END IF;

        -- Two Observations off the one handshake, over two of the three fields
        -- `transport.tls_configuration` is allowed to assert, because the
        -- transition this Finding is opened towards counts two evidence rows
        -- and one of them has to be the control.
        INSERT INTO observations (program_id, subject_entity_id, kind, summary,
                                  provenance_kind, receipt_id, metadata)
        VALUES (v_program, v_entity, 'transport_parameters_observed',
                'the version the target negotiated with this door', 'receipt',
                v_receipt,
                jsonb_build_object('transport',
                    jsonb_build_object('tls_version', 'TLSv1.2')))
        RETURNING id INTO v_variant;
        INSERT INTO observations (program_id, subject_entity_id, kind, summary,
                                  provenance_kind, receipt_id, metadata)
        VALUES (v_program, v_entity, 'transport_parameters_observed',
                'the cipher the same handshake settled on', 'receipt', v_receipt,
                jsonb_build_object('transport',
                    jsonb_build_object('cipher', 'ECDHE-RSA-AES128-GCM-SHA256')))
        RETURNING id INTO v_control;
        INSERT INTO hypothesis_evidence (hypothesis_id, observation_id, polarity, role)
        VALUES (v_hypothesis, v_variant, 'supports', 'variant'),
               (v_hypothesis, v_control, 'supports', 'control');

        INSERT INTO tests (program_id, hypothesis_id, spec, spec_sha256)
        VALUES (v_program, v_hypothesis, v_spec, rk2_test_spec_digest(v_spec))
        RETURNING id INTO v_test;
        INSERT INTO test_runs (program_id, test_id, lane, outcome,
                               assertion_results, finished_at)
        VALUES (v_program, v_test, 'replay', 'holds',
                jsonb_build_object(
                    'assertions', jsonb_build_array(jsonb_build_object(
                        'id', 'the-variant-is-served', 'held', true)),
                    'failed', '[]'::jsonb, 'cleanup', 'done'),
                clock_timestamp())
        RETURNING id INTO v_run;

        INSERT INTO findings (program_id, subject_entity_id, property_class,
                              class_id, title, severity, severity_basis, status,
                              opened_by_test_run_id, demonstrated)
        VALUES (v_program, v_entity, 'transport.tls_configuration',
                'cleartext_transmission',
                'the door measured a transport the target does not advertise',
                'info', 'undetermined', 'candidate', v_run,
                jsonb_build_object(
                    'assertion_kinds', jsonb_build_array('status_equals'),
                    'roles', jsonb_build_array('baseline', 'variant', 'control'),
                    'receipts', 1))
        RETURNING id INTO v_finding;
        INSERT INTO finding_hypotheses (finding_id, hypothesis_id)
        VALUES (v_finding, v_hypothesis);

        -- The statement this whole file exists for. Before it, this INSERT
        -- raised `ungrounded: observation % is backed by a proxy_internal
        -- receipt`, and there was no other Observation the class was allowed to
        -- offer.
        INSERT INTO finding_evidence (finding_id, observation_id, ordinal)
        VALUES (v_finding, v_variant, 1), (v_finding, v_control, 2);

        IF (SELECT count(*) FROM finding_evidence WHERE finding_id = v_finding) <> 2 THEN
            RAISE EXCEPTION
                'ticket 116: a probe-only claim still cannot be a Finding''s evidence';
        END IF;

        RAISE EXCEPTION 'ticket 116 proof' USING ERRCODE = 'RK116';
    EXCEPTION WHEN SQLSTATE 'RK116' THEN
        NULL;
    END;
END $$;
