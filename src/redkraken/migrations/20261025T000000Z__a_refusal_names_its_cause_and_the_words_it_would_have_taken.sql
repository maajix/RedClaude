-- ===========================================================================
-- Production harness 148 and 163 -- a refusal names its real cause, and the
-- words it would have accepted
-- ===========================================================================
-- Two refusals read live, in two different verbs, failing the same way: each
-- one told a child that something was wrong and nothing a child could act on.
--
-- 148. `rk2hunt7`, proposal PR1. Seven refusals, three of them about one event
-- and two of those three wrong:
--
--     1|hypotheses[1]|no_support|no evidence edge in this result supports it
--     2|evidence[2]  |no_subject|the hypothesis it names was not promoted
--     3|evidence[3]  |no_subject|the hypothesis it names was not promoted
--
-- Both edges named the same claim, both said `supports`, both carried a
-- counting role, and both Observations had been promoted moments earlier. On
-- the face of the record the claim had two supporting edges and was refused for
-- having none, and the edges were refused for naming a claim that was refused.
-- The cause is in neither sentence: 018's `enforce_evidential_kind` refuses a
-- `technology_identified` Observation in any role but `context`, so both
-- INSERTs raised, both were caught into `v_faults`, `v_supported` stayed false,
-- `RK033` was raised, and the block rolled back. `v_faults` was emptied into
-- `v_drops` on the success path only, so the sentences went with it and the
-- post-loop cascade wrote `no_subject` over the two edges it no longer had an
-- account of.
--
-- 155 explained the intended half of that at line 879 of the file it replaced:
-- "Its edges' refusals survive with it. Had the block rolled back, they would
-- have been reported against the Hypothesis instead." That is what it costs. A
-- hunter reading its own drops cannot learn that `technology_identified` may
-- only be cited with `role=context`, which is the one sentence that would stop
-- it repeating the mistake, and every drop this Program files is a message to
-- the next run.
--
-- 163. `rk2hunt17`, the first campaign in this tree to reach `conclude`. Two
-- supported claims, two Tasks, six Agent runs, eighteen proposals, no Findings:
--
--     AR17 | missing_security_headers  | refused | ... is not a vulnerability class
--     AR17 | security_misconfiguration | refused | ... is not a vulnerability class
--     AR21 | header_policy             | refused | ...
--     AR23 | missing_hsts              | refused | ...
--
-- Every run spent its three proposals on a synonym of the last one, because the
-- eighth arm of `rk2_finding_refusal` names the word that is wrong and no word
-- that is right. `_launch.Proposal` stops at three refusals for a good reason
-- -- a model that has convinced itself will spend the whole run on one claim --
-- and that reason does not cover a word the child was never shown. So the
-- refusal carries the vocabulary.
--
-- Not an enum, and not a list written here. The roster already argued this out
-- for `propose_finding`'s own argument: a vulnerability class is a word from a
-- seeded table that later tickets add rows to, and a second copy of that table
-- goes stale the first time somebody extends it. The sentence reads the table.
-- ===========================================================================


-- ---------------------------------------------------------------------------
-- 1. Ticket 148: the edges leave with the claim, and they say why
-- ---------------------------------------------------------------------------
-- The only change is in pass 3's post-block handler, and it is the smallest one
-- that answers the ticket: the faults the inner loop already collected are
-- carried out of the block that rolled back, and the cascade covers only the
-- edges that have no account of their own. Nothing about what is written, when
-- a claim survives, moves at all.

CREATE OR REPLACE FUNCTION rk2_promote_hypotheses(
    p_proposal         uuid,
    p_entity_refs      jsonb,
    p_observation_refs jsonb,
    p_next             integer
) RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p             uuid := rk2_program_required();
    v             proposals%ROWTYPE;
    v_next        integer := p_next;
    v_refused     integer := 0;
    v_element     jsonb;
    v_path        text;
    v_reason      text;
    v_cited       text;
    v_fault       text;
    v_ref         text;
    v_subject     uuid;
    v_class       text;
    v_identity_a  uuid;
    v_identity_b  uuid;
    v_rationale   jsonb;
    v_missing     text;
    v_hypothesis  uuid;
    v_label       text;
    v_polarity    text;
    v_role        text;
    v_observation uuid;
    v_other       uuid;
    v_converged   boolean;
    v_supported   boolean;
    v_candidates  jsonb[] := '{}';        -- pass 1's survivors, in element order
    v_edges       jsonb[] := '{}';        -- pass 2's survivors, in element order
    v_candidate   jsonb;
    v_edge        jsonb;
    v_drop        jsonb;
    v_faults      jsonb[];                -- one candidate's edges' refusals
    v_drops       jsonb[] := '{}';        -- pass 3's refusals, written at the end
    v_status      text;                   -- the status of the claim converged on
    v_kept        text;                   -- the polarity of the edge that stands
    v_labels      text[] := '{}';
BEGIN
    SELECT * INTO v FROM proposals WHERE id = p_proposal AND program_id = p;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'proposal % is not a result of this Program', p_proposal
            USING ERRCODE = 'check_violation';
    END IF;

    -- === Pass 1: candidates ================================================
    FOR v_element, v_path IN
        SELECT e.value, 'hypotheses[' || (e.n - 1) || ']'
          FROM (SELECT value, row_number() OVER () AS n
                  FROM jsonb_array_elements(
                          CASE WHEN jsonb_typeof(v.payload -> 'hypotheses') = 'array'
                               THEN v.payload -> 'hypotheses' ELSE '[]'::jsonb END)
                 WHERE jsonb_typeof(value) = 'object') e
         ORDER BY e.n
    LOOP
        CONTINUE WHEN EXISTS (
            SELECT 1 FROM proposal_drops d
             WHERE d.proposal_id = v.id AND d.element_path = v_path);

        v_reason := NULL;
        v_cited := NULL;
        v_subject := NULL;
        v_identity_a := NULL;
        v_identity_b := NULL;
        v_other := NULL;

        v_ref := nullif(btrim(v_element ->> 'ref'), '');
        v_class := nullif(btrim(v_element ->> 'property_class'), '');
        v_rationale := v_element -> 'rationale';

        -- `subject_ref` first, for the reason the Observations walk resolves it
        -- first: a Hypothesis about an Endpoint proposed beside it has no label
        -- to name until that walk ran.
        IF nullif(btrim(v_element ->> 'subject_ref'), '') IS NOT NULL THEN
            v_subject := nullif(p_entity_refs ->> btrim(v_element ->> 'subject_ref'), '')::uuid;
        ELSIF nullif(btrim(v_element ->> 'subject_label'), '') IS NOT NULL THEN
            SELECT e.id INTO v_subject FROM entities e
             WHERE e.program_id = p AND e.label = btrim(v_element ->> 'subject_label');
            -- Told apart, as pass 2 tells its two label sides apart and as 021
            -- told them apart before either: a label nobody was issued is a
            -- hunter's mistake about its own Program, and a label issued to
            -- another Program is the one refusal that is an isolation event.
            -- Reading the second as the first would bury it.
            IF v_subject IS NULL THEN
                SELECT e.id INTO v_other FROM entities e
                 WHERE e.label = btrim(v_element ->> 'subject_label');
            END IF;
        END IF;

        -- Both cells, resolved the same way and reported apart. `identity_a` is
        -- the caller the claim is about and `identity_b` is the one it is about
        -- relative to, so a claim that names the second and gets it wrong is not
        -- a claim about the first with a detail missing.
        SELECT x.entity_id, x.fault INTO v_identity_a, v_fault
          FROM rk2_identity_cell(p, p_entity_refs, v_element, 'a') x;
        IF v_fault IS NULL THEN
            SELECT x.entity_id, x.fault INTO v_identity_b, v_fault
              FROM rk2_identity_cell(p, p_entity_refs, v_element, 'b') x;
        END IF;

        IF v_fault IS NOT NULL THEN
            v_reason := 'no_identity';
            v_cited := v_fault;
        ELSIF v_element ? 'status' OR v_element ? 'outcome'
           OR v_element ? 'verdict' OR v_element ? 'transition' THEN
            -- Refused rather than ignored even when the value is `proposed`:
            -- the field is a claim about the state machine, and a result that
            -- states the machine's answer is stating something it was not asked
            -- and cannot know.
            v_reason := 'claims_execution';
            v_cited := coalesce(v_element ->> 'status', v_element ->> 'outcome',
                                v_element ->> 'verdict', v_element ->> 'transition',
                                'a status field');
        ELSIF v_subject IS NULL THEN
            v_reason := CASE WHEN v_other IS NULL
                             THEN 'no_subject' ELSE 'label_other_program' END;
            v_cited := coalesce(nullif(btrim(v_element ->> 'subject_ref'), ''),
                                nullif(btrim(v_element ->> 'subject_label'), ''),
                                'no subject_ref and no subject_label');
        ELSIF v_class IS NULL
           OR NOT EXISTS (SELECT 1 FROM property_classes c WHERE c.id = v_class) THEN
            v_reason := 'unknown_kind';
            v_cited := coalesce(v_class, 'no property_class');
        ELSIF nullif(btrim(coalesce(v_element ->> 'statement', '')), '') IS NULL THEN
            v_reason := 'malformed_field';
            v_cited := 'statement is empty';
        ELSIF v_ref IS NULL THEN
            -- Not a formality. An evidence edge names a candidate of this same
            -- result by `ref` and has no other way to reach one, so a candidate
            -- without a `ref` is a claim no edge in this result can support --
            -- and it would otherwise be refused `no_support` at the end of pass
            -- 3, which names a real rule and the wrong mistake.
            v_reason := 'malformed_field';
            v_cited := 'ref is empty: an evidence edge names its claim by ref';
        ELSIF v_rationale IS NULL OR jsonb_typeof(v_rationale) <> 'object' THEN
            v_reason := 'malformed_field';
            v_cited := 'rationale is not an object';
        ELSIF v_rationale - rk2_rationale_keys() <> '{}'::jsonb THEN
            v_reason := 'malformed_field';
            v_cited := 'rationale takes only ' ||
                       array_to_string(rk2_rationale_keys(), ', ');
        ELSE
            v_missing := rk2_rationale_missing(v_rationale);
            IF v_missing IS NOT NULL THEN
                v_reason := 'malformed_field';
                v_cited := 'rationale does not answer ' || v_missing;
            END IF;
        END IF;

        IF v_reason IS NOT NULL THEN
            INSERT INTO proposal_drops
                (proposal_id, program_id, ordinal, element_path, reason, cited)
            VALUES (v.id, p, v_next, v_path, v_reason, left(v_cited, 300));
            v_next := v_next + 1;
            v_refused := v_refused + 1;
            CONTINUE;
        END IF;

        v_candidates := v_candidates || jsonb_build_object(
            'path', v_path,
            'ref', v_ref,
            'subject', v_subject::text,
            'property_class', v_class,
            'identity_a', v_identity_a::text,
            'identity_b', v_identity_b::text,
            'statement', left(btrim(v_element ->> 'statement'), 2000),
            'rationale', v_rationale);
    END LOOP;

    -- === Pass 2: edges =====================================================
    --
    -- Two places, one list. Ticket 155: the contract has a top-level `evidence`
    -- array and says of a claim only that it must be given "at least one
    -- evidence edge naming it", which does not say at which level -- so a model
    -- that writes the edge inside the claim it belongs to has read the sentence
    -- correctly and lost every claim it filed. `rk2hunt14` did exactly that:
    -- three well-formed claims, each carrying its own edge, all three refused
    -- `no_support` because this loop walked an empty array.
    --
    -- The nested edge is lifted rather than the schema closed. Closing the
    -- element would refuse the whole call, and a run whose result is refused
    -- files nothing at all -- so one misplaced key would cost every Observation
    -- of that run as well as the claim.
    --
    -- Three properties the lift has to hold. The claim it is written in is the
    -- claim it names, so `hypothesis_ref` is filled from that claim's own `ref`.
    -- An edge that already names a claim keeps the name it was given: the child
    -- said which one, and a containing element is not evidence that it meant a
    -- different one. And a lifted edge is reported under its own path, because
    -- `element_path` is what a drop is de-duplicated by and borrowing a
    -- top-level ordinal would silence a drop belonging to another element.
    FOR v_element, v_path IN
        WITH top AS (
            SELECT value, row_number() OVER () AS n
              FROM jsonb_array_elements(
                      CASE WHEN jsonb_typeof(v.payload -> 'evidence') = 'array'
                           THEN v.payload -> 'evidence' ELSE '[]'::jsonb END)
             WHERE jsonb_typeof(value) = 'object'
        ), claims AS (
            SELECT value, row_number() OVER () AS n
              FROM jsonb_array_elements(
                      CASE WHEN jsonb_typeof(v.payload -> 'hypotheses') = 'array'
                           THEN v.payload -> 'hypotheses' ELSE '[]'::jsonb END)
             WHERE jsonb_typeof(value) = 'object'
        ), nested AS (
            SELECT c.n AS claim_n,
                   nullif(btrim(c.value ->> 'ref'), '') AS claim_ref,
                   e.value,
                   row_number() OVER (PARTITION BY c.n) AS n
              FROM claims c
              CROSS JOIN LATERAL jsonb_array_elements(
                      CASE WHEN jsonb_typeof(c.value -> 'evidence') = 'array'
                           THEN c.value -> 'evidence' ELSE '[]'::jsonb END) AS e(value)
             WHERE jsonb_typeof(e.value) = 'object'
        )
        SELECT e.value, e.path
          FROM (
              SELECT t.value, 'evidence[' || (t.n - 1) || ']' AS path,
                     0 AS tier, t.n AS ord, 0::bigint AS sub
                FROM top t
              UNION ALL
              SELECT CASE
                         WHEN n.value ? 'hypothesis_ref'
                           OR n.value ? 'hypothesis_label' THEN n.value
                         WHEN n.claim_ref IS NULL THEN n.value
                         ELSE n.value
                              || jsonb_build_object('hypothesis_ref', n.claim_ref)
                     END,
                     'hypotheses[' || (n.claim_n - 1) || '].evidence['
                                   || (n.n - 1) || ']',
                     1 AS tier, n.claim_n AS ord, n.n AS sub
                FROM nested n
          ) e
         ORDER BY e.tier, e.ord, e.sub
    LOOP
        CONTINUE WHEN EXISTS (
            SELECT 1 FROM proposal_drops d
             WHERE d.proposal_id = v.id AND d.element_path = v_path);

        v_reason := NULL;
        v_cited := NULL;
        v_observation := NULL;
        v_ref := NULL;
        v_hypothesis := NULL;
        v_polarity := nullif(btrim(v_element ->> 'polarity'), '');
        v_role := nullif(btrim(v_element ->> 'role'), '');

        -- The claim side. A `hypothesis_ref` names a pass-1 survivor and is
        -- resolved in pass 3, once the row exists; a `hypothesis_label` names
        -- one this Program already holds and is resolved here.
        IF nullif(btrim(v_element ->> 'hypothesis_ref'), '') IS NOT NULL THEN
            v_ref := btrim(v_element ->> 'hypothesis_ref');
            IF NOT EXISTS (SELECT 1 FROM unnest(v_candidates) c
                            WHERE c ->> 'ref' = v_ref) THEN
                v_reason := 'no_subject';
                v_cited := v_ref;
            END IF;
        ELSIF nullif(btrim(v_element ->> 'hypothesis_label'), '') IS NOT NULL THEN
            v_cited := btrim(v_element ->> 'hypothesis_label');
            SELECT h.id INTO v_hypothesis FROM hypotheses h
             WHERE h.program_id = p AND h.label = v_cited;
            IF v_hypothesis IS NULL THEN
                SELECT h.id INTO v_other FROM hypotheses h WHERE h.label = v_cited;
                v_reason := CASE WHEN v_other IS NULL
                                 THEN 'no_such_label' ELSE 'label_other_program' END;
            END IF;
        ELSE
            v_reason := 'no_subject';
            v_cited := 'no hypothesis_ref and no hypothesis_label';
        END IF;

        -- The Observation side.
        IF v_reason IS NULL THEN
            IF nullif(btrim(v_element ->> 'observation_ref'), '') IS NOT NULL THEN
                v_cited := btrim(v_element ->> 'observation_ref');
                v_observation := nullif(p_observation_refs ->> v_cited, '')::uuid;
                IF v_observation IS NULL THEN
                    v_reason := 'no_such_label';
                END IF;
            ELSIF nullif(btrim(v_element ->> 'observation_label'), '') IS NOT NULL THEN
                v_cited := btrim(v_element ->> 'observation_label');
                SELECT o.id INTO v_observation FROM observations o
                 WHERE o.program_id = p AND o.label = v_cited;
                IF v_observation IS NULL THEN
                    -- Told apart, because they are different mistakes: one
                    -- label was never issued and the other was issued to
                    -- somebody else, and only the second is an isolation event
                    -- worth reading as one.
                    SELECT o.id INTO v_other FROM observations o WHERE o.label = v_cited;
                    v_reason := CASE WHEN v_other IS NULL
                                     THEN 'no_such_label' ELSE 'label_other_program' END;
                END IF;
            ELSE
                v_reason := 'no_provenance';
                v_cited := 'no observation_ref and no observation_label';
            END IF;
        END IF;

        IF v_reason IS NULL THEN
            IF v_polarity IS NULL OR v_polarity NOT IN ('supports','refutes') THEN
                v_reason := 'unknown_kind';
                v_cited := coalesce(v_polarity, 'no polarity');
            ELSIF v_role IS NULL
               OR v_role NOT IN ('baseline','variant','control','context') THEN
                v_reason := 'unknown_kind';
                v_cited := coalesce(v_role, 'no role');
            END IF;
        END IF;

        IF v_reason IS NOT NULL THEN
            INSERT INTO proposal_drops
                (proposal_id, program_id, ordinal, element_path, reason, cited)
            VALUES (v.id, p, v_next, v_path, v_reason, left(v_cited, 300));
            v_next := v_next + 1;
            v_refused := v_refused + 1;
            CONTINUE;
        END IF;

        v_edges := v_edges || jsonb_build_object(
            'path', v_path,
            'ref', v_ref,
            'hypothesis', v_hypothesis::text,
            'observation', v_observation::text,
            'polarity', v_polarity,
            'role', v_role);
    END LOOP;

    -- === Pass 3: the rows ==================================================
    -- One block per candidate, and the block covers that candidate's edges as
    -- well as the candidate itself. That is what makes "verifies ... before
    -- creating canonical rows" true of the support check rather than nearly
    -- true: whether an edge is admissible is not fully knowable from the
    -- payload -- 018's `enforce_evidential_kind` refuses a non-evidential
    -- Observation in any role but `context`, and 025's transport guard refuses
    -- fields a transport claim may not assert -- so the honest test of "is this
    -- claim supported" is to write the edges and see which ones survive. A
    -- block that ends unsupported rolls back its own Hypothesis, its provenance
    -- and every edge it wrote, and no other transaction sees any of it.
    --
    -- Which is why the refusals are collected rather than written as they are
    -- found: a `proposal_drops` row inserted inside the block would roll back
    -- with it, and a refused Hypothesis takes its edges down with it, which the
    -- agent has to be told about too.
    FOREACH v_candidate IN ARRAY v_candidates
    LOOP
        v_path := v_candidate ->> 'path';
        v_ref := v_candidate ->> 'ref';
        v_faults := '{}';
        v_supported := false;
        v_reason := NULL;
        v_status := NULL;

        -- Before anything is written: what this candidate would converge on,
        -- and whether that claim is still open to being proposed.
        --
        -- 018's dedup key says nothing about status, so a claim already
        -- `testing` or already settled is a row this candidate can land on --
        -- and landing on it means adding this hunter's evidence edges to it.
        -- 007's transition guard counts `hypothesis_evidence` for
        -- `min_supporting_evidence`, so that is a hunter contributing to the
        -- quorum the runtime reads before it calls a claim supported, about a
        -- claim whose Test is already running. `testable` is refused for the
        -- same reason one step earlier: 023 has already ranked it into a Task.
        --
        -- What the hunter should do with a claim that is past proposing is
        -- propose the Observation, not the edge, so the refusal says which
        -- status it ran into rather than pretending the claim is not there.
        --
        -- `FOR UPDATE` because this is a check whose answer has to still be
        -- true when the insert below runs: the row is locked here and the
        -- transition guard takes the same lock, so a transition cannot land
        -- between the two.
        SELECT h.status INTO v_status
          FROM hypotheses h
         WHERE h.program_id = p
           AND h.superseded_by IS NULL
           AND h.subject_entity_id = (v_candidate ->> 'subject')::uuid
           AND h.identity_a_entity_id
               IS NOT DISTINCT FROM (v_candidate ->> 'identity_a')::uuid
           AND h.identity_b_entity_id
               IS NOT DISTINCT FROM (v_candidate ->> 'identity_b')::uuid
           AND h.property_class = v_candidate ->> 'property_class'
           FOR UPDATE;

        IF v_status IS NOT NULL AND v_status <> 'proposed' THEN
            v_reason := 'claim_past_proposed';
            v_cited := 'the claim this converges on is ' || v_status;
        ELSE
        BEGIN
            -- One statement, and `DO UPDATE` rather than `DO NOTHING` for the
            -- reason 021's Entity insert uses it: `DO NOTHING` returns no row
            -- when a concurrent promotion has inserted and not yet committed,
            -- and the read that would follow cannot see it either. `DO UPDATE`
            -- waits for that transaction and then reports the row. The SET is a
            -- no-op on purpose: the statement and the rationale of whoever got
            -- there first are what other rows may already cite, and a second
            -- hunter's prose does not overwrite them. What the second hunter
            -- contributes is its evidence and its provenance row.
            INSERT INTO hypotheses
                (program_id, subject_entity_id, identity_a_entity_id,
                 identity_b_entity_id, property_class, statement, rationale)
            VALUES (p, (v_candidate ->> 'subject')::uuid,
                    (v_candidate ->> 'identity_a')::uuid,
                    (v_candidate ->> 'identity_b')::uuid,
                    v_candidate ->> 'property_class',
                    v_candidate ->> 'statement',
                    v_candidate -> 'rationale')
            ON CONFLICT (subject_entity_id, identity_a_entity_id,
                         identity_b_entity_id, property_class)
                WHERE superseded_by IS NULL
                DO UPDATE SET statement = hypotheses.statement
            RETURNING id, label INTO v_hypothesis, v_label;

            -- Convergence is read off the trail rather than off the insert: a
            -- Hypothesis that already carries a provenance row was reached
            -- before, whether by an earlier proposal or by an earlier element
            -- of this one.
            v_converged := EXISTS (
                SELECT 1 FROM hypothesis_provenance hp
                 WHERE hp.hypothesis_id = v_hypothesis);

            INSERT INTO hypothesis_provenance
                (program_id, hypothesis_id, proposal_id, element_path,
                 agent_run_id, converged)
            VALUES (p, v_hypothesis, v.id, v_path, v.agent_run_id, v_converged)
            ON CONFLICT (hypothesis_id, proposal_id, element_path) DO NOTHING;

            -- 018 made `hypothesis_near_matches` able to record a hard key
            -- collision and left it without a writer. This is the writer: the
            -- second result to reach a Hypothesis leaves the statement it would
            -- have written, so a hunter reading near matches sees the prose
            -- that converged and not only the row it converged onto.
            IF v_converged THEN
                INSERT INTO hypothesis_near_matches
                    (program_id, candidate_statement, matched_hypothesis_id,
                     action, agent_run_id)
                VALUES (p, v_candidate ->> 'statement', v_hypothesis,
                        'key_collision', v.agent_run_id);
            END IF;

            -- This candidate's own edges. An edge that names no `ref` names no
            -- candidate, and is written after this loop against a Hypothesis
            -- that already existed.
            FOREACH v_edge IN ARRAY v_edges
            LOOP
                CONTINUE WHEN v_edge ->> 'ref' IS DISTINCT FROM v_ref;
                BEGIN
                    -- The primary key is (hypothesis, observation, role), so one
                    -- Observation may be a baseline for one claim and a control
                    -- for another, and the same edge proposed twice is one row.
                    -- That is "retain distinct valid evidence edges" as a key.
                    --
                    -- Polarity is not in that key, which is the one place where
                    -- `DO NOTHING` would be silence rather than idempotence: the
                    -- same Observation in the same role saying `refutes` where a
                    -- row already says `supports` is a different claim about the
                    -- same pairing, and dropping it without a word would let a
                    -- hunter believe it had been recorded. So what stands is
                    -- read back and compared.
                    v_kept := NULL;
                    INSERT INTO hypothesis_evidence
                        (hypothesis_id, observation_id, polarity, role, proposal_id)
                    VALUES (v_hypothesis, (v_edge ->> 'observation')::uuid,
                            v_edge ->> 'polarity', v_edge ->> 'role', v.id)
                    ON CONFLICT (hypothesis_id, observation_id, role) DO NOTHING
                    RETURNING polarity INTO v_kept;

                    IF v_kept IS NULL THEN
                        SELECT he.polarity INTO v_kept FROM hypothesis_evidence he
                         WHERE he.hypothesis_id = v_hypothesis
                           AND he.observation_id = (v_edge ->> 'observation')::uuid
                           AND he.role = v_edge ->> 'role';
                    END IF;

                    IF v_kept IS DISTINCT FROM v_edge ->> 'polarity' THEN
                        v_faults := v_faults || jsonb_build_object(
                            'path', v_edge ->> 'path',
                            'reason', 'polarity_conflict',
                            'cited', 'this Observation already ' ||
                                     coalesce(v_kept, 'stands') ||
                                     ' this claim in that role');
                        CONTINUE;
                    END IF;

                    -- Supported is read off the row that stands and not off the
                    -- payload, for the reason this whole pass writes first and
                    -- asks afterwards: the edge that counts is the one in the
                    -- table. `context` is deliberately not a role that counts:
                    -- 018 built it for an Observation that may be attached and
                    -- may never push a Hypothesis anywhere, and a claim standing
                    -- on nothing else stands on nothing.
                    IF v_kept = 'supports'
                       AND v_edge ->> 'role' IN ('baseline','variant','control') THEN
                        v_supported := true;
                    END IF;
                EXCEPTION WHEN check_violation OR raise_exception
                            OR not_null_violation OR foreign_key_violation
                            OR unique_violation THEN
                    v_faults := v_faults || jsonb_build_object(
                        'path', v_edge ->> 'path',
                        'reason', 'refused_by_invariant',
                        'cited', left(SQLERRM, 300));
                END;
            END LOOP;

            IF NOT v_supported THEN
                -- Its own SQLSTATE rather than a message the handler would have
                -- to recognise by its prose. `RK` and the ticket number is the
                -- convention for a code this schema defines; `RK033` is this
                -- file's, and the handler below is the only thing that reads it.
                RAISE EXCEPTION 'no evidence edge in this result supports it'
                    USING ERRCODE = 'RK033';
            END IF;

            v_labels := v_labels || v_label;
            -- Its edges' refusals survive with it. Had the block rolled back,
            -- they would have been reported against the Hypothesis instead.
            v_drops := v_drops || v_faults;
        EXCEPTION
            WHEN SQLSTATE 'RK033' THEN
                v_reason := 'no_support';
                v_cited := SQLERRM;
            WHEN check_violation OR raise_exception OR not_null_violation
              OR foreign_key_violation OR unique_violation THEN
                v_reason := 'refused_by_invariant';
                v_cited := left(SQLERRM, 300);
        END;
        END IF;

        -- Outside the block, so that it runs once for either refusal and so
        -- that what it writes is not rolled back by the block it describes.
        --
        -- Ticket 148: the candidate's own edges' refusals leave with it, and
        -- they leave saying what refused them. A PL/pgSQL variable survives the
        -- exception that rolled the block back -- only the persistent writes go
        -- -- so `v_faults` still holds every sentence the inner loop caught. It
        -- was emptied into `v_drops` on the success path alone, which is the
        -- whole of the defect: a claim refused for standing on nothing lost the
        -- one sentence that said why nothing stood, and the cascade below then
        -- wrote `no_subject` over the same edges. Measured on `rk2hunt7`,
        -- proposal PR1: three refusals describing one event, and the cause --
        -- 018's `enforce_evidential_kind` answering that `technology_identified`
        -- is not evidential and may only be cited with `role=context` -- named
        -- by none of the three.
        IF v_reason IS NOT NULL THEN
            v_drops := v_drops || jsonb_build_object(
                'path', v_path, 'reason', v_reason, 'cited', v_cited);
            v_drops := v_drops || v_faults;
            -- The cascade, over the edges that have no refusal of their own.
            -- It also stops claiming to be a cause: "the hypothesis it names
            -- was not promoted" is true, is useless, and reads to a hunter as
            -- though the edge were the mistake. It now says which refusal it is
            -- downstream of, so one drop leads to the other.
            v_drops := v_drops || (
                SELECT coalesce(array_agg(jsonb_build_object(
                           'path', e ->> 'path', 'reason', 'no_subject',
                           'cited', 'the hypothesis it names was refused '
                                    || v_reason || ': ' || coalesce(v_cited, ''))
                       ORDER BY e ->> 'path'), '{}'::jsonb[])
                  FROM unnest(v_edges) e
                 WHERE v_ref IS NOT NULL AND e ->> 'ref' = v_ref
                   AND NOT EXISTS (SELECT 1 FROM unnest(v_faults) f
                                    WHERE f ->> 'path' = e ->> 'path'));
        END IF;
    END LOOP;

    -- The edges that named a Hypothesis this Program already held. They stand
    -- on their own: the claim exists and this result is adding to its evidence,
    -- which is the other half of "retain distinct valid evidence edges".
    FOREACH v_edge IN ARRAY v_edges
    LOOP
        CONTINUE WHEN v_edge ->> 'ref' IS NOT NULL;

        -- The same question pass 3 asks of a candidate, asked of the claim this
        -- edge names: an edge is how evidence reaches a Hypothesis, so naming a
        -- label rather than a `ref` is the other way to hand a hunter's edge to
        -- a claim whose Test is already running. Locked here rather than read in
        -- pass 2, so that the answer is still true when the insert runs.
        SELECT h.status INTO v_status FROM hypotheses h
         WHERE h.id = (v_edge ->> 'hypothesis')::uuid AND h.program_id = p
           FOR UPDATE;
        IF v_status IS DISTINCT FROM 'proposed' THEN
            v_drops := v_drops || jsonb_build_object(
                'path', v_edge ->> 'path', 'reason', 'claim_past_proposed',
                'cited', 'the claim it names is ' || coalesce(v_status, 'gone'));
            CONTINUE;
        END IF;

        BEGIN
            -- `DO NOTHING` and not `DO UPDATE`: an edge already there was
            -- asserted by whoever asserted it, and `proposal_id` goes on saying
            -- so. The race `DO UPDATE` guards against above does not arise here,
            -- because nothing downstream needs this row's identity back. What is
            -- read back is the polarity, for the reason above: a `DO NOTHING`
            -- that swallowed the opposite polarity would be silence.
            v_kept := NULL;
            INSERT INTO hypothesis_evidence
                (hypothesis_id, observation_id, polarity, role, proposal_id)
            VALUES ((v_edge ->> 'hypothesis')::uuid,
                    (v_edge ->> 'observation')::uuid,
                    v_edge ->> 'polarity', v_edge ->> 'role', v.id)
            ON CONFLICT (hypothesis_id, observation_id, role) DO NOTHING
            RETURNING polarity INTO v_kept;

            IF v_kept IS NULL THEN
                SELECT he.polarity INTO v_kept FROM hypothesis_evidence he
                 WHERE he.hypothesis_id = (v_edge ->> 'hypothesis')::uuid
                   AND he.observation_id = (v_edge ->> 'observation')::uuid
                   AND he.role = v_edge ->> 'role';
            END IF;

            IF v_kept IS DISTINCT FROM v_edge ->> 'polarity' THEN
                v_drops := v_drops || jsonb_build_object(
                    'path', v_edge ->> 'path', 'reason', 'polarity_conflict',
                    'cited', 'this Observation already ' ||
                             coalesce(v_kept, 'stands') ||
                             ' this claim in that role');
            END IF;
        EXCEPTION WHEN check_violation OR raise_exception OR not_null_violation
                    OR foreign_key_violation OR unique_violation THEN
            v_drops := v_drops || jsonb_build_object(
                'path', v_edge ->> 'path', 'reason', 'refused_by_invariant',
                'cited', left(SQLERRM, 300));
        END;
    END LOOP;

    -- The collected refusals, continuing the one ordinal sequence the caller's
    -- three walks have been spending.
    FOREACH v_drop IN ARRAY v_drops
    LOOP
        INSERT INTO proposal_drops
            (proposal_id, program_id, ordinal, element_path, reason, cited)
        VALUES (v.id, p, v_next, v_drop ->> 'path', v_drop ->> 'reason',
                left(v_drop ->> 'cited', 300));
        v_next := v_next + 1;
        v_refused := v_refused + 1;
    END LOOP;

    -- Counted off the column rather than off a running total, so that the
    -- repeated call -- which has no running total to report -- answers the same
    -- question with the same query. The question is how many edges this result
    -- owns, not how many stand on its claims: a convergence whose every edge was
    -- already there adds nothing and says 0, and the edges it named are on the
    -- proposal that first asserted them.
    RETURN jsonb_build_object(
        'hypotheses', to_jsonb(v_labels),
        'evidence', (SELECT count(*) FROM hypothesis_evidence he
                      WHERE he.proposal_id = v.id),
        'refused', v_refused,
        'next', v_next);
END $fn$;

COMMENT ON FUNCTION rk2_promote_hypotheses(uuid, jsonb, jsonb, integer) IS
  'Ticket 33''s three passes, with ticket 155''s lift and ticket 148''s account: the edges of a proposal are its top-level `evidence` array together with the edges written inside the claims themselves, a claim is graded on whether it cited support rather than on where the citation was put, and a claim that is refused takes its edges'' own refusals out with it instead of replacing them with a sentence about itself.';


-- ---------------------------------------------------------------------------
-- 2. Ticket 163: the refusal names the words that would have worked
-- ---------------------------------------------------------------------------
-- Arm 8 and nothing else. The other seven are about the evidence and each one
-- already names the row it read; this is the only one that is about the
-- proposal, and it was the only one a child could not act on.

CREATE OR REPLACE FUNCTION rk2_finding_refusal(
        p_program uuid, p_hypothesis uuid, p_test_run uuid, p_class text)
RETURNS text
LANGUAGE plpgsql STABLE AS $fn$
DECLARE
    v_hyp  hypotheses%ROWTYPE;
    v_run  test_runs%ROWTYPE;
    v_test tests%ROWTYPE;
    v_near text;
    v_all  text;
BEGIN
    -- 1. The claim exists, here.
    SELECT * INTO v_hyp FROM hypotheses
     WHERE id = p_hypothesis AND program_id = p_program;
    IF NOT FOUND THEN
        RETURN format('%s is not a Hypothesis of this Program', p_hypothesis);
    END IF;

    -- 2. And it is supported. Every other status is a claim that has not
    --    settled, or has settled the other way.
    IF v_hyp.status <> 'supported' THEN
        RETURN format('hypothesis %s is %s, and a Finding rests on a supported claim',
                      v_hyp.label, v_hyp.status);
    END IF;

    -- 3. A superseded claim is one 007 folded into another. The Finding belongs
    --    on the keeper, and opening it here would put a canonical row on a cell
    --    whose claim has moved.
    IF v_hyp.superseded_by IS NOT NULL THEN
        RETURN format('hypothesis %s was superseded and is no longer canonical',
                      v_hyp.label);
    END IF;

    -- 4. The run exists, here.
    SELECT * INTO v_run FROM test_runs
     WHERE id = p_test_run AND program_id = p_program;
    IF NOT FOUND THEN
        RETURN format('%s is not a Test run of this Program', p_test_run);
    END IF;

    -- 5. And it is a run of a Test of this claim.
    SELECT * INTO v_test FROM tests WHERE id = v_run.test_id;
    IF v_test.hypothesis_id <> p_hypothesis THEN
        RETURN format('test run of %s settles %s, not %s',
                      v_test.label,
                      (SELECT label FROM hypotheses WHERE id = v_test.hypothesis_id),
                      v_hyp.label);
    END IF;

    -- 6. And it held. 035 derives the outcome from the run's own Receipts, so
    --    this is a fact about what came back and not about what was reported.
    IF v_run.outcome <> 'holds' THEN
        RETURN format('the run of %s concluded %s, and a Finding rests on a run that holds',
                      v_test.label, v_run.outcome);
    END IF;
    IF v_run.lane <> 'replay' THEN
        RETURN format('the run of %s is lane %s, and a Finding rests on a replay',
                      v_test.label, v_run.lane);
    END IF;

    -- 7. And it is the run that settled this claim. Not any holding run of the
    --    same Test: the transition 007 recorded cites one Receipt, and that
    --    Receipt has to be one of this run's. A second holding run of the same
    --    Test is a re-run, and a re-run is what 037 validates with.
    IF NOT EXISTS (
        SELECT 1 FROM hypothesis_transitions ht
          JOIN test_run_receipts trr ON trr.receipt_id = ht.receipt_id
         WHERE ht.hypothesis_id = p_hypothesis
           AND ht.from_status = 'testing' AND ht.to_status = 'supported'
           AND ht.actor_kind = 'runtime'
           AND trr.test_run_id = p_test_run) THEN
        RETURN format('the run of %s is not the run that settled %s',
                      v_test.label, v_hyp.label);
    END IF;

    -- 8. The class is a word from the vocabulary. Last, because it is the one
    --    refusal that is about the proposal rather than about the evidence, and
    --    a hunter who gets this after fixing six others has learned nothing.
    --
    --    Ticket 163: and it says which words it would have taken. Read out of
    --    the table rather than written here, so a migration that seeds a class
    --    changes the sentence with it. The whole vocabulary, because it is
    --    thirty-seven short words and the alternative -- a shortlist -- is this
    --    function guessing what the child meant, which is the guessing that
    --    produced `missing_security_headers` three times in a row. The closest
    --    by prefix are named first, so a child that was one word away reads the
    --    answer before it reads the list.
    IF NOT EXISTS (SELECT 1 FROM vulnerability_classes WHERE id = p_class) THEN
        SELECT string_agg(vc.id, ' ' ORDER BY vc.id) INTO v_all
          FROM vulnerability_classes vc;
        SELECT string_agg(vc.id, ' ' ORDER BY vc.id) INTO v_near
          FROM vulnerability_classes vc
         WHERE p_class IS NOT NULL
           AND split_part(vc.id, '_', 1) = split_part(btrim(lower(p_class)), '_', 1);
        RETURN format('%s is not a vulnerability class%s. This harness holds %s: %s',
                      coalesce(p_class, '(none)'),
                      CASE WHEN v_near IS NULL THEN ''
                           ELSE '; the nearest by prefix are ' || v_near END,
                      (SELECT count(*) FROM vulnerability_classes),
                      v_all);
    END IF;

    RETURN NULL;
END $fn$;

COMMENT ON FUNCTION rk2_finding_refusal(uuid, uuid, uuid, text) IS
    'Criteria 1 and 5. Whether a Finding may be opened from this claim and this '
    'run, as the sentence that says why not. NULL means yes. Answers rather '
    'than raises, so that `open_finding` can file what it hears. The class arm '
    'carries the vocabulary it is refusing against, read from '
    'vulnerability_classes, because a child that is told only which word is '
    'wrong spends its next proposal on a synonym.';
