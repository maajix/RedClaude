-- ===========================================================================
-- Production harness 33 -- a proposal becomes a canonical Hypothesis
-- ===========================================================================
-- 021 promoted Entities, Relationships and Observations and stopped there, for
-- the reason 020 stopped before it: a Hypothesis has its own dedup rule, its
-- own evidence edges and its own state machine, and a promotion that wrote one
-- without them would write a claim nothing could later test. This file is
-- those rules.
--
-- Six things, and each one is a criterion.
--
--   The rationale is structured. `hypotheses.statement` is one sentence and a
--   sentence is not reviewable: two hunters can write the same words about
--   different mechanisms. `rationale` is three named fields -- what the defect
--   would be, what a correct system does instead, and what result would settle
--   it against the hunter -- so the claim can be read apart from the prose that
--   carried it. The third field is the one 034 needs: a refutation is only
--   worth retaining if something said in advance what a refutation would be.
--
--   The proposal never claims execution. A promoted Hypothesis is `proposed`
--   and nothing else. An element that names any status is refused
--   `claims_execution` rather than clamped, because a hunter that wrote
--   `status: supported` did not make a typo -- it asserted a test it did not
--   run, and clamping it would promote the rest of that element as if the
--   assertion had not been made. The other half of the same rule is that a
--   result never reaches a claim that has moved on: converging on a Hypothesis
--   that is already `testing`, or naming one by label, would put a hunter's
--   evidence edges under a Test that is already running -- and 007's guard
--   counts those edges. Refused `claim_past_proposed`, both ways in.
--
--   The Identity cell resolves. `hypotheses.identity_a_entity_id` is half the
--   dedup key, and a key half of which silently went NULL merges two claims
--   about two different callers into one. An element that names an Identity
--   this Program has not got is refused rather than promoted without it.
--
--   The evidence comes first. Nothing is inserted until every element of the
--   result has been checked, because "verifies ... before creating canonical
--   rows" is a claim about order and not only about outcome. The walk below is
--   three passes for that reason: candidates, then their edges, then the rows.
--
--   Unsupported is refused. A Hypothesis with no edge that supports it is a
--   sentence, and 007's transition machine will never move it anywhere -- so it
--   is refused at the staging boundary where the reason can still be reported,
--   rather than accumulated as a canonical row nothing can do anything with.
--
--   Duplicates converge and keep their edges. The dedup key is 018's index; two
--   proposals that reach it produce one Hypothesis, two `hypothesis_provenance`
--   rows and the union of their evidence. The second proposal also leaves a
--   `hypothesis_near_matches` row with action `key_collision`, which is the
--   trace 018 built that column for and had no writer for until now. The union
--   has one seam: 007 keys an edge by `(hypothesis, observation, role)` and not
--   by polarity, so the same Observation cannot both support and refute one
--   claim in one role. Taking the first silently would hand the second hunter a
--   claim carrying the opposite of what it wrote, so it is refused
--   `polarity_conflict` and does not count as support.
-- ===========================================================================


-- ---------------------------------------------------------------------------
-- 1. The rationale, as fields rather than as prose
-- ---------------------------------------------------------------------------
-- Three keys, closed. A fourth would be a field no reader knows to look at, and
-- a free-form object here would be `statement` again with braces around it.
--
--   `mechanism`   what the defect is, in terms of what the system does.
--   `expectation` what a correct system does instead. Without it a mechanism
--                 is not yet a claim that anything is wrong.
--   `falsifier`   the result that would settle this against the hunter. It is
--                 what a Test is written from, and it is the field a hunter
--                 cannot write while pretending a test already ran.
--
-- The column takes a default of `{}` and the CHECK only bounds the key set,
-- because rows predating this file exist and there is no rationale to invent
-- for them. Completeness is required where it can be required honestly: at
-- promotion, of the element that is asking to become a row.

CREATE FUNCTION rk2_rationale_keys() RETURNS text[]
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $fn$
    SELECT ARRAY['mechanism','expectation','falsifier']::text[]
$fn$;

COMMENT ON FUNCTION rk2_rationale_keys() IS
    'The three fields of a Hypothesis rationale, as a value. One definition, so '
    'the keys the column admits and the keys promotion requires cannot drift.';

ALTER TABLE hypotheses
    ADD COLUMN rationale jsonb NOT NULL DEFAULT '{}'::jsonb;

-- `jsonb - text[]` deletes the listed keys; an object left empty by that
-- deletion had no key outside the list. A subquery is not available in a CHECK
-- and an IMMUTABLE function is -- which is the shape `entity_provenance.origin`
-- already uses for `rk2_origins()`.
ALTER TABLE hypotheses
    ADD CONSTRAINT hypotheses_rationale_shape
    CHECK (jsonb_typeof(rationale) = 'object'
       AND rationale - rk2_rationale_keys() = '{}'::jsonb);

COMMENT ON COLUMN hypotheses.rationale IS
    'Mechanism, expectation and falsifier. Complete on every promoted row; '
    'empty is what a row written before this file has, not a permitted claim.';

CREATE FUNCTION rk2_rationale_missing(p_rationale jsonb) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $fn$
    SELECT string_agg(k, ', ' ORDER BY k)
      FROM unnest(rk2_rationale_keys()) k
     WHERE nullif(btrim(coalesce(p_rationale ->> k, '')), '') IS NULL
$fn$;

COMMENT ON FUNCTION rk2_rationale_missing(jsonb) IS
    'The keys this rationale does not answer, or NULL when it answers all of '
    'them. The refusal quotes it, because which field is missing is the whole '
    'content of the refusal.';


-- ---------------------------------------------------------------------------
-- 2. One row per staged element that reached one Hypothesis
-- ---------------------------------------------------------------------------
-- 021's argument, applied to the other convergence: two hunters that reach the
-- same subject, Property class and Identity cell produce one Hypothesis, and
-- the second one's reasoning is not less real for arriving second. A column
-- would hold the first and lose the rest.
--
-- No `origin` here and no evidence keys, unlike `entity_provenance`. A
-- Hypothesis has exactly one origin -- a proposal promoted it, because nothing
-- else in this system writes one -- and its evidence is `hypothesis_evidence`,
-- which is a real edge with a polarity rather than a provenance note. What this
-- table adds is what neither of those carries: which staged result asked for
-- this row, and which element of it.

CREATE TABLE hypothesis_provenance (
    id            uuid NOT NULL PRIMARY KEY DEFAULT uuidv7(),
    program_id    uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    hypothesis_id uuid NOT NULL,
    proposal_id   uuid NOT NULL,
    element_path  text NOT NULL,
    agent_run_id  uuid,
    converged     boolean NOT NULL DEFAULT false,
    at            timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (hypothesis_id, program_id) REFERENCES hypotheses (id, program_id),
    FOREIGN KEY (proposal_id, program_id)   REFERENCES proposals  (id, program_id),
    FOREIGN KEY (agent_run_id, program_id)  REFERENCES agent_runs (id, program_id),
    -- The idempotence key, and the same one `entity_provenance` uses: a
    -- promotion that runs twice writes this row once.
    UNIQUE (hypothesis_id, proposal_id, element_path)
);

CREATE INDEX hypothesis_provenance_hypothesis_idx
    ON hypothesis_provenance (hypothesis_id);

COMMENT ON TABLE hypothesis_provenance IS
    'One row per staged element that reached one Hypothesis. Append-only in '
    'practice: convergence adds rows, never replaces them.';

COMMENT ON COLUMN hypothesis_provenance.converged IS
    'Whether this element found the Hypothesis already there. The first row for '
    'a Hypothesis is false; every later one is true.';

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('hypothesis_provenance', 'program_id', 'program-scoped: the purge root');

-- `audit`, for 021's reason: the row is an append-only trail of one runtime
-- decision, written on its own whenever a second result reaches a Hypothesis
-- that already exists. An Event per row would be a second copy of the trail.
INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('hypothesis_provenance', 'audit',
     'the append-only trail of which staged elements reached one Hypothesis; the row is the record',
     '33');

GRANT SELECT, INSERT, UPDATE, DELETE ON hypothesis_provenance TO rk2_runtime;

-- The rationale is readable by the role a child reads through, because a
-- hunter that cannot read the falsifier of an existing Hypothesis will propose
-- the same one again -- which is the duplication 018's near-match machinery
-- exists to prevent. The provenance trail is not: which proposal, from which
-- run, is the supervisor's question, and answering it to a child puts another
-- run's handle one join away from a role that must not resolve one.
INSERT INTO state_read_surface (table_name, column_name, added_by) VALUES
    ('hypotheses', 'rationale', '33');

-- An evidence edge gets the same question answered on it directly rather than
-- through a second table, because unlike a Hypothesis an edge converges on
-- nothing: the primary key is (hypothesis, observation, role), so one result
-- either created the edge or found it already there, and the first result to
-- assert a support is the one that asserted it. Nullable, because 007 built
-- this table and rows written before this file have no result behind them to
-- name.
ALTER TABLE hypothesis_evidence ADD COLUMN proposal_id uuid;

-- Composite, like every other key on this table: 017 gave `hypothesis_evidence`
-- a derived `program_id` and joined both its sides to it, so an edge already
-- cannot span two Programs, and a single-column key to `proposals` would be the
-- one citation on the row that could. Nullable and MATCH SIMPLE, so the rows
-- 007 admitted before this file satisfy it by having no proposal at all.
ALTER TABLE hypothesis_evidence
    ADD CONSTRAINT hypothesis_evidence_proposal_fkey
    FOREIGN KEY (proposal_id, program_id) REFERENCES proposals (id, program_id);

COMMENT ON COLUMN hypothesis_evidence.proposal_id IS
    'The staged result that first asserted this support. NULL on a row written '
    'before promotion could write one.';

-- The edge's other side has to take it down too, and this file is where that
-- stops being theoretical: nothing wrote `hypothesis_evidence` before it, so
-- nothing has ever purged a Program that held one.
--
-- 016 gave every table exactly one purge edge, and this table's is
-- `hypothesis_id`. That leaves `observation_id` NO ACTION, and both parents
-- hang off `programs` directly -- so `DELETE FROM programs` fires two cascades
-- and the check on this one can be queued before the delete that would satisfy
-- it. Which of the two runs first is the order of the RI triggers on
-- `programs`, which is the order of their OIDs, which is the order the tables
-- were created in. A purge that works or does not depending on that is not a
-- purge.
--
-- 016's reason for one edge was that a second cascade path is a second way for
-- a *narrow* delete to half-succeed. It does not apply here: 013 made
-- `observations` deletable only while `app.purging` is on, so this path cannot
-- fire outside a purge at all. And the edge describes a pairing -- this
-- Observation supports this claim -- which describes nothing once either end is
-- gone, the same reason 20260810T173000Z gave `artifact_seal` a second edge.
ALTER TABLE hypothesis_evidence
    DROP CONSTRAINT hypothesis_evidence_observation_id_fkey;
ALTER TABLE hypothesis_evidence
    ADD CONSTRAINT hypothesis_evidence_observation_id_fkey
    FOREIGN KEY (observation_id, program_id)
    REFERENCES observations (id, program_id) ON DELETE CASCADE;

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('hypothesis_evidence', 'observation_id',
     'ON DELETE CASCADE to observations: the edge is the pairing of one claim with one Observation and describes nothing once either side is gone; the Observation side is deletable only under app.purging, so this path cannot fire outside a purge');


-- ---------------------------------------------------------------------------
-- 3. Only the runtime moves a Hypothesis out of `proposed`
-- ---------------------------------------------------------------------------
-- 007 seeded `proposed -> testable` with `required_actor_kind = 'llm'`, which
-- is the one transition in that table a model could make. Spec 135 wants a
-- hunter unable to claim execution before a Test run exists, and this ticket's
-- sixth criterion says the same about `testable` specifically -- so the actor
-- becomes the runtime and the hunter's whole reach over the state machine is
-- gone. `testable` is not a formality: 023 ranks testable Hypotheses into
-- Tasks, so a model that could set it could schedule its own work.
--
-- Every other hypothesis transition already required the runtime. This is the
-- last one that did not.

UPDATE transition_rules
   SET required_actor_kind = 'runtime'
 WHERE machine = 'hypothesis'
   AND from_status = 'proposed'
   AND to_status = 'testable';

DO $$
DECLARE v_loose text;
BEGIN
    SELECT string_agg(from_status || ' -> ' || to_status || ' (' ||
                      coalesce(required_actor_kind, 'any') || ')', '; ')
      INTO v_loose FROM transition_rules
     WHERE machine = 'hypothesis'
       AND required_actor_kind IS DISTINCT FROM 'runtime';
    IF v_loose IS NOT NULL THEN
        RAISE EXCEPTION
            'ph2-33: a hypothesis transition still admits a non-runtime actor: %',
            v_loose;
    END IF;
END $$;


-- ---------------------------------------------------------------------------
-- 4. Three more ways an element can be refused
-- ---------------------------------------------------------------------------
--   `claims_execution` the element named a status, an outcome or a transition.
--                      Its own reason because it is the one refusal that is
--                      about the agent's authority rather than about its data.
--   `no_identity`      an Identity cell named something this Program has not
--                      got, or something that is not an Identity. Not
--                      `no_subject`, for the reason 021 kept `no_parent`
--                      apart: the element's subject is fine and it is the cell
--                      beside it that is missing, and an agent told
--                      `no_subject` would resend the same claim about the same
--                      subject.
--   `no_support`       no evidence edge in this result supports the claim. Not
--                      `no_provenance`, which is about a citation that does not
--                      resolve: here every citation may resolve and the
--                      element still asserts something nothing stands behind.
--   `claim_past_proposed`
--                      the claim this element would reach is no longer
--                      `proposed`. Its own reason and not `claims_execution`,
--                      which is about an element asserting a status: here the
--                      element asserted nothing and the claim moved on without
--                      it. The refusal names the status it ran into, because
--                      what a hunter does next differs -- a claim under test is
--                      one to wait for and a refuted one is one to read.
--   `polarity_conflict`
--                      the same Observation already stands on this claim in
--                      this role saying the other thing. Not `unknown_kind`:
--                      the polarity is in the vocabulary and it is the pairing
--                      that is already spoken for.
--
-- `unknown_kind` is reused for a Property class, a polarity and a role the
-- closed vocabulary refuses, for 021's reason: it says one thing, and
-- `element_path` already says which vocabulary.

ALTER TABLE proposal_drops DROP CONSTRAINT proposal_drops_reason_check;
ALTER TABLE proposal_drops ADD CONSTRAINT proposal_drops_reason_check
    CHECK (reason IN ('no_such_receipt','receipt_other_program',
                      'receipt_proxy_internal','receipt_other_run',
                      'no_such_tool_run','no_such_label',
                      'label_other_program','no_provenance',
                      'no_subject','unknown_kind','incompatible_provenance',
                      'refused_by_invariant',
                      'malformed_field','no_parent','out_of_scope',
                      'invalid_direction','is_containment',
                      'no_such_artifact','artifact_not_source','artifact_changed',
                      'artifact_not_read','no_source_citation',
                      'path_not_in_output',
                      'claims_execution','no_identity','no_support',
                      'claim_past_proposed','polarity_conflict'));


-- ---------------------------------------------------------------------------
-- 5. Where an Identity cell comes from
-- ---------------------------------------------------------------------------
-- Two cells resolved the same way, so the resolution is one function rather
-- than two copies of six lines. It reports two things because the caller has to
-- tell them apart: which Entity the cell resolved to, and -- when the element
-- named a cell that did not resolve -- the sentence the refusal quotes. Both
-- NULL is the third case and the common one: most Hypotheses are about an
-- anonymous caller and name no cell at all.

CREATE FUNCTION rk2_identity_cell(
    p_program uuid, p_refs jsonb, p_element jsonb, p_cell text
) RETURNS TABLE (entity_id uuid, fault text)
LANGUAGE plpgsql STABLE AS $fn$
DECLARE
    v_ref   text := nullif(btrim(p_element ->> ('identity_' || p_cell || '_ref')), '');
    v_label text := nullif(btrim(p_element ->> ('identity_' || p_cell || '_label')), '');
    v_id    uuid;
    v_cited text;
BEGIN
    IF v_ref IS NULL AND v_label IS NULL THEN
        RETURN QUERY SELECT NULL::uuid, NULL::text;
        RETURN;
    END IF;

    IF v_ref IS NOT NULL THEN
        v_cited := v_ref;
        v_id := nullif(p_refs ->> v_ref, '')::uuid;
    ELSE
        v_cited := v_label;
        SELECT e.id INTO v_id FROM entities e
         WHERE e.program_id = p_program AND e.label = v_label;
    END IF;

    -- Being an Entity of this Program is not enough. The column's foreign key
    -- is to `identities`, so a Host named here would be refused by the key with
    -- a message about a constraint; refusing it by name says which of the
    -- element's fields was wrong.
    IF v_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM identities i
         WHERE i.entity_id = v_id AND i.program_id = p_program) THEN
        v_id := NULL;
    END IF;

    IF v_id IS NULL THEN
        RETURN QUERY SELECT NULL::uuid,
            'identity_' || p_cell || ' names ' || v_cited ||
            ', which is not an Identity of this Program';
        RETURN;
    END IF;

    RETURN QUERY SELECT v_id, NULL::text;
END $fn$;

REVOKE ALL ON FUNCTION rk2_identity_cell(uuid, jsonb, jsonb, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rk2_identity_cell(uuid, jsonb, jsonb, text) TO rk2_runtime;

COMMENT ON FUNCTION rk2_identity_cell(uuid, jsonb, jsonb, text) IS
    'One half of a Hypothesis dedup key, resolved from a ref or a label. Two '
    'NULLs mean the element named no cell, which is correct and common; a fault '
    'means it named one that is not an Identity of this Program.';


-- ---------------------------------------------------------------------------
-- 6. The walk: candidates, then edges, then rows
-- ---------------------------------------------------------------------------
-- Its own function rather than two more loops in `promote_proposal`, because
-- the order here is not the order there. The three walks in that function are
-- one pass each: an element is checked and then written, and the next element
-- may name what the last one produced. Hypotheses cannot be done that way --
-- whether a candidate is supported is a fact about the `evidence` list, which
-- is read after it -- so this is three passes over two lists, and the passes
-- are the reason it is worth reading as one thing.
--
--   Pass 1 checks every candidate except for support and keeps the survivors.
--   Nothing is written. A candidate that fails here is not offered to pass 2,
--   so an edge naming it is refused with its own reason rather than silently
--   ignored.
--
--   Pass 2 checks every edge. An edge may name a pass-1 survivor by `ref` or a
--   Hypothesis this Program already holds by label; it may name an Observation
--   promoted in this same result by `ref` or one this Program already holds by
--   label. Nothing is written here either.
--
--   Pass 3 writes. A survivor with no supporting edge is refused `no_support`
--   here, which is the last moment it can be, and everything else becomes a row
--   -- converging on the Hypothesis the dedup key already names, if there is
--   one. The edges follow, once every Hypothesis they could name exists.
--
-- The two ref maps arrive as arguments because they are the caller's walks'
-- output. The drop ordinal arrives and leaves for the same reason:
-- `proposal_drops.ordinal` is one sequence per proposal and this function
-- writes into the middle of it.

CREATE FUNCTION rk2_promote_hypotheses(
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
    FOR v_element, v_path IN
        SELECT e.value, 'evidence[' || (e.n - 1) || ']'
          FROM (SELECT value, row_number() OVER () AS n
                  FROM jsonb_array_elements(
                          CASE WHEN jsonb_typeof(v.payload -> 'evidence') = 'array'
                               THEN v.payload -> 'evidence' ELSE '[]'::jsonb END)
                 WHERE jsonb_typeof(value) = 'object') e
         ORDER BY e.n
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
        IF v_reason IS NOT NULL THEN
            v_drops := v_drops || jsonb_build_object(
                'path', v_path, 'reason', v_reason, 'cited', v_cited);
            v_drops := v_drops || (
                SELECT coalesce(array_agg(jsonb_build_object(
                           'path', e ->> 'path', 'reason', 'no_subject',
                           'cited', 'the hypothesis it names was not promoted')
                       ORDER BY e ->> 'path'), '{}'::jsonb[])
                  FROM unnest(v_edges) e
                 WHERE v_ref IS NOT NULL AND e ->> 'ref' = v_ref);
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

REVOKE ALL ON FUNCTION rk2_promote_hypotheses(uuid, jsonb, jsonb, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rk2_promote_hypotheses(uuid, jsonb, jsonb, integer) TO rk2_runtime;

COMMENT ON FUNCTION rk2_promote_hypotheses(uuid, jsonb, jsonb, integer) IS
    'The Hypothesis and evidence halves of one promotion, in three passes: '
    'candidates, edges, then rows. Nothing is written until every element has '
    'been checked, because an unsupported claim can only be refused while it is '
    'still staging data.';


-- ---------------------------------------------------------------------------
-- 7. Promotion, with five element lists instead of three
-- ---------------------------------------------------------------------------
-- The three walks 021 wrote are unchanged except in one place: an Observation
-- now records its `ref`, the way an Entity already did. Without it an evidence
-- edge could only cite an Observation from an earlier result, and a hunter that
-- found a differential and stated what it means submits both in one result --
-- so the common case would have been the unreachable one.

CREATE OR REPLACE FUNCTION promote_proposal(p_proposal uuid) RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p           uuid := rk2_program_required();
    v           proposals%ROWTYPE;
    v_version   integer;
    v_next      integer;
    v_element   jsonb;
    v_path      text;
    v_receipt   uuid;
    v_tool_run  uuid;
    v_evidence  text;   -- the label the element cited, whatever came of it
    v_subject   uuid;
    v_kind      text;
    v_parent_type text;
    v_scope_class text;
    v_allowed   text[];
    v_provenance text;
    v_reason    text;
    v_cited     text;
    v_label     text;
    v_refs      jsonb := '{}'::jsonb;   -- the proposal's own handles
    v_type      text;
    v_parent    uuid;
    v_parent_key text;
    v_parent_selector_kind text;
    v_parent_selector text;
    v_parent_port integer;
    v_parent_path text;
    v_selector_kind text;
    v_selector  text;
    v_scheme    text;
    v_base_url  text;
    v_port      integer;
    v_path_text text;
    v_dedup     text;
    v_fault     text;
    v_entity    uuid;
    v_created   boolean;
    v_fqdn      text;
    v_apex      text;
    v_wildcard  boolean;
    v_address   text;
    v_hostname  text;
    v_protocol  text;
    v_method    text;
    v_template  text;
    v_location  text;
    v_name      text;
    v_app_kind  text;
    v_identity_class text;
    v_src       uuid;
    v_dst       uuid;
    v_src_type  text;
    v_dst_type  text;
    v_relationship uuid;
    v_src_label text;
    v_dst_label text;
    v_entities  text[] := '{}';
    v_relationships text[] := '{}';
    v_promoted  text[] := '{}';
    v_refused   integer := 0;
    v_wrote_entity boolean := false;   -- whether the scope projection has work
    v_canonical boolean;               -- whether anything at all became canonical
    v_obs_refs  jsonb := '{}'::jsonb;   -- the same handles, for Observations
    v_observation uuid;
    v_hypotheses jsonb;                 -- what the Hypothesis walk made of it
BEGIN
    SELECT * INTO v FROM proposals
     WHERE id = p_proposal AND program_id = p FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'proposal % is not a staged result of this Program', p_proposal
            USING ERRCODE = 'check_violation';
    END IF;

    -- Idempotent, and it reports the same answer rather than a different one.
    -- A promotion that ran and a promotion that had already run are the same
    -- state, and the caller retrying after a lost connection needs to be told
    -- what is true rather than what this call did. The two new lists are read
    -- back from the provenance rows, which is what they are for.
    IF v.status <> 'staged' THEN
        RETURN jsonb_build_object(
            'proposal', v.label, 'status', v.status, 'repeated', true,
            'entities', coalesce(
                (SELECT jsonb_agg(DISTINCT e.label) FROM entity_provenance ep
                   JOIN entities e ON e.id = ep.entity_id
                  WHERE ep.proposal_id = v.id), '[]'::jsonb),
            'relationships', coalesce(
                (SELECT jsonb_agg(DISTINCT s.label || ' ' || r.type || ' ' || d.label)
                   FROM relationship_provenance rp
                   JOIN relationships r ON r.id = rp.relationship_id
                   JOIN entities s ON s.id = r.src_entity_id
                   JOIN entities d ON d.id = r.dst_entity_id
                  WHERE rp.proposal_id = v.id), '[]'::jsonb),
            'observations', coalesce(
                (SELECT jsonb_agg(o.label ORDER BY o.label) FROM observations o
                  WHERE o.program_id = p AND o.metadata ->> 'proposal' = v.label),
                '[]'::jsonb),
            'hypotheses', coalesce(
                (SELECT jsonb_agg(DISTINCT h.label) FROM hypothesis_provenance hp
                   JOIN hypotheses h ON h.id = hp.hypothesis_id
                  WHERE hp.proposal_id = v.id), '[]'::jsonb),
            'evidence', (SELECT count(*) FROM hypothesis_evidence he
                          WHERE he.proposal_id = v.id),
            'refused', (SELECT count(*) FROM proposal_drops d WHERE d.proposal_id = v.id));
    END IF;

    PERFORM set_actor('runtime', 'promotion');
    PERFORM set_cause(v.agent_run_id, v.task_id);

    SELECT pr.scope_version INTO v_version FROM programs pr WHERE pr.id = p;
    SELECT coalesce(max(ordinal) + 1, 0) INTO v_next
      FROM proposal_drops WHERE proposal_id = v.id;

    -- === Entities ==========================================================
    FOR v_element, v_path IN
        SELECT e.value, 'new_entities[' || (e.n - 1) || ']'
          FROM (SELECT value, row_number() OVER () AS n
                  FROM jsonb_array_elements(
                          CASE WHEN jsonb_typeof(v.payload -> 'new_entities') = 'array'
                               THEN v.payload -> 'new_entities' ELSE '[]'::jsonb END)
                 WHERE jsonb_typeof(value) = 'object') e
         ORDER BY e.n
    LOOP
        CONTINUE WHEN EXISTS (
            SELECT 1 FROM proposal_drops d
             WHERE d.proposal_id = v.id AND d.element_path = v_path);

        v_reason := NULL; v_cited := NULL; v_fault := NULL;
        v_receipt := NULL; v_tool_run := NULL; v_provenance := NULL;
        v_parent := NULL; v_parent_key := NULL;
        v_selector_kind := NULL; v_selector := NULL; v_port := NULL;
        v_path_text := '/'; v_dedup := NULL;
        v_scheme := NULL; v_base_url := NULL;

        v_type := nullif(btrim(v_element ->> 'type'), '');
        SELECT x.receipt_id, x.tool_run_id, x.provenance_kind, x.cited
          INTO v_receipt, v_tool_run, v_provenance, v_evidence
          FROM rk2_element_evidence(p, v_element) x;

        IF v_type IS NULL OR NOT (v_type = ANY (rk2_entity_types())) THEN
            v_reason := 'unknown_kind';
            v_cited := v_type;
        ELSIF v_provenance IS NULL THEN
            -- An Entity is a claim that something is out there, and criterion 1
            -- asks for stable evidence references. A proposed Entity citing
            -- nothing is a guess, and the harness has no way to tell it from a
            -- finding later.
            v_reason := 'no_provenance';
            v_cited := v_evidence;
        END IF;

        -- The containment parent, for the three types that have one.
        IF v_reason IS NULL AND v_type IN ('service','endpoint','parameter') THEN
            v_cited := coalesce(nullif(btrim(v_element ->> 'parent_ref'), ''),
                                nullif(btrim(v_element ->> 'parent_label'), ''));
            IF nullif(btrim(v_element ->> 'parent_ref'), '') IS NOT NULL THEN
                v_parent := nullif(v_refs ->> btrim(v_element ->> 'parent_ref'), '')::uuid;
            ELSIF nullif(btrim(v_element ->> 'parent_label'), '') IS NOT NULL THEN
                SELECT e.id INTO v_parent FROM entities e
                 WHERE e.program_id = p AND e.label = btrim(v_element ->> 'parent_label');
            END IF;
            IF v_parent IS NULL THEN
                v_reason := 'no_parent';
            ELSE
                SELECT e.dedup_key, e.type, e.scope_selector_kind, e.scope_selector,
                       e.scope_port, e.scope_path_raw
                  INTO v_parent_key, v_parent_type, v_parent_selector_kind, v_parent_selector,
                       v_parent_port, v_parent_path
                  FROM entities e WHERE e.id = v_parent;
                IF NOT EXISTS (SELECT 1 FROM entity_containment c
                                WHERE c.child_type = v_type AND c.parent_type = v_parent_type) THEN
                    v_reason := 'no_parent';
                    v_cited := v_cited || ' is a ' || v_parent_type;
                END IF;
            END IF;
        END IF;

        -- The typed fields, per type. Each arm produces a selector for the
        -- scope question and the parts of the dedup key, or a sentence saying
        -- which field it could not accept.
        IF v_reason IS NULL THEN
            IF v_type = 'domain' THEN
                v_fqdn := scope_normalize_host(v_element ->> 'fqdn');
                -- `coalesce`, because an absent key compares NULL rather than
                -- false and `domains.wildcard` is NOT NULL: a Domain proposed
                -- without the flag is a Domain, not a refusal.
                v_wildcard := coalesce((v_element -> 'wildcard') = 'true'::jsonb, false);
                IF v_fqdn IS NULL OR position('.' IN v_fqdn) = 0 OR v_fqdn !~ '[a-z]' THEN
                    v_fault := 'fqdn is absent or is not a dotted domain name';
                ELSE
                    SELECT array_to_string(l[greatest(1, cardinality(l) - 1):cardinality(l)], '.')
                      INTO v_apex FROM (SELECT string_to_array(v_fqdn, '.') AS l) s;
                    v_selector_kind := CASE WHEN v_wildcard THEN 'wildcard_domain' ELSE 'host' END;
                    v_selector := v_fqdn;
                    v_dedup := rk2_dedup_key(v_type,
                        ARRAY[CASE WHEN v_wildcard THEN '*.' || v_fqdn ELSE v_fqdn END]);
                END IF;

            ELSIF v_type = 'host' THEN
                v_hostname := scope_normalize_host(v_element ->> 'hostname');
                v_address  := scope_normalize_host(v_element ->> 'address');
                IF nullif(btrim(v_element ->> 'address'), '') IS NOT NULL
                   AND (v_address IS NULL OR v_address !~ '^([0-9.]+|[0-9a-f:]+)$') THEN
                    -- Refused rather than dropped. A Host promoted on its
                    -- hostname with the offered address silently discarded is a
                    -- row that answers "what address is this" with nothing,
                    -- while the agent that sent one has been told it landed.
                    v_fault := 'address is not an IP address';
                ELSIF v_hostname IS NULL AND v_address IS NULL THEN
                    v_fault := 'a host needs a hostname or an address, and neither was usable';
                ELSE
                    v_selector_kind := 'host';
                    v_selector := coalesce(v_hostname, v_address);
                    v_dedup := rk2_dedup_key(v_type, ARRAY[v_selector]);
                END IF;

            ELSIF v_type = 'service' THEN
                v_protocol := lower(coalesce(nullif(btrim(v_element ->> 'protocol'), ''), 'tcp'));
                v_port := CASE WHEN v_element ->> 'port' ~ '^[0-9]{1,5}$'
                               THEN (v_element ->> 'port')::integer END;
                IF v_port IS NULL OR v_port NOT BETWEEN 1 AND 65535 THEN
                    v_fault := 'port is absent or is not a number between 1 and 65535';
                ELSIF v_protocol !~ '^[a-z0-9_+-]{1,32}$' THEN
                    v_fault := 'protocol is not a short lowercase token';
                ELSE
                    v_selector_kind := v_parent_selector_kind;
                    v_selector := v_parent_selector;
                    v_dedup := rk2_dedup_key(v_type,
                        ARRAY[v_parent_key, v_port::text, v_protocol]);
                END IF;

            ELSIF v_type = 'application' THEN
                SELECT u.scheme, u.host, u.port, u.path, u.fault
                  INTO v_scheme, v_selector, v_port, v_path_text, v_fault
                  FROM rk2_parse_base_url(v_element ->> 'base_url') u;
                v_app_kind := nullif(btrim(v_element ->> 'kind'), '');
                IF v_fault IS NULL AND v_app_kind IS NOT NULL
                   AND v_app_kind NOT IN ('web','api','spa','graphql','websocket') THEN
                    v_fault := 'kind is not one of web, api, spa, graphql, websocket';
                END IF;
                IF v_fault IS NULL THEN
                    v_selector_kind := 'host';
                    -- The canonical spelling, built once: the key two proposals
                    -- converge on and the URL the column stores are the same
                    -- string, so they cannot drift apart.
                    v_base_url := v_scheme || '://' || v_selector ||
                        CASE WHEN v_port = CASE WHEN v_scheme = 'https' THEN 443 ELSE 80 END
                             THEN '' ELSE ':' || v_port::text END ||
                        CASE WHEN v_path_text = '/' THEN '' ELSE v_path_text END;
                    v_dedup := rk2_dedup_key(v_type, ARRAY[v_base_url]);
                END IF;

            ELSIF v_type = 'endpoint' THEN
                v_method := upper(coalesce(nullif(btrim(v_element ->> 'method'), ''), ''));
                SELECT c.path, c.fault INTO v_template, v_fault
                  FROM rk2_clean_path(v_element ->> 'path_template') c;
                IF v_method !~ '^[A-Z]{3,10}$' THEN
                    v_fault := 'method is absent or is not an HTTP method token';
                ELSIF v_fault IS NULL THEN
                    -- The route as the fence would see it. An Application at
                    -- `/api` and an Endpoint at `/users` is one request to
                    -- `/api/users`, and the scope question is about that.
                    v_path_text := CASE
                        WHEN v_parent_path = '/' THEN v_template
                        WHEN v_template = v_parent_path
                          OR starts_with(v_template, v_parent_path || '/') THEN v_template
                        ELSE v_parent_path || v_template END;
                    v_selector_kind := v_parent_selector_kind;
                    v_selector := v_parent_selector;
                    v_port := v_parent_port;
                    v_dedup := rk2_dedup_key(v_type,
                        ARRAY[v_parent_key, v_method, v_template]);
                END IF;

            ELSIF v_type = 'parameter' THEN
                v_name := nullif(btrim(v_element ->> 'name'), '');
                v_location := lower(coalesce(nullif(btrim(v_element ->> 'location'), ''), ''));
                IF v_name IS NULL THEN
                    v_fault := 'name is absent';
                ELSIF v_location NOT IN ('query','body','path','header','cookie') THEN
                    v_fault := 'location is not one of query, body, path, header, cookie';
                ELSE
                    v_selector_kind := v_parent_selector_kind;
                    v_selector := v_parent_selector;
                    v_port := v_parent_port;
                    v_path_text := v_parent_path;
                    v_dedup := rk2_dedup_key(v_type,
                        ARRAY[v_parent_key, v_location, v_name]);
                END IF;

            ELSIF v_type = 'technology' THEN
                v_name := nullif(btrim(v_element ->> 'name'), '');
                IF v_name IS NULL THEN
                    v_fault := 'name is absent';
                ELSE
                    v_dedup := rk2_dedup_key(v_type,
                        ARRAY[lower(v_name),
                              coalesce(nullif(btrim(v_element ->> 'version'), ''), '')]);
                END IF;

            ELSE   -- identity
                v_name := nullif(btrim(v_element ->> 'slot_name'), '');
                v_identity_class :=
                    lower(coalesce(nullif(btrim(v_element ->> 'class'), ''), 'anonymous'));
                IF v_name IS NULL THEN
                    v_fault := 'slot_name is absent';
                ELSIF v_identity_class <> 'anonymous' THEN
                    -- 003: a non-anonymous Identity must carry a secret_ref, and
                    -- a secret is the operator's to place. Refused here with a
                    -- sentence rather than left to the CHECK, because "the row
                    -- was refused" and "an agent may not propose credentials"
                    -- are different things to have been told.
                    v_fault := 'an agent may propose only an anonymous identity; '
                            || 'a credentialed one is configured by the operator';
                ELSE
                    v_dedup := rk2_dedup_key(v_type, ARRAY[v_name]);
                END IF;
            END IF;

            IF v_fault IS NOT NULL THEN
                v_reason := 'malformed_field';
                v_cited := left(v_fault, 300);
            END IF;
        END IF;

        -- Scope, before the row exists. `not_addressable` is not a refusal: a
        -- Technology and an Identity have no address, which 021 says is a
        -- different answer from being out of scope.
        IF v_reason IS NULL THEN
            SELECT s.scope_class INTO v_scope_class
              FROM scope_class_of_entity(p, v_version, v_selector_kind, v_selector,
                                         v_port, v_path_text, v_path_text) s;
            IF v_scope_class = 'denied' THEN
                v_reason := 'out_of_scope';
                v_cited := left(coalesce(v_selector, '') ||
                                coalesce(':' || v_port::text, '') ||
                                CASE WHEN v_path_text = '/' THEN '' ELSE v_path_text END, 300);
            END IF;
        END IF;

        IF v_reason IS NOT NULL THEN
            INSERT INTO proposal_drops
                (proposal_id, program_id, ordinal, element_path, reason, cited)
            VALUES (v.id, p, v_next, v_path, v_reason, v_cited);
            v_next := v_next + 1;
            v_refused := v_refused + 1;
            CONTINUE;
        END IF;

        BEGIN
            -- Converge on the key, and touch nothing else. `last_seen_at` is
            -- the only column a second sighting is evidence about; the scope
            -- columns are the projection's and 021's trigger refuses them here.
            INSERT INTO entities
                (program_id, type, dedup_key, origin, scope_selector_kind,
                 scope_selector, scope_port, scope_path_raw, scope_path_norm)
            VALUES (p, v_type, v_dedup, 'proposed', v_selector_kind,
                    v_selector, v_port, v_path_text, v_path_text)
            ON CONFLICT (program_id, type, dedup_key)
                DO UPDATE SET last_seen_at = now()
            RETURNING id, (xmax = 0), label INTO v_entity, v_created, v_label;

            -- The detail row. Filled where it is empty and never overwritten:
            -- a second proposal that knows less is not a correction.
            IF v_type = 'domain' THEN
                INSERT INTO domains (entity_id, fqdn, apex, wildcard)
                VALUES (v_entity, v_fqdn, v_apex, v_wildcard)
                ON CONFLICT (entity_id) DO NOTHING;
            ELSIF v_type = 'host' THEN
                INSERT INTO hosts (entity_id, hostname, address)
                VALUES (v_entity, v_hostname, v_address::inet)
                ON CONFLICT (entity_id) DO UPDATE
                   SET hostname = coalesce(hosts.hostname, EXCLUDED.hostname),
                       address  = coalesce(hosts.address,  EXCLUDED.address);
            ELSIF v_type = 'service' THEN
                INSERT INTO services (entity_id, host_id, port, protocol, banner)
                VALUES (v_entity, v_parent, v_port, v_protocol,
                        left(nullif(btrim(v_element ->> 'banner'), ''), 500))
                ON CONFLICT (entity_id) DO UPDATE
                   SET banner = coalesce(services.banner, EXCLUDED.banner);
            ELSIF v_type = 'application' THEN
                INSERT INTO applications (entity_id, base_url, kind)
                VALUES (v_entity, v_base_url, v_app_kind)
                ON CONFLICT (entity_id) DO UPDATE
                   SET kind = coalesce(applications.kind, EXCLUDED.kind);
            ELSIF v_type = 'endpoint' THEN
                INSERT INTO endpoints (entity_id, application_id, method, path_template,
                                       auth_required, request_content_type)
                VALUES (v_entity, v_parent, v_method, v_template,
                        CASE WHEN jsonb_typeof(v_element -> 'auth_required') = 'boolean'
                             THEN (v_element -> 'auth_required') = 'true'::jsonb END,
                        left(nullif(btrim(v_element ->> 'request_content_type'), ''), 200))
                ON CONFLICT (entity_id) DO UPDATE
                   SET auth_required = coalesce(endpoints.auth_required, EXCLUDED.auth_required),
                       request_content_type = coalesce(endpoints.request_content_type,
                                                       EXCLUDED.request_content_type);
            ELSIF v_type = 'parameter' THEN
                INSERT INTO parameters (entity_id, endpoint_id, name, location,
                                        value_class, reflected)
                VALUES (v_entity, v_parent, v_name, v_location,
                        left(nullif(btrim(v_element ->> 'value_class'), ''), 200),
                        CASE WHEN jsonb_typeof(v_element -> 'reflected') = 'boolean'
                             THEN (v_element -> 'reflected') = 'true'::jsonb END)
                ON CONFLICT (entity_id) DO UPDATE
                   SET value_class = coalesce(parameters.value_class, EXCLUDED.value_class),
                       reflected   = coalesce(parameters.reflected,   EXCLUDED.reflected);
            ELSIF v_type = 'technology' THEN
                INSERT INTO technologies (entity_id, name, version, cpe)
                VALUES (v_entity, v_name,
                        nullif(btrim(v_element ->> 'version'), ''),
                        left(nullif(btrim(v_element ->> 'cpe'), ''), 200))
                ON CONFLICT (entity_id) DO UPDATE
                   SET cpe = coalesce(technologies.cpe, EXCLUDED.cpe);
            ELSE
                INSERT INTO identities (entity_id, slot_name, class)
                VALUES (v_entity, v_name, 'anonymous')
                ON CONFLICT (entity_id) DO NOTHING;
            END IF;

            INSERT INTO entity_provenance
                (program_id, entity_id, origin, proposal_id, element_path,
                 agent_run_id, receipt_id, tool_run_id)
            VALUES (p, v_entity, 'proposed', v.id, v_path,
                    v.agent_run_id, v_receipt, v_tool_run)
            ON CONFLICT (entity_id, origin, proposal_id, element_path) DO NOTHING;

            v_wrote_entity := true;
            v_entities := v_entities || v_label;
            IF nullif(btrim(v_element ->> 'ref'), '') IS NOT NULL THEN
                v_refs := v_refs || jsonb_build_object(btrim(v_element ->> 'ref'),
                                                       v_entity::text);
            END IF;
        EXCEPTION WHEN check_violation OR raise_exception OR not_null_violation
                    OR foreign_key_violation OR unique_violation THEN
            INSERT INTO proposal_drops
                (proposal_id, program_id, ordinal, element_path, reason, cited)
            VALUES (v.id, p, v_next, v_path, 'refused_by_invariant',
                    left(SQLERRM, 300));
            v_next := v_next + 1;
            v_refused := v_refused + 1;
        END;
    END LOOP;

    -- One projection for the whole walk. Every Entity above was inserted denied
    -- and every one of them was scope-checked before it was; this is what turns
    -- the check into the stored class, and re-running it at the same version
    -- writes nothing.
    IF v_wrote_entity AND v_version IS NOT NULL THEN
        PERFORM refresh_scope_projection(p);
    END IF;

    -- === Relationships =====================================================
    FOR v_element, v_path IN
        SELECT e.value, 'relationships[' || (e.n - 1) || ']'
          FROM (SELECT value, row_number() OVER () AS n
                  FROM jsonb_array_elements(
                          CASE WHEN jsonb_typeof(v.payload -> 'relationships') = 'array'
                               THEN v.payload -> 'relationships' ELSE '[]'::jsonb END)
                 WHERE jsonb_typeof(value) = 'object') e
         ORDER BY e.n
    LOOP
        CONTINUE WHEN EXISTS (
            SELECT 1 FROM proposal_drops d
             WHERE d.proposal_id = v.id AND d.element_path = v_path);

        v_reason := NULL; v_cited := NULL;
        v_receipt := NULL; v_tool_run := NULL; v_provenance := NULL;
        v_src := NULL; v_dst := NULL;

        v_type := nullif(btrim(v_element ->> 'type'), '');
        SELECT x.receipt_id, x.tool_run_id, x.provenance_kind, x.cited
          INTO v_receipt, v_tool_run, v_provenance, v_evidence
          FROM rk2_element_evidence(p, v_element) x;

        IF nullif(btrim(v_element ->> 'src_ref'), '') IS NOT NULL THEN
            v_src := nullif(v_refs ->> btrim(v_element ->> 'src_ref'), '')::uuid;
        ELSIF nullif(btrim(v_element ->> 'src_label'), '') IS NOT NULL THEN
            SELECT e.id INTO v_src FROM entities e
             WHERE e.program_id = p AND e.label = btrim(v_element ->> 'src_label');
        END IF;
        IF nullif(btrim(v_element ->> 'dst_ref'), '') IS NOT NULL THEN
            v_dst := nullif(v_refs ->> btrim(v_element ->> 'dst_ref'), '')::uuid;
        ELSIF nullif(btrim(v_element ->> 'dst_label'), '') IS NOT NULL THEN
            SELECT e.id INTO v_dst FROM entities e
             WHERE e.program_id = p AND e.label = btrim(v_element ->> 'dst_label');
        END IF;

        SELECT e.type INTO v_src_type FROM entities e WHERE e.id = v_src;
        SELECT e.type INTO v_dst_type FROM entities e WHERE e.id = v_dst;

        IF v_provenance IS NULL THEN
            v_reason := 'no_provenance';
            v_cited := v_evidence;
        ELSIF v_src IS NULL OR v_dst IS NULL THEN
            v_reason := 'no_subject';
            v_cited := CASE WHEN v_src IS NULL
                            THEN coalesce(nullif(btrim(v_element ->> 'src_ref'), ''),
                                          nullif(btrim(v_element ->> 'src_label'), ''))
                            ELSE coalesce(nullif(btrim(v_element ->> 'dst_ref'), ''),
                                          nullif(btrim(v_element ->> 'dst_label'), '')) END;
        ELSIF NOT EXISTS (SELECT 1 FROM relationship_directions d WHERE d.type = v_type) THEN
            v_reason := 'unknown_kind';
            v_cited := v_type;
        ELSIF EXISTS (SELECT 1 FROM entity_containment c
                       WHERE (c.child_type, c.parent_type) IN
                             ((v_src_type, v_dst_type), (v_dst_type, v_src_type))) THEN
            -- Named apart from `invalid_direction` on purpose: the pair is not
            -- merely undefined, it is already a fact of the schema, and the
            -- agent's mistake is modelling rather than orientation.
            v_reason := 'is_containment';
            v_cited := v_src_type || ' and ' || v_dst_type || ' are containment, not a relationship';
        ELSIF NOT EXISTS (SELECT 1 FROM relationship_directions d
                           WHERE d.type = v_type AND d.src_type = v_src_type
                             AND d.dst_type = v_dst_type) THEN
            v_reason := 'invalid_direction';
            v_cited := v_type || ' does not go from ' || v_src_type || ' to ' || v_dst_type;
        END IF;

        IF v_reason IS NOT NULL THEN
            INSERT INTO proposal_drops
                (proposal_id, program_id, ordinal, element_path, reason, cited)
            VALUES (v.id, p, v_next, v_path, v_reason, left(v_cited, 300));
            v_next := v_next + 1;
            v_refused := v_refused + 1;
            CONTINUE;
        END IF;

        BEGIN
            INSERT INTO relationships (program_id, src_entity_id, dst_entity_id, type, origin)
            VALUES (p, v_src, v_dst, v_type, 'proposed')
            ON CONFLICT (src_entity_id, dst_entity_id, type)
                DO UPDATE SET last_seen_at = now()
            RETURNING id INTO v_relationship;

            INSERT INTO relationship_provenance
                (program_id, relationship_id, origin, proposal_id, element_path,
                 agent_run_id, receipt_id, tool_run_id)
            VALUES (p, v_relationship, 'proposed', v.id, v_path,
                    v.agent_run_id, v_receipt, v_tool_run)
            ON CONFLICT (relationship_id, origin, proposal_id, element_path) DO NOTHING;

            SELECT e.label INTO v_src_label FROM entities e WHERE e.id = v_src;
            SELECT e.label INTO v_dst_label FROM entities e WHERE e.id = v_dst;
            v_relationships := v_relationships ||
                (v_src_label || ' ' || v_type || ' ' || v_dst_label);
        EXCEPTION WHEN check_violation OR raise_exception OR not_null_violation
                    OR foreign_key_violation OR unique_violation THEN
            INSERT INTO proposal_drops
                (proposal_id, program_id, ordinal, element_path, reason, cited)
            VALUES (v.id, p, v_next, v_path, 'refused_by_invariant',
                    left(SQLERRM, 300));
            v_next := v_next + 1;
            v_refused := v_refused + 1;
        END;
    END LOOP;

    -- === Observations ======================================================
    FOR v_element, v_path IN
        SELECT e.value, 'observations[' || (e.n - 1) || ']'
          FROM (SELECT value, row_number() OVER () AS n
                  FROM jsonb_array_elements(
                          CASE WHEN jsonb_typeof(v.payload -> 'observations') = 'array'
                               THEN v.payload -> 'observations' ELSE '[]'::jsonb END)
                 WHERE jsonb_typeof(value) = 'object') e
         ORDER BY e.n
    LOOP
        CONTINUE WHEN EXISTS (
            SELECT 1 FROM proposal_drops d
             WHERE d.proposal_id = v.id AND d.element_path = v_path);

        v_reason := NULL;
        v_receipt := NULL;
        v_tool_run := NULL;
        v_provenance := NULL;
        v_subject := NULL;
        v_cited := NULL;

        SELECT x.receipt_id, x.tool_run_id, x.provenance_kind, x.cited
          INTO v_receipt, v_tool_run, v_provenance, v_evidence
          FROM rk2_element_evidence(p, v_element) x;

        -- `subject_ref` first, because an Observation about an Entity proposed
        -- in the same result has no label to name until the walk above ran.
        IF nullif(btrim(v_element ->> 'subject_ref'), '') IS NOT NULL THEN
            v_subject := nullif(v_refs ->> btrim(v_element ->> 'subject_ref'), '')::uuid;
            v_cited := btrim(v_element ->> 'subject_ref');
        ELSE
            SELECT e.id INTO v_subject FROM entities e
             WHERE e.program_id = p AND e.label = v_element ->> 'subject_label';
            v_cited := v_element ->> 'subject_label';
        END IF;
        v_kind := v_element ->> 'kind';
        SELECT k.allowed_provenance INTO v_allowed
          FROM observation_kinds k WHERE k.id = v_kind;

        IF v_provenance IS NULL THEN
            v_reason := 'no_provenance';
            v_cited := v_evidence;
        ELSIF v_subject IS NULL THEN
            v_reason := 'no_subject';
        ELSIF v_allowed IS NULL THEN
            v_reason := 'unknown_kind';
            v_cited := v_kind;
        ELSIF NOT (v_provenance = ANY (v_allowed)) THEN
            v_reason := 'incompatible_provenance';
            v_cited := v_kind;
        END IF;

        IF v_reason IS NOT NULL THEN
            INSERT INTO proposal_drops
                (proposal_id, program_id, ordinal, element_path, reason, cited)
            VALUES (v.id, p, v_next, v_path, v_reason, v_cited);
            v_next := v_next + 1;
            v_refused := v_refused + 1;
            CONTINUE;
        END IF;

        BEGIN
            INSERT INTO observations
                (program_id, agent_run_id, subject_entity_id, kind, summary,
                 provenance_kind, receipt_id, tool_run_id, metadata)
            VALUES
                (p, v.agent_run_id, v_subject, v_kind,
                 left(coalesce(v_element ->> 'summary', ''), 2000),
                 v_provenance, v_receipt, v_tool_run,
                 jsonb_build_object('proposal', v.label, 'element', v_path))
            RETURNING label, id INTO v_label, v_observation;
            v_promoted := v_promoted || v_label;

            -- The handle, recorded the way an Entity's is. Without it an
            -- evidence edge could only cite an Observation from an earlier
            -- result, and a hunter that ran a differential and stated what it
            -- means submits both halves in one result.
            IF nullif(btrim(v_element ->> 'ref'), '') IS NOT NULL THEN
                v_obs_refs := v_obs_refs || jsonb_build_object(
                    btrim(v_element ->> 'ref'), v_observation::text);
            END IF;
        EXCEPTION WHEN check_violation OR raise_exception OR not_null_violation
                    OR foreign_key_violation OR unique_violation THEN
            INSERT INTO proposal_drops
                (proposal_id, program_id, ordinal, element_path, reason, cited)
            VALUES (v.id, p, v_next, v_path, 'refused_by_invariant',
                    left(SQLERRM, 300));
            v_next := v_next + 1;
            v_refused := v_refused + 1;
        END;
    END LOOP;

    -- The fourth and fifth lists, once the three walks above have produced
    -- every handle they can name. Its own function, and its own three passes:
    -- whether a Hypothesis is supported is a fact about the `evidence` list,
    -- which is read after it, so it cannot be settled one element at a time.
    v_hypotheses := rk2_promote_hypotheses(v.id, v_refs, v_obs_refs, v_next);
    v_next := (v_hypotheses ->> 'next')::integer;
    v_refused := v_refused + (v_hypotheses ->> 'refused')::integer;

    -- Promoted if anything at all became canonical. A recon run that found
    -- four Hosts and asserted nothing about them has done its Task, and 020's
    -- completion trigger reads this status.
    v_canonical := cardinality(v_promoted) > 0
              OR cardinality(v_entities) > 0
              OR cardinality(v_relationships) > 0
              OR jsonb_array_length(v_hypotheses -> 'hypotheses') > 0
              OR (v_hypotheses ->> 'evidence')::integer > 0;

    UPDATE proposals
       SET status = CASE WHEN v_canonical THEN 'promoted' ELSE 'rejected' END,
           promoted_at = CASE WHEN v_canonical THEN now() END
     WHERE id = v.id;

    RETURN jsonb_build_object(
        'proposal', v.label,
        'status', CASE WHEN v_canonical THEN 'promoted' ELSE 'rejected' END,
        'repeated', false,
        'entities', to_jsonb(v_entities),
        'relationships', to_jsonb(v_relationships),
        'observations', to_jsonb(v_promoted),
        'hypotheses', v_hypotheses -> 'hypotheses',
        'evidence', (v_hypotheses ->> 'evidence')::integer,
        'refused', v_refused);
END $fn$;
REVOKE ALL ON FUNCTION promote_proposal(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION promote_proposal(uuid) TO rk2_runtime;

COMMENT ON FUNCTION promote_proposal(uuid) IS
    'Turns one staged agent-run result into canonical Entities, Relationships, '
    'Observations, Hypotheses and evidence edges, in one transaction with the '
    'Events that record them. Every subject is canonicalized and scope-checked '
    'and every claim is grounded before its row exists; what cannot be grounded '
    'becomes a proposal_drops row rather than an exception.';


-- ---------------------------------------------------------------------------
-- 8. The record an agent reads
-- ---------------------------------------------------------------------------
-- One field added to the Hypothesis record, and it is the one a second hunter
-- needs: `statement` says what the claim is and `rationale` says what would
-- settle it, so a hunter deciding whether to propose the same thing again can
-- see whether the falsifier it has in mind was already written down. It lives
-- on `hypotheses`, so `rk2_revision` moves when it does and the record's digest
-- and its revision stay in step.
--
-- No evidence count here on purpose, however tempting: an edge is its own row
-- with no Event of its own -- 030 exempted `hypothesis_evidence` as `covered` --
-- so a count folded into this record would change the digest while leaving the
-- revision where it was, which is the trap 021 had to spend a `greatest()` on.
-- `v_evidence` already answers the question, row by row, with the polarity and
-- the role attached.

CREATE OR REPLACE VIEW v_records WITH (security_invoker = true) AS
SELECT r.kind,
       r.label,
       r.revision,
       encode(sha256(convert_to(r.record::text, 'utf8')), 'hex') AS digest,
       r.record
  FROM (
    SELECT 'entity'::text AS kind, e.label,
           -- The revision has to cover the record, and the record now carries
           -- this Entity's relationships. A Relationship is its own row with
           -- its own Events, so joining one changes the digest and leaves
           -- `rk2_revision('entities', ...)` where it was -- and `state.py`
           -- ranks by revision while a packet reader compares them. The
           -- greatest of the two is the revision of what is being read.
           greatest(rk2_revision('entities', e.id),
                    coalesce((SELECT max(rk2_revision('relationships', rel.id))
                                FROM relationships rel
                               WHERE rel.src_entity_id = e.id
                                  OR rel.dst_entity_id = e.id), 0)) AS revision,
           jsonb_build_object(
               'kind', 'entity',
               'label', e.label,
               'type', e.type,
               'in_scope', e.in_scope,
               'descriptor', rk2_descriptor(e.id),
               'identity_class', i.class,
               'scope_class', e.scope_class,
               'scope_tier', e.scope_tier,
               'origin', e.origin,
               'origins', (SELECT coalesce(jsonb_agg(DISTINCT o.origin), '[]'::jsonb)
                             FROM (SELECT e.origin AS origin
                                   UNION
                                   SELECT ep.origin FROM entity_provenance ep
                                    WHERE ep.entity_id = e.id) o),
               'parent_label', par.label,
               'relationships', (
                   SELECT coalesce(jsonb_agg(x.entry ORDER BY x.entry), '[]'::jsonb)
                     FROM (SELECT jsonb_build_object(
                                      'type', rel.type, 'direction', 'out',
                                      'label', other.label) AS entry
                             FROM relationships rel
                             JOIN entities other ON other.id = rel.dst_entity_id
                            WHERE rel.src_entity_id = e.id
                            UNION ALL
                           SELECT jsonb_build_object(
                                      'type', rel.type, 'direction', 'in',
                                      'label', other.label)
                             FROM relationships rel
                             JOIN entities other ON other.id = rel.src_entity_id
                            WHERE rel.dst_entity_id = e.id
                            ORDER BY 1 LIMIT 20) x),
               'relationship_count', (SELECT count(*) FROM relationships rel
                                       WHERE rel.src_entity_id = e.id
                                          OR rel.dst_entity_id = e.id),
               'first_seen_at', rk2_instant(e.first_seen_at),
               'last_seen_at', rk2_instant(e.last_seen_at)) AS record
      FROM entities e
      LEFT JOIN identities i ON i.entity_id = e.id
      LEFT JOIN services   cs ON cs.entity_id = e.id
      LEFT JOIN endpoints  ce ON ce.entity_id = e.id
      LEFT JOIN parameters cp ON cp.entity_id = e.id
      LEFT JOIN entities  par ON par.id = coalesce(cs.host_id, ce.application_id,
                                                   cp.endpoint_id)

    UNION ALL
    SELECT 'hypothesis', hy.label,
           rk2_revision('hypotheses', hy.id),
           jsonb_build_object(
               'kind', 'hypothesis',
               'label', hy.label,
               'status', hy.status,
               'property_class', hy.property_class,
               'statement', hy.statement,
               'rationale', hy.rationale,
               'subject_label', subj.label,
               'identity_a_label', ia.label,
               'identity_b_label', ib.label,
               'superseded_by_label', sup.label,
               'observed_fingerprint', hy.observed_fingerprint,
               'status_changed_at', rk2_instant(hy.status_changed_at),
               'created_at', rk2_instant(hy.created_at))
      FROM hypotheses hy
      LEFT JOIN entities subj ON subj.id = hy.subject_entity_id
      LEFT JOIN entities ia   ON ia.id   = hy.identity_a_entity_id
      LEFT JOIN entities ib   ON ib.id   = hy.identity_b_entity_id
      LEFT JOIN hypotheses sup ON sup.id = hy.superseded_by

    UNION ALL
    SELECT 'observation', o.label,
           rk2_revision('observations', o.id),
           jsonb_build_object(
               'kind', 'observation',
               'label', o.label,
               'observation_kind', o.kind,
               'summary', o.summary,
               'provenance_kind', o.provenance_kind,
               'subject_label', subj.label,
               'receipt_label', rc.label,
               'tool_run_label', tr.label,
               'observed_at', rk2_instant(o.observed_at))
      FROM observations o
      LEFT JOIN entities  subj ON subj.id = o.subject_entity_id
      LEFT JOIN receipts  rc   ON rc.id   = o.receipt_id
      LEFT JOIN tool_runs tr   ON tr.id   = o.tool_run_id

    UNION ALL
    SELECT 'receipt', rc.label,
           rk2_revision('receipts', rc.id),
           jsonb_build_object(
               'kind', 'receipt',
               'label', rc.label,
               'lane', rc.lane,
               'purpose', rc.purpose,
               'decision', rc.decision,
               'reason', rc.reason,
               'method', rc.method,
               'scheme', rc.scheme,
               'host', rc.host,
               'port', rc.port,
               'path', rc.path,
               'status_code', rc.status_code,
               'identity_label', idn.label,
               'tool_run_label', tr.label,
               'scope_class', rc.scope_class,
               'intercepted', rc.intercepted,
               'transport_citable', rc.transport_citable,
               'request_agent_sha', rc.request_agent_sha,
               'response_agent_sha', rc.response_agent_sha,
               'waited_ms', rc.waited_ms,
               'ts_arrival', rk2_instant(rc.ts_arrival))
      FROM receipts rc
      LEFT JOIN entities  idn ON idn.id = rc.identity_entity_id
      LEFT JOIN tool_runs tr  ON tr.id  = rc.tool_run_id

    UNION ALL
    SELECT 'tool_run', tr.label,
           rk2_revision('tool_runs', tr.id),
           jsonb_build_object(
               'kind', 'tool_run',
               'label', tr.label,
               'tool', tr.tool,
               'status', tr.status,
               'decision', tr.decision,
               'decision_reason', tr.decision_reason,
               'risk_class', tr.risk_class,
               'transport', tr.transport,
               'mcp_server', tr.mcp_server,
               'task_label', tk.label,
               'args_sha256', tr.args_sha256,
               'result_sha256', tr.result_sha256,
               'started_at', rk2_instant(tr.started_at),
               'finished_at', rk2_instant(tr.finished_at))
      FROM tool_runs tr
      LEFT JOIN tasks tk ON tk.id = tr.task_id

    UNION ALL
    SELECT 'task', tk.label,
           rk2_revision('tasks', tk.id),
           jsonb_build_object(
               'kind', 'task',
               'label', tk.label,
               'task_kind', tk.kind,
               'status', tk.status,
               'subject_label', subj.label,
               'hypothesis_label', hy.label,
               'finding_label', f.label,
               'skill_name', tk.skill_name,
               'priority', tk.priority,
               'expected_information_gain', tk.expected_information_gain,
               'potential_impact', tk.potential_impact,
               'novelty', tk.novelty,
               'estimated_cost', tk.estimated_cost,
               'confidence_of_execution', tk.confidence_of_execution,
               'attempts', tk.attempts,
               'abandoned_reason', tk.abandoned_reason,
               'created_at', rk2_instant(tk.created_at),
               'claimed_at', rk2_instant(tk.claimed_at),
               'finished_at', rk2_instant(tk.finished_at))
      FROM tasks tk
      LEFT JOIN entities   subj ON subj.id = tk.subject_entity_id
      LEFT JOIN hypotheses hy   ON hy.id   = tk.hypothesis_id
      LEFT JOIN findings   f    ON f.id    = tk.finding_id

    UNION ALL
    SELECT 'test', ts.label,
           rk2_revision('tests', ts.id),
           jsonb_build_object(
               'kind', 'test',
               'label', ts.label,
               'hypothesis_label', hy.label,
               'supersedes_label', prev.label,
               'spec_sha256', ts.spec_sha256,
               'created_at', rk2_instant(ts.created_at))
      FROM tests ts
      LEFT JOIN hypotheses hy ON hy.id = ts.hypothesis_id
      LEFT JOIN tests prev ON prev.id = ts.supersedes_test_id

    UNION ALL
    SELECT 'finding', f.label,
           rk2_revision('findings', f.id),
           jsonb_build_object(
               'kind', 'finding',
               'label', f.label,
               'status', f.status,
               'class_id', f.class_id,
               'title', f.title,
               'severity', f.severity,
               'cvss_vector', f.cvss_vector,
               'subject_label', subj.label,
               'duplicate_of_label', dup.label,
               'external_ref', f.external_ref,
               'validated_run_outcome', f.validated_run_outcome,
               'status_changed_at', rk2_instant(f.status_changed_at),
               'reported_at', rk2_instant(f.reported_at),
               'created_at', rk2_instant(f.created_at))
      FROM findings f
      LEFT JOIN entities subj ON subj.id = f.subject_entity_id
      LEFT JOIN findings dup  ON dup.id  = f.duplicate_of_finding_id
  ) r;

COMMENT ON VIEW v_records IS
    'Every labelled record this Program holds, with its revision and a digest of itself. The only identifier is the label.';


-- ---------------------------------------------------------------------------
-- 9. The standing check
-- ---------------------------------------------------------------------------
-- Five arms: two for what promotion can get wrong and three for the structures
-- that would make the first two meaningless. A transition rule that drifted
-- back to `llm`, a detached status guard and a dedup index rebuilt without
-- `NULLS NOT DISTINCT` all read as "no violations" from a query over
-- `hypotheses` alone, which is what a standing check is for.
--
-- No arm for an evidence edge that spans two Programs: 017 gave this table a
-- derived `program_id` and joined both its sides to it, so the key refuses one
-- and the check would be asking a question the key has already answered.

CREATE FUNCTION check_hypothesis_promotion()
RETURNS TABLE (problem text, subject text, detail text)
LANGUAGE sql STABLE AS $fn$
    -- 1. A promoted claim nothing stands behind. `no_support` refuses this at
    --    the staging boundary, so a row here is a claim that got in some other
    --    way -- and the transition machine will never move it anywhere.
    SELECT 'promoted_hypothesis_without_evidence', h.label,
           'a hypothesis_provenance row says a proposal produced it and no evidence edge supports it'
      FROM hypotheses h
     WHERE EXISTS (SELECT 1 FROM hypothesis_provenance hp
                    WHERE hp.hypothesis_id = h.id)
       AND NOT EXISTS (SELECT 1 FROM hypothesis_evidence he
                        WHERE he.hypothesis_id = h.id
                          AND he.polarity = 'supports'
                          AND he.role IN ('baseline','variant','control'))

  UNION ALL
    -- 2. A promoted claim that does not say what would refute it. 034 retains a
    --    refutation only where something said in advance what one would be, so
    --    an empty falsifier here is a Hypothesis no negative result can close.
    SELECT 'promoted_hypothesis_without_rationale', h.label,
           'rationale does not answer ' || rk2_rationale_missing(h.rationale)
      FROM hypotheses h
     WHERE EXISTS (SELECT 1 FROM hypothesis_provenance hp
                    WHERE hp.hypothesis_id = h.id)
       AND rk2_rationale_missing(h.rationale) IS NOT NULL

  UNION ALL
    -- 3. The transition rule this file changed, checked as a fact rather than
    --    as a migration that ran once. A seed re-applied from 007 would put
    --    `llm` back and nothing else would notice.
    SELECT 'hypothesis_transition_admits_non_runtime',
           t.from_status || ' -> ' || t.to_status,
           'required_actor_kind is ' || coalesce(t.required_actor_kind, 'null') ||
           '; only the runtime may move a Hypothesis'
      FROM transition_rules t
     WHERE t.machine = 'hypothesis'
       AND t.required_actor_kind IS DISTINCT FROM 'runtime'

  UNION ALL
    -- 4. The two triggers that make arm 3 mean anything. `hypotheses_status_guard`
    --    is what refuses a direct status write, and `hypothesis_transition_guard`
    --    is what reads `transition_rules` when a transition row is inserted.
    --    Either one detached and the actor rule is a table nothing consults --
    --    which reads as "no violations" from any query over statuses.
    SELECT 'hypothesis_status_trigger_detached', t.name,
           'the trigger that makes the transition table binding is missing or disabled'
      FROM (VALUES ('hypotheses_status_guard'),
                   ('hypothesis_transition_guard')) AS t(name)
     WHERE NOT EXISTS (
        SELECT 1 FROM pg_trigger g
         WHERE g.tgname = t.name AND NOT g.tgisinternal AND g.tgenabled <> 'D')

  UNION ALL
    -- 5. The dedup index itself. Every convergence in this file rests on it,
    --    and an index dropped or rebuilt without `NULLS NOT DISTINCT` would let
    --    two claims about the same anonymous caller both be canonical.
    SELECT 'hypothesis_dedup_index_missing', 'hypotheses_dedup_idx',
           'the unique index promotion converges on is absent or no longer treats NULL cells as equal'
     WHERE NOT EXISTS (
        SELECT 1 FROM pg_index i
          JOIN pg_class c ON c.oid = i.indexrelid
         WHERE c.relname = 'hypotheses_dedup_idx'
           AND i.indisunique
           AND i.indnullsnotdistinct)
$fn$;

REVOKE ALL ON FUNCTION check_hypothesis_promotion() FROM PUBLIC;

INSERT INTO standing_checks(name, query, owner_ticket, note) VALUES
    ('hypothesis_promotion', 'SELECT * FROM check_hypothesis_promotion()', '33',
     'every promoted Hypothesis names what supports it and what would refute it, and only the runtime can move one out of proposed');

COMMENT ON FUNCTION check_hypothesis_promotion() IS
    'What Hypothesis promotion can get wrong, as rows, plus the three '
    'structures that keep the first two of them empty by construction.';


-- ---------------------------------------------------------------------------
-- 10. The invariants this file must not have broken
-- ---------------------------------------------------------------------------

SELECT apply_state_rls();
SELECT apply_state_grants();

DO $$
DECLARE n integer; d text;
BEGIN
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_program_isolation();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-33 breaks program isolation (% problems): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || subject, '; ')
      INTO n, d FROM check_hypothesis_promotion();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-33 refuses to finish: % promotion violation(s): %', n, d;
    END IF;
END $$;
