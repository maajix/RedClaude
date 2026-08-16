-- ---------------------------------------------------------------------------
-- 20260820T000000Z__a_report_is_a_projection_of_what_holds.sql  (42)
-- ---------------------------------------------------------------------------
--
-- 034 built most of a Finding report and none of a chain report. It has the
-- block registry, the platform templates, `report_source_bundle`, the blockers,
-- the digest, the immutable `report_renderings` row and the approval gate that
-- names one -- and in the whole tree there is no code that reads any of it. The
-- renderer 034 was designed around was never written, so the bundle has been a
-- projection nobody projects and the templates have been an ordering nobody
-- orders.
--
-- This file is the half of 042 that belongs in the schema. The other half is
-- `src/redkraken/reporting.py`, which is the renderer itself and is pure: a
-- dict in, a string out, no connection in its signature. Named for the activity
-- because every module in the package already imports `outcome.report`.
--
-- Six criteria, and where each of them lives:
--
--   1. a pure renderer, no model, tools, target access or state mutation
--      -- `reporting.render`, which takes the bundle and not a connection. What
--      belongs here is that everything it needs is reachable from one STABLE
--      function, so there is nothing for it to go and fetch.
--   2. only validated Findings and sound, review-cleared chains render
--      -- `report_blockers` on the Finding side, unchanged; and on the chain
--      side `rk2_chain_unsoundness`, also unchanged. Section 4 says why the
--      chain side needs no gate of its own, which is the one decision in this
--      file that looks like an omission and is not.
--   3. scope, subjects, reproduction, baseline/variant/controls, impact,
--      limitations, evidence identifiers, remediation
--      -- sections 1 and 2 add the three blocks 034 had no place for, section 3
--      adds the three bundle keys they read, and section 6 makes "one form
--      carries all of them" a standing check rather than a promise.
--   4. composed versus executed end to end
--      -- section 4's `rk2_chain_execution`, which asks whether one Tool run's
--      stamps cover a whole root-to-leaf path.
--   5. equivalent rows in any order render byte-identically
--      -- every aggregate below carries ORDER BY, and the renderer sorts
--      nothing it was not given in order. Asserted by fixture in
--      tests/test_database.py and tests/test_reporting.py.
--   6. optional narrative, off by default, introducing no new fact
--      -- `reporting.render(bundle, narrative=...)`, checked against the bundle's
--      own scalars. The same rule 034 wrote for chain step params, applied to
--      prose instead of to slots.
--
-- One consequence worth stating before it surprises somebody: this file changes
-- what `report_source_bundle` returns, so it changes `finding_source_digest`,
-- so an approval recorded before it no longer matches its source and
-- `check_report_grounding`'s `approval_stale` arm will say so. That is the
-- correct answer rather than a migration defect -- the document a human
-- approved is not the document this schema now renders -- and the remedy is to
-- render and approve again.


-- ===========================================================================
-- 1. The blocks criterion 3 asks for, and which subject each belongs to
-- ===========================================================================
--
-- 034's registry has nine blocks and all nine are about a Finding. A chain
-- report needs four of its own, and three of the nine subjects criterion 3
-- names -- scope, controls, limitations -- have no block at all.
--
-- A block now says which subjects it may appear under, and a template says
-- which subject it is a form for. Without those two columns the registry could
-- not tell a chain form from a Finding form, and `report_source_bundle` would
-- happily hand a renderer the block list of a chain template.

ALTER TABLE report_blocks
    ADD COLUMN subjects text[] NOT NULL DEFAULT ARRAY['finding']
        CHECK (cardinality(subjects) >= 1
               AND subjects <@ ARRAY['chain', 'finding']::text[]);

COMMENT ON COLUMN report_blocks.subjects IS
  'Ticket 42: what this block can be a section of. A block is a renderer with a name, and the renderer for `severity_block` reads a CVSS vector that a chain does not have -- so the pairing is a fact about the block rather than a convention a template author is trusted with.';

ALTER TABLE report_templates
    ADD COLUMN subject text NOT NULL DEFAULT 'finding'
        CHECK (subject IN ('finding', 'chain'));

-- `complete` rather than a second registry of "which template is the real one".
-- Criterion 3 is a claim about a form, and a claim about a form needs a form to
-- be about: without this column the check in section 6 would have to name
-- `platform.long_form` as a literal, and a template renamed later would make the
-- check pass by asking nothing.
ALTER TABLE report_templates
    ADD COLUMN complete boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN report_templates.subject IS
  'Ticket 42: whether this form is a form for a Finding or for a kill chain. The two bundles are different shapes, so a template used against the wrong one is a refusal and not a sparse report.';

COMMENT ON COLUMN report_templates.complete IS
  'Ticket 42 criterion 3: this form carries every block the criterion names for its subject, and `check_report_projection` fails the gate if it stops doing so. Exactly one template per subject is the complete one; the others are deliberately shorter.';

INSERT INTO report_blocks (id, name, description, subjects) VALUES
 ('scope_block','Scope',
  'the Program, the scope document version in force, and what the policy says about this subject. Never wall-clock: the version is a number the Program carries.',
  ARRAY['chain','finding']),
 ('controls','Baseline, variant and control',
  'the validating Test''s actions grouped by the role each was written under, with the assertion verdicts the run recorded.',
  ARRAY['finding']),
 ('limitations','Limitations',
  'what this report does not establish, derived from state rather than authored: soft blockers, review signals, an incomplete cleanup, an assertion that could not be evaluated, evidence that may not be shown.',
  ARRAY['chain','finding']),
 ('chain_header','Chain header',
  'the chain label, the capabilities it started from, and how many steps it composes.',
  ARRAY['chain']),
 ('chain_composition','Composition',
  'criterion 4: whether each step was demonstrated separately and composed afterwards, or whether one run walked the whole chain.',
  ARRAY['chain']),
 ('chain_transitions','Transitions',
  'one entry per step in depth order -- what it required, what it obtained, against which subject and as which Identity -- and the capability edges between them.',
  ARRAY['chain']),
 ('chain_evidence','Chain evidence',
  'per step, the Receipt the transition assertion was read from and the digest of the Test specification that produced it.',
  ARRAY['chain']);


-- ===========================================================================
-- 2. The forms
-- ===========================================================================
--
-- `platform.long_form` is re-ordered rather than appended to. Three of its new
-- blocks belong in the middle of it -- scope is read before the impact
-- sentence, controls beside the reproduction, limitations before remediation --
-- and a form whose sections are in the wrong order is a form a triager reads in
-- the wrong order. Deleted and re-inserted whole because the ordinal is half
-- the primary key, so nine UPDATEs would collide with each other on the way
-- past.

DELETE FROM report_template_blocks WHERE template_id = 'platform.long_form';

INSERT INTO report_template_blocks (template_id, ordinal, block_id) VALUES
 ('platform.long_form', 1,'provenance_header'),
 ('platform.long_form', 2,'scope_block'),
 ('platform.long_form', 3,'impact_sentence'),
 ('platform.long_form', 4,'affected_assets'),
 ('platform.long_form', 5,'attack_chain'),
 ('platform.long_form', 6,'poc_payload'),
 ('platform.long_form', 7,'repro_steps'),
 ('platform.long_form', 8,'controls'),
 ('platform.long_form', 9,'evidence_manifest'),
 ('platform.long_form',10,'severity_block'),
 ('platform.long_form',11,'limitations'),
 ('platform.long_form',12,'remediation');

UPDATE report_templates SET complete = true WHERE id = 'platform.long_form';

-- `rk2.default` stays four blocks and stays on a screen. That is what its own
-- note says it is for, and a short form is not an incomplete one: the check in
-- section 6 asks the complete form and asks nothing of this one.

INSERT INTO report_templates (id, platform, name, notes, subject, complete) VALUES
 ('rk2.chain','rk2','redKraken chain',
  'the chain, what it obtained and how it was demonstrated. Fits on a screen.',
  'chain', false),
 ('platform.chain_long_form','generic','Long-form chain submission',
  'the same shape a platform form asks for, for a composition rather than for one Finding.',
  'chain', true);

INSERT INTO report_template_blocks (template_id, ordinal, block_id) VALUES
 ('rk2.chain',1,'chain_header'),
 ('rk2.chain',2,'chain_composition'),
 ('rk2.chain',3,'chain_transitions'),
 ('platform.chain_long_form',1,'chain_header'),
 ('platform.chain_long_form',2,'scope_block'),
 ('platform.chain_long_form',3,'chain_composition'),
 ('platform.chain_long_form',4,'chain_transitions'),
 ('platform.chain_long_form',5,'chain_evidence'),
 ('platform.chain_long_form',6,'limitations');


-- ===========================================================================
-- 3. What a Finding report says that 034's bundle could not
-- ===========================================================================
--
-- Rule 1 of 034 still holds and this file does not weaken it: `findings.title`,
-- `observations.summary`, `hypotheses.statement` and `tests.label` are
-- model-writable and none of them appears below either. Everything added here
-- is a column the runtime wrote or a digest it computed.

-- 034 left the third column of this view unaliased, so it is `?column?` and a
-- second reader cannot name it. Renamed rather than worked around: the arm that
-- reads it below would otherwise have to quote a name PostgreSQL invented.
ALTER VIEW report_review_signals RENAME COLUMN "?column?" TO detail;

-- What the report does NOT establish. Derived, never authored: a limitations
-- section a model wrote is a limitations section that says what its author
-- wanted a reader to worry about, and a triager reading it would learn nothing
-- about what the harness actually failed to show.
--
-- Soft blockers and review signals first, because those are the two places the
-- corpus already puts "worth saying, not disqualifying". The rest are the four
-- honest gaps a validated Finding can still have.
CREATE FUNCTION finding_limitations(p_finding uuid)
RETURNS TABLE (code text, detail text)
LANGUAGE sql STABLE AS $fn$
    SELECT 'soft_blocker', b.code || ': ' || b.detail
      FROM report_blockers(p_finding) b WHERE b.severity = 'soft'
    UNION ALL
    SELECT 'review_signal', s.code || ': ' || s.detail
      FROM report_review_signals s WHERE s.finding_id = p_finding
    UNION ALL
    -- The Test stated an undo and the run did not finish it. Whatever the
    -- report says was demonstrated, something was left behind.
    SELECT 'cleanup_incomplete',
           'the validating run left its cleanup ' || (tr.assertion_results ->> 'cleanup')
      FROM findings f JOIN test_runs tr ON tr.id = f.validated_by_test_run_id
     WHERE f.id = p_finding AND tr.assertion_results ->> 'cleanup' <> 'done'
    UNION ALL
    -- 035 records a null verdict for an assertion the runtime could not
    -- evaluate. The Finding is validated on the assertions that held; this
    -- names the ones that settled nothing either way.
    SELECT 'assertion_inconclusive',
           'assertion ' || (a ->> 'id') || ' could not be evaluated'
      FROM findings f
      JOIN test_runs tr ON tr.id = f.validated_by_test_run_id
      CROSS JOIN LATERAL jsonb_array_elements(tr.assertion_results -> 'assertions') a
     WHERE f.id = p_finding AND jsonb_typeof(a -> 'held') = 'null'
    UNION ALL
    -- One holding run is one observation. A target that is flaky in the right
    -- direction produces exactly this, and a reader deserves to know the count
    -- rather than to infer it from a report that reads like a certainty.
    SELECT 'single_observation',
           'the validating Test has held once, on ' || tr.lane
      FROM findings f JOIN test_runs tr ON tr.id = f.validated_by_test_run_id
     WHERE f.id = p_finding
       AND (SELECT count(*) FROM test_runs x
             WHERE x.test_id = tr.test_id AND x.outcome = 'holds') = 1
    UNION ALL
    -- 038 separates authorising an impact from proving one. A Finding whose
    -- effects were witnessed by an observation but never demonstrated through
    -- an impact run has an impact sentence that rests on inference.
    --
    -- Counted rather than named per effect. `finding_effects.effect_id` is a
    -- `report_effects` id and `impact_demonstrations.impact_class` is an
    -- `impact_classes` id; the two vocabularies exist for different purposes and
    -- nothing in the schema maps one onto the other, so no row here can say
    -- which effect a given demonstration proved. Saying that plainly is the
    -- limitation; a per-effect sentence keyed off a per-Finding predicate would
    -- name one effect and mean another.
    SELECT 'impact_not_demonstrated',
           n.witnessed::text || ' effect(s) are witnessed and '
             || n.demonstrated::text || ' impact run(s) demonstrated an impact class; '
             || 'the two vocabularies are not mapped onto one another, so the '
             || 'impact above is not established effect by effect'
      FROM (SELECT (SELECT count(*) FROM finding_effects fe
                     WHERE fe.finding_id = p_finding) AS witnessed,
                   (SELECT count(*) FROM impact_demonstrations d
                     WHERE d.finding_id = p_finding) AS demonstrated) n
     WHERE n.demonstrated < n.witnessed
    UNION ALL
    -- 006's two visibilities. A credential-bearing Artifact is one the report
    -- cannot quote, so the evidence list carries its hash and not its bytes,
    -- and saying so is better than a reader wondering why an excerpt is absent.
    SELECT 'evidence_withheld',
           'the response to ' || r.label || ' is credential-bearing and is cited by hash only'
      FROM (SELECT DISTINCT receipt_id FROM finding_cited_receipts
             WHERE finding_id = p_finding) x
      JOIN receipts r ON r.id = x.receipt_id
      JOIN artifacts a ON a.sha256 = r.response_agent_sha
     WHERE a.visibility = 'credential_bearing'
$fn$;

COMMENT ON FUNCTION finding_limitations(uuid) IS
  'Ticket 42 criterion 3: what a validated Finding''s report does not establish, read off state rather than written by anybody. Soft blockers, review signals, an unfinished cleanup, an assertion that settled nothing, a single holding run, an impact that was witnessed but never demonstrated, and evidence that may not be quoted.';

-- The bundle, re-created whole. Three keys are added and nothing is removed:
-- `kind` so a renderer given one of these knows which shape it has, `scope` and
-- `run` because criterion 3 names facts 034 had no key for, and `limitations`
-- because the function above has to reach the renderer somehow.
--
-- The role split criterion 3 asks for -- baseline, variant, control -- is NOT a
-- key here. `spec` already carries every action with the role it was written
-- under, and grouping them is what a renderer is for; a second grouped copy in
-- the bundle would be the same three lists in two places, drifting the first
-- time somebody edits one.
CREATE OR REPLACE FUNCTION report_source_bundle(p_finding uuid, p_template text)
RETURNS jsonb LANGUAGE sql STABLE AS $fn$
    SELECT jsonb_build_object(
      'kind',          'finding',
      'finding_label', f.label,
      'template',      p_template,
      -- The id AND the heading. 034 sent the id alone, which left the name in
      -- the registry with no reader and would have had the renderer carry a
      -- second copy of nine headings -- one to drift from the other the first
      -- time a platform's section was renamed.
      'blocks',        (SELECT jsonb_agg(jsonb_build_object('id', b.block_id, 'name', k.name)
                                         ORDER BY b.ordinal)
                          FROM report_template_blocks b
                          JOIN report_blocks k ON k.id = b.block_id
                         WHERE b.template_id = p_template),
      'class', (SELECT jsonb_build_object('id',vc.id,'name',vc.name,'cwe',vc.cwe_id,
                                          'short_name',vc.short_name,'remediation',vc.remediation)
                  FROM vulnerability_classes vc WHERE vc.id = f.class_id),
      'subject', (SELECT jsonb_build_object('dedup_key',e.dedup_key,'type',e.type,
                                            'method',ep.method,'path',ep.path_template,
                                            'base_url',app.base_url)
                    FROM entities e
                    LEFT JOIN endpoints ep ON ep.entity_id = e.id
                    LEFT JOIN applications app ON app.entity_id = ep.application_id
                   WHERE e.id = f.subject_entity_id),
      -- Criterion 3's scope. The version the Program is at now and the digest
      -- of the document it names, so a reader can tell two submissions made
      -- under two different policies apart, and what the policy projected onto
      -- this subject. `scope_class` rather than `in_scope` alone because 021
      -- has a fourth class for a subject with no address, and a Finding about
      -- a technology has one.
      'scope', (SELECT jsonb_build_object(
                         'program', pr.slug,
                         'version', pr.scope_version,
                         'policy_sha256', psv.policy_sha256,
                         'subject_class', e.scope_class,
                         'subject_in_scope', e.in_scope)
                  FROM programs pr
                  JOIN entities e ON e.id = f.subject_entity_id
                  LEFT JOIN program_scope_versions psv
                    ON psv.program_id = pr.id AND psv.version = pr.scope_version
                 WHERE pr.id = f.program_id),
      'provenance', (SELECT jsonb_build_object(
                              'lane', (SELECT string_agg(DISTINCT r.lane, ',') FROM finding_cited_receipts fcr
                                         JOIN receipts r ON r.id = fcr.receipt_id
                                        WHERE fcr.finding_id = f.id),
                              'at',   (SELECT to_char(min(r.ts_arrival) AT TIME ZONE 'UTC','HH24:MI:SS')
                                         FROM finding_cited_receipts fcr
                                         JOIN receipts r ON r.id = fcr.receipt_id
                                        WHERE fcr.finding_id = f.id))),
      'effects', (SELECT coalesce(jsonb_agg(jsonb_build_object('id',re.id,'phrase',re.phrase)
                                            ORDER BY fe.ordinal), '[]'::jsonb)
                    FROM finding_effects fe JOIN report_effects re ON re.id = fe.effect_id
                   WHERE fe.finding_id = f.id),
      -- Criterion 3 says "demonstrated impact" and `effects` above is not it:
      -- 038 draws the line between an effect an observation witnessed and an
      -- impact a run proved, and only the second has an after-state Receipt and
      -- a performed cleanup behind it. Both are carried, under the two words,
      -- so a triager reading the impact section is told which of the two each
      -- line is. Ordered by class rather than by insertion, because 038 admits
      -- one demonstration per Test run and two runs are not otherwise ordered.
      'demonstrations', (SELECT coalesce(jsonb_agg(jsonb_build_object(
                                  'class', d.impact_class,
                                  'description', ic.description,
                                  'after_state', r.label,
                                  'receipts', d.receipts,
                                  'cleanup_receipts', d.cleanup_receipts)
                                ORDER BY d.impact_class, r.label), '[]'::jsonb)
                           FROM impact_demonstrations d
                           JOIN impact_classes ic ON ic.impact_class = d.impact_class
                           JOIN receipts r ON r.id = d.after_state_receipt_id
                          WHERE d.finding_id = f.id),
      'technology', (SELECT te.name FROM finding_chain_step_citations c
                       JOIN finding_chain_steps st ON st.id = c.step_id
                       JOIN observations o ON o.id = c.observation_id
                       JOIN technologies te ON te.entity_id = o.subject_entity_id
                      WHERE st.finding_id = f.id AND o.kind = 'technology_identified'
                      ORDER BY st.ordinal, c.ordinal LIMIT 1),
      'chain', (SELECT coalesce(jsonb_agg(jsonb_build_object(
                          'ordinal', st.ordinal, 'label', m.label,
                          'template', m.template, 'params', st.params,
                          'citations', (SELECT coalesce(jsonb_agg(coalesce(r2.label, o2.label)
                                                        ORDER BY c2.ordinal), '[]'::jsonb)
                                          FROM finding_chain_step_citations c2
                                          LEFT JOIN receipts r2 ON r2.id = c2.receipt_id
                                          LEFT JOIN observations o2 ON o2.id = c2.observation_id
                                         WHERE c2.step_id = st.id))
                        ORDER BY st.ordinal), '[]'::jsonb)
                  FROM finding_chain_steps st JOIN report_mechanisms m ON m.id = st.mechanism_id
                 WHERE st.finding_id = f.id),
      'spec', (SELECT t.spec FROM test_runs tr JOIN tests t ON t.id = tr.test_id
                WHERE tr.id = f.validated_by_test_run_id),
      'spec_sha256', (SELECT t.spec_sha256 FROM test_runs tr JOIN tests t ON t.id = tr.test_id
                       WHERE tr.id = f.validated_by_test_run_id),
      -- What the validating run answered. The Test says what was attempted and
      -- this says what came of it, which is the half of criterion 3's
      -- "assertion outcomes" that a specification cannot carry.
      'run', (SELECT jsonb_build_object(
                       'outcome', tr.outcome,
                       'lane', tr.lane,
                       'cleanup', tr.assertion_results ->> 'cleanup',
                       'assertions', (SELECT coalesce(jsonb_agg(
                                                jsonb_build_object('id', a ->> 'id',
                                                                   'held', a -> 'held')
                                                ORDER BY a ->> 'id'), '[]'::jsonb)
                                        FROM jsonb_array_elements(
                                               tr.assertion_results -> 'assertions') a))
                FROM test_runs tr WHERE tr.id = f.validated_by_test_run_id),
      'evidence', (SELECT coalesce(jsonb_agg(jsonb_build_object(
                            'receipt', r.label, 'method', r.method, 'path', r.path,
                            'status', r.status_code,
                            'request_sha', r.request_agent_sha,
                            'response_sha', r.response_agent_sha,
                            'visibility', (SELECT a.visibility FROM artifacts a
                                            WHERE a.sha256 = r.response_agent_sha))
                          ORDER BY r.ts_arrival, r.label), '[]'::jsonb)
                     FROM (SELECT DISTINCT receipt_id FROM finding_cited_receipts
                            WHERE finding_id = f.id) x
                     JOIN receipts r ON r.id = x.receipt_id),
      'severity', jsonb_build_object(
            'vector', f.cvss_vector, 'band', f.severity,
            'score',  CASE WHEN f.cvss_vector IS NULL THEN NULL
                           ELSE cvss31_base_score(f.cvss_vector) END,
            'origin', 'computed by the runtime from witnessed effects; not adjudicated'),
      'limitations', (SELECT coalesce(jsonb_agg(jsonb_build_object('code',l.code,'detail',l.detail)
                                                ORDER BY l.code, l.detail), '[]'::jsonb)
                        FROM finding_limitations(f.id) l),
      -- With the severity, which 034 dropped. Criterion 2 turns on the
      -- difference -- a hard blocker refuses the render and a soft one becomes
      -- a limitation -- and a renderer given codes alone would have to decide
      -- which was which from a second copy of `report_blockers`'s own table.
      'blockers', (SELECT coalesce(jsonb_agg(jsonb_build_object(
                                     'severity',severity,'code',code,'detail',detail)
                                   ORDER BY severity, code, detail), '[]'::jsonb)
                     FROM report_blockers(f.id))
    )
    FROM findings f WHERE f.id = p_finding
      AND EXISTS (SELECT 1 FROM report_templates t
                   WHERE t.id = p_template AND t.subject = 'finding');
$fn$;

COMMENT ON FUNCTION report_source_bundle(uuid, text) IS
  'Ticket 19, extended by ticket 42: everything a Finding report may say, and the whole of it. Answers NULL for a template that is not a Finding form, so a chain template cannot produce a report with every block missing.';

-- ---------------------------------------------------------------------------
-- The composition, which is not one of the six criteria and is here because
-- without it none of them can be met
-- ---------------------------------------------------------------------------
--
-- 034 designed `finding_effects` and `finding_chain_steps`, made `no_effect`
-- and `no_chain` HARD blockers on them, and left both tables with no writer.
-- Nothing in the tree has ever inserted a row into either. So every Finding in
-- existence carries two hard blockers, criterion 2 refuses all of them, and
-- criterion 3's "demonstrated impact" and "reproduction" sections would print
-- from two tables that are always empty. A renderer that can render nothing is
-- not an implementation of this ticket.
--
-- The rows cannot be derived. `report_effects` is eleven phrases and
-- `impact_classes` is six classes with no mapping between them, and
-- `finding_effects.witness_observation_id` is NOT NULL -- which observation
-- witnesses which effect is a judgement, not a join. Same for the chain: which
-- mechanism sentences describe this Finding, in what order, citing which rows.
-- So the judgement is a parameter and this function is what validates it.
--
-- Almost nothing is validated HERE, on purpose. 034 already put the rules on
-- the tables: `chain_step_grounding` checks the slots, the no-new-facts rule
-- and the citation minimum; `chain_citation_agent_lane` and its sibling check
-- the lane; the foreign keys check the vocabulary and the Program. Restating
-- any of that would be two rulebooks that agree until the day one is edited.
-- What this adds is the three things a trigger cannot say: which Program is
-- asking, that a composition with no effects or no steps is a no-op dressed as
-- a success, and a refusal an agent can read instead of a transaction that
-- aborts at commit.
--
-- The last one is why `SET CONSTRAINTS` appears. `chain_step_grounding` is
-- DEFERRABLE INITIALLY DEFERRED, so it fires when the caller commits -- long
-- after the call that was wrong, in a transaction that may hold other work.
-- Making it immediate for the length of this function, inside a block that
-- catches, turns a commit-time abort into a returned sentence and leaves the
-- caller's transaction intact.
--
-- Re-composing replaces. A Finding whose evidence grew has a better report to
-- make, and the previous rendering's digest stops matching -- which is
-- `approval_stale` doing its job, not damage.
CREATE FUNCTION compose_finding_report(p_finding uuid, p_composition jsonb)
RETURNS jsonb LANGUAGE plpgsql AS $fn$
DECLARE
    p          uuid := rk2_program_required();
    v_effects  jsonb := p_composition -> 'effects';
    v_steps    jsonb := p_composition -> 'steps';
    v_refusal  text;
    v_step     jsonb;
    v_ordinal  int := 0;
    v_step_id  uuid;
    v_cites    int := 0;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM findings WHERE id = p_finding AND program_id = p) THEN
        RETURN jsonb_build_object('outcome','refused',
          'refusal','no Finding of this Program is recorded under that id');
    END IF;
    IF jsonb_typeof(v_effects) IS DISTINCT FROM 'array' OR jsonb_array_length(v_effects) = 0 THEN
        RETURN jsonb_build_object('outcome','refused',
          'refusal','effects must be a non-empty array: a composition with no effect leaves the no_effect blocker standing');
    END IF;
    IF jsonb_typeof(v_steps) IS DISTINCT FROM 'array' OR jsonb_array_length(v_steps) = 0 THEN
        RETURN jsonb_build_object('outcome','refused',
          'refusal','steps must be a non-empty array: a composition with no step leaves the no_chain blocker standing');
    END IF;

    BEGIN
        -- Citations cascade from the steps; the effects have no children.
        DELETE FROM finding_chain_steps WHERE finding_id = p_finding AND program_id = p;
        DELETE FROM finding_effects     WHERE finding_id = p_finding AND program_id = p;

        INSERT INTO finding_effects (program_id, finding_id, ordinal, effect_id,
                                     witness_observation_id)
        SELECT p, p_finding, e.ordinality, e.value ->> 'effect',
               (e.value ->> 'witness')::uuid
          FROM jsonb_array_elements(v_effects) WITH ORDINALITY AS e(value, ordinality);

        FOR v_step IN SELECT value FROM jsonb_array_elements(v_steps) LOOP
            v_ordinal := v_ordinal + 1;
            INSERT INTO finding_chain_steps (program_id, finding_id, ordinal,
                                             mechanism_id, params)
            VALUES (p, p_finding, v_ordinal, v_step ->> 'mechanism',
                    coalesce(v_step -> 'params', '{}'::jsonb))
            RETURNING id INTO v_step_id;

            INSERT INTO finding_chain_step_citations (program_id, step_id, ordinal,
                                                      receipt_id, observation_id)
            SELECT p, v_step_id, c.ordinality,
                   (c.value ->> 'receipt')::uuid, (c.value ->> 'observation')::uuid
              FROM jsonb_array_elements(coalesce(v_step -> 'citations', '[]'::jsonb))
                   WITH ORDINALITY AS c(value, ordinality);
            v_cites := v_cites + coalesce(jsonb_array_length(v_step -> 'citations'), 0);
        END LOOP;

        -- Everything 034 defers to commit, asked for here instead.
        SET CONSTRAINTS chain_step_grounding IMMEDIATE;
    EXCEPTION WHEN raise_exception OR foreign_key_violation OR check_violation
                OR unique_violation OR not_null_violation OR invalid_text_representation THEN
        v_refusal := SQLERRM;
    END;

    SET CONSTRAINTS chain_step_grounding DEFERRED;
    IF v_refusal IS NOT NULL THEN
        RETURN jsonb_build_object('outcome','refused','refusal',v_refusal);
    END IF;

    -- What still stands between this Finding and a report, in the vocabulary
    -- that already answers that question. `unwitnessed_effect` is the one the
    -- caller just caused; it is returned the same way as the ones it did not,
    -- because a composer that graded its own input would be a second copy of
    -- `report_blockers` that starts out agreeing.
    RETURN jsonb_build_object(
      'outcome','composed',
      'effects',   jsonb_array_length(v_effects),
      'steps',     v_ordinal,
      'citations', v_cites,
      'blockers', (SELECT coalesce(jsonb_agg(jsonb_build_object('code',b.code,'detail',b.detail)
                                             ORDER BY b.code, b.detail), '[]'::jsonb)
                     FROM report_blockers(p_finding) b WHERE b.severity = 'hard'));
END $fn$;

COMMENT ON FUNCTION compose_finding_report(uuid, jsonb) IS
  'Ticket 42: write the impact and reproduction halves of a Finding, which 034 designed, made hard blockers of, and gave no writer. Takes the hunter''s judgement -- which effects, witnessed by which observations, described by which mechanism sentences citing which rows -- and lets 034''s own triggers rule on it, immediately rather than at commit. Replaces any previous composition. Returns the hard blockers that remain.';


-- ===========================================================================
-- 4. The chain side
-- ===========================================================================
--
-- Criterion 2 asks that only "sound, review-cleared chains" render, and there
-- is deliberately no `chain_report_blockers` below. It would have exactly one
-- arm. `rk2_chain_unsoundness` already asks 039's question of every step, the
-- four a chain has of its own, and -- in its arm (f) -- the two review gates
-- that hold a member: `known_issue` and `duplicate`. A chain gate of this
-- file's own would be that function called through a wrapper.
--
-- The six blockers 040 left out stay out, and now for a reason it could only
-- half state. `no_effect`, `no_chain` and `unwitnessed_effect` hold a Finding's
-- OWN report because they empty its impact sentence and its attack chain; a
-- chain report renders neither, so a member missing them is a member whose own
-- report is unrenderable and whose pivot is untouched. `cvss_stale` and
-- `severity_unstated` are about a severity band no chain report prints.
-- `not_validated` fires on a member that has been reported, and a chain is
-- most worth having exactly when its strongest member has been submitted.

-- Criterion 4, as a computation rather than as a flag somebody sets.
--
-- Every stamp names the Tool run that demonstrated it. Composition is the
-- normal case: N stamps from N runs, each proving one transition, joined
-- afterwards by capabilities. An end-to-end execution is the case where one run
-- did the whole walk -- so its stamps cover a path from a step nothing feeds
-- into to a step that feeds nothing.
--
-- Asked over a graph restricted to one run at a time. A walk that changed runs
-- half way is two demonstrations and is what composition already means, so the
-- recursive term joins on the run as well as on the edge.
CREATE FUNCTION rk2_chain_execution(p_program uuid, p_chain uuid) RETURNS text
LANGUAGE sql STABLE AS $fn$
    WITH RECURSIVE member AS (
        SELECT cs.stamp_id, s.tool_run_id
          FROM chain_steps cs JOIN pivot_stamps s ON s.id = cs.stamp_id
         WHERE cs.chain_id = p_chain AND cs.program_id = p_program
    ),
    walk AS (
        SELECT m.tool_run_id, m.stamp_id
          FROM member m
         WHERE NOT EXISTS (SELECT 1 FROM chain_edges e
                            WHERE e.chain_id = p_chain AND e.to_stamp_id = m.stamp_id)
        UNION
        SELECT w.tool_run_id, e.to_stamp_id
          FROM walk w
          JOIN chain_edges e ON e.chain_id = p_chain AND e.from_stamp_id = w.stamp_id
          JOIN member m ON m.stamp_id = e.to_stamp_id AND m.tool_run_id = w.tool_run_id
    )
    SELECT CASE WHEN EXISTS (
                    SELECT 1 FROM walk w
                     WHERE NOT EXISTS (SELECT 1 FROM chain_edges e
                                        WHERE e.chain_id = p_chain
                                          AND e.from_stamp_id = w.stamp_id))
                THEN 'executed' ELSE 'composed' END
$fn$;

COMMENT ON FUNCTION rk2_chain_execution(uuid, uuid) IS
  'Ticket 42 criterion 4: `executed` when one Tool run''s stamps cover a whole root-to-leaf path of this chain, `composed` otherwise. A stamp names the run that demonstrated it, so the difference between "each step was shown separately" and "one run walked the chain" is a fact about the stamps and not a claim anybody makes.';

CREATE FUNCTION chain_limitations(p_program uuid, p_chain uuid)
RETURNS TABLE (code text, detail text)
LANGUAGE sql STABLE AS $fn$
    -- A chain with two roots or two leaves is more than one route, and "the
    -- chain" in a report about it is a figure of speech. Said once here rather
    -- than left for a reader to count off the transitions.
    SELECT 'multiple_routes',
           'the composition has ' || r.roots || ' entry step(s) and ' || r.leaves
           || ' terminal step(s), so it is more than one route'
      FROM (SELECT count(*) FILTER (
                     WHERE NOT EXISTS (SELECT 1 FROM chain_edges e
                                        WHERE e.chain_id = p_chain
                                          AND e.to_stamp_id = cs.stamp_id)) AS roots,
                   count(*) FILTER (
                     WHERE NOT EXISTS (SELECT 1 FROM chain_edges e
                                        WHERE e.chain_id = p_chain
                                          AND e.from_stamp_id = cs.stamp_id)) AS leaves
              FROM chain_steps cs
             WHERE cs.chain_id = p_chain AND cs.program_id = p_program) r
     WHERE r.roots > 1 OR r.leaves > 1
    UNION ALL
    -- Every member's own limitations, carried up under the member that has
    -- them. A chain is at most as well established as the steps it is made of,
    -- and a limitation stated on a Finding's report and dropped from the chain
    -- report composed on it would be a limitation the composition hid.
    SELECT 'member_' || l.code, 'member ' || f.label || ': ' || l.detail
      FROM chain_steps cs
      JOIN pivot_stamps s ON s.id = cs.stamp_id
      JOIN findings f ON f.id = s.finding_id
      CROSS JOIN LATERAL finding_limitations(f.id) l
     WHERE cs.chain_id = p_chain AND cs.program_id = p_program
$fn$;

COMMENT ON FUNCTION chain_limitations(uuid, uuid) IS
  'Ticket 42 criterion 3, on the chain side: what a sound chain''s report does not establish. Its own -- that a branching composition is several routes -- and every limitation of every member, named with the member it belongs to.';

-- The chain bundle. Built on 040's own reads rather than beside them:
-- `rk2_chain_unsoundness` decides, and an unsound chain answers with the reason
-- and no steps, which is exactly what `read_kill_chain` does and for the same
-- argument. What is added over that read is what a report needs and a caller
-- acting on the chain does not: the form, the scope, the evidence identifiers,
-- the limitations, and criterion 4's word.
CREATE FUNCTION chain_source_bundle(p_chain uuid, p_template text)
RETURNS jsonb LANGUAGE plpgsql STABLE AS $fn$
DECLARE
    p       uuid := rk2_program_required();
    v_chain chains%ROWTYPE;
    v_why   text;
    v_form  jsonb;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM report_templates t
                    WHERE t.id = p_template AND t.subject = 'chain') THEN
        RETURN NULL;
    END IF;

    SELECT * INTO v_chain FROM chains WHERE id = p_chain AND program_id = p;
    IF NOT FOUND THEN
        RETURN jsonb_build_object(
            'kind', 'chain', 'chain', NULL, 'template', p_template,
            'sound', false,
            'unsound', 'no chain of this Program is recorded under that id');
    END IF;

    v_form := jsonb_build_object(
        'kind', 'chain', 'chain', v_chain.label, 'template', p_template,
        'blocks', (SELECT jsonb_agg(jsonb_build_object('id', b.block_id, 'name', k.name)
                                    ORDER BY b.ordinal)
                     FROM report_template_blocks b
                     JOIN report_blocks k ON k.id = b.block_id
                    WHERE b.template_id = p_template));

    v_why := rk2_chain_unsoundness(p, p_chain);
    IF v_why IS NOT NULL THEN
        RETURN v_form || jsonb_build_object('sound', false, 'unsound', v_why);
    END IF;

    RETURN v_form || jsonb_build_object(
        'sound', true,
        'unsound', NULL,
        'entry', to_jsonb(v_chain.entry),
        'source_sha256', v_chain.source_sha256,
        'execution', rk2_chain_execution(p, p_chain),
        'scope', (SELECT jsonb_build_object(
                           'program', pr.slug,
                           'version', pr.scope_version,
                           'policy_sha256', psv.policy_sha256)
                    FROM programs pr
                    LEFT JOIN program_scope_versions psv
                      ON psv.program_id = pr.id AND psv.version = pr.scope_version
                   WHERE pr.id = p),
        'steps', (SELECT coalesce(jsonb_agg(jsonb_build_object(
                             'stamp', s.label, 'depth', cs.depth,
                             'member', f.label, 'class', f.class_id,
                             'subject', e.label, 'identity', i.slot_name,
                             'transition', s.transition,
                             'provides', s.provides,
                             'requires', to_jsonb(s.requires),
                             'conditions', s.conditions)
                         ORDER BY cs.depth, s.label), '[]'::jsonb)
                    FROM chain_steps cs
                    JOIN pivot_stamps s ON s.id = cs.stamp_id
                    JOIN findings f ON f.id = s.finding_id
                    JOIN entities e ON e.id = s.subject_entity_id
                    JOIN identities i ON i.entity_id = s.identity_entity_id
                   WHERE cs.chain_id = p_chain),
        'edges', (SELECT coalesce(jsonb_agg(jsonb_build_object(
                             'from', u.label, 'to', d.label,
                             'capability', ce.capability)
                         ORDER BY u.label, d.label, ce.capability), '[]'::jsonb)
                    FROM chain_edges ce
                    JOIN pivot_stamps u ON u.id = ce.from_stamp_id
                    JOIN pivot_stamps d ON d.id = ce.to_stamp_id
                   WHERE ce.chain_id = p_chain),
        'evidence', (SELECT coalesce(jsonb_agg(jsonb_build_object(
                               'stamp', s.label,
                               'receipt', r.label,
                               'method', r.method, 'path', r.path,
                               'status', r.status_code,
                               'spec_sha256', s.source ->> 'test_spec')
                           ORDER BY s.label), '[]'::jsonb)
                       FROM chain_steps cs
                       JOIN pivot_stamps s ON s.id = cs.stamp_id
                       JOIN receipts r ON r.id = s.transition_receipt_id
                      WHERE cs.chain_id = p_chain),
        'limitations', (SELECT coalesce(jsonb_agg(
                                  jsonb_build_object('code', l.code, 'detail', l.detail)
                                  ORDER BY l.code, l.detail), '[]'::jsonb)
                          FROM chain_limitations(p, p_chain) l));
END $fn$;

COMMENT ON FUNCTION chain_source_bundle(uuid, text) IS
  'Ticket 42: everything a kill chain report may say, and the whole of it. An unsound chain answers with the reason and no steps, which is 040''s decision restated where the renderer reads it; a template that is not a chain form answers NULL.';

-- The digest, on 034's rule and for 034's reason: what identifies the document
-- is what it says, and the gate evaluated when somebody acts on it is not part
-- of that. On the chain side the gate is `sound`/`unsound` rather than a
-- `blockers` array, so those two are what comes out.
CREATE FUNCTION chain_source_digest(p_chain uuid, p_template text) RETURNS text
LANGUAGE sql STABLE AS $fn$
    SELECT encode(sha256(convert_to(
             ((chain_source_bundle(p_chain, p_template) - 'sound') - 'unsound')::text,
             'UTF8')), 'hex');
$fn$;

COMMENT ON FUNCTION chain_source_digest(uuid, text) IS
  'Ticket 42: the identity of a rendered chain report, over everything in the bundle except whether it may be rendered right now. 034''s argument for leaving `blockers` out of the Finding digest, applied to the pair that answers the same question here.';


-- ===========================================================================
-- 5. Reading one
-- ===========================================================================
--
-- Two functions the runtime calls, so that `reporting.py` names a verb rather than
-- assembling a query. Both are STABLE and read-only: criterion 1's "no state
-- mutation" is a property of the whole path from the command to the bytes, and
-- a read surface that could write would make it a property of nobody.

CREATE FUNCTION read_finding_report(p_finding uuid, p_template text) RETURNS jsonb
LANGUAGE sql STABLE AS $fn$
    SELECT report_source_bundle(f.id, p_template)
             || jsonb_build_object('digest', finding_source_digest(f.id, p_template))
      FROM findings f
     WHERE f.program_id = rk2_program_required() AND f.id = p_finding
       AND EXISTS (SELECT 1 FROM report_templates t
                    WHERE t.id = p_template AND t.subject = 'finding');
$fn$;

COMMENT ON FUNCTION read_finding_report(uuid, text) IS
  'Ticket 42: the source bundle of one Finding of the bound Program, with its digest. NULL for a Finding of another Program or a template that is not a Finding form -- the two cases where there is nothing to render rather than something that must not be rendered.';

CREATE FUNCTION read_chain_report(p_chain uuid, p_template text) RETURNS jsonb
LANGUAGE sql STABLE AS $fn$
    SELECT CASE WHEN b IS NULL THEN NULL
                ELSE b || jsonb_build_object('digest',
                            chain_source_digest(p_chain, p_template)) END
      FROM (SELECT chain_source_bundle(p_chain, p_template) AS b) s;
$fn$;

COMMENT ON FUNCTION read_chain_report(uuid, text) IS
  'Ticket 42: the source bundle of one kill chain of the bound Program, with its digest. The Program comes from the session, as it does for `read_kill_chain`.';

-- The one write in this file, and the row 034 designed and left unreachable.
-- `enforce_report_approval` names a `report_renderings` row, nothing in the tree
-- ever made one, so the approval gate has so far been a door onto a wall.
--
-- Two of the four columns a caller could get wrong are not taken from the
-- caller. The digest is recomputed here and the content hash is taken over the
-- bytes handed in, so a rendering cannot claim to be a projection of a source it
-- was not made from -- which is the whole load-bearing property of the approval
-- gate above. What IS taken on trust is that the content is what the renderer
-- produced from that bundle: SQL cannot re-render, and a second renderer here
-- would be the first one written twice.
CREATE FUNCTION record_rendering(
    p_finding uuid, p_template text, p_content text, p_renderer text
) RETURNS jsonb LANGUAGE plpgsql AS $fn$
DECLARE
    p       uuid := rk2_program_required();
    v_id    uuid;
    v_digest text;
    v_hard  text;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM findings WHERE id = p_finding AND program_id = p) THEN
        RETURN jsonb_build_object('outcome','refused',
          'refusal','no Finding of this Program is recorded under that id');
    END IF;

    SELECT string_agg(b.code || ': ' || b.detail, '; ' ORDER BY b.code) INTO v_hard
      FROM report_blockers(p_finding) b WHERE b.severity = 'hard';
    IF v_hard IS NOT NULL THEN
        -- Criterion 2 where it costs something. The renderer refuses to produce
        -- bytes for a blocked Finding, and this refuses to keep bytes for one,
        -- so a rendering made before a blocker appeared cannot be filed after.
        RETURN jsonb_build_object('outcome','blocked','refusal',v_hard);
    END IF;

    v_digest := finding_source_digest(p_finding, p_template);
    IF v_digest IS NULL THEN
        RETURN jsonb_build_object('outcome','refused',
          'refusal', p_template || ' is not a Finding form');
    END IF;

    INSERT INTO report_renderings
        (program_id, finding_id, template_id, source_digest,
         content, content_sha256, renderer_version)
    VALUES (p, p_finding, p_template, v_digest, p_content,
            encode(sha256(convert_to(p_content,'UTF8')),'hex'), p_renderer)
    RETURNING id INTO v_id;

    RETURN jsonb_build_object('outcome','recorded','rendering',v_id,
      'source_digest',v_digest,
      'content_sha256',encode(sha256(convert_to(p_content,'UTF8')),'hex'));
END $fn$;

COMMENT ON FUNCTION record_rendering(uuid, text, text, text) IS
  'Ticket 42: file the exact bytes a human is to read, so that ticket 19''s approval gate has a row to name. The source digest and the content hash are computed here rather than accepted, because those two are what the gate compares.';


-- ===========================================================================
-- 6. The rules, as a query
-- ===========================================================================

CREATE FUNCTION rk2_report_required_blocks(p_subject text) RETURNS text[]
LANGUAGE sql IMMUTABLE AS $fn$
    SELECT CASE p_subject
        -- Criterion 3, word for word, mapped onto the registry: scope,
        -- affected subjects, reproduction, baseline/variant/controls,
        -- demonstrated impact, limitations, evidence identifiers, remediation.
        -- `provenance_header` is not in the criterion and is not required here.
        WHEN 'finding' THEN ARRAY['scope_block','affected_assets','repro_steps',
                                  'controls','impact_sentence','limitations',
                                  'evidence_manifest','remediation']
        -- The chain form's own reading of the same sentence. There is no
        -- remediation block: a chain's remediation is its members', and a
        -- report that restated it would be restating nine curated paragraphs
        -- nobody wrote about the composition.
        WHEN 'chain'   THEN ARRAY['scope_block','chain_header','chain_composition',
                                  'chain_transitions','chain_evidence','limitations']
    END
$fn$;

COMMENT ON FUNCTION rk2_report_required_blocks(text) IS
  'Ticket 42 criterion 3: the blocks a complete form must carry, in one place so that the check and the seeded templates cannot disagree. A criterion stated as a literal inside a check is a criterion that stops being checked the day somebody edits the check.';

CREATE FUNCTION check_report_projection()
RETURNS TABLE (rule text, obj text, detail text)
LANGUAGE sql STABLE AS $fn$
    -- 1. the complete form of each subject carries every block criterion 3
    --    names for it
    SELECT 'submission_incomplete', t.id, b
      FROM report_templates t
      CROSS JOIN LATERAL unnest(rk2_report_required_blocks(t.subject)) b
     WHERE t.complete
       AND NOT EXISTS (SELECT 1 FROM report_template_blocks tb
                        WHERE tb.template_id = t.id AND tb.block_id = b)
    UNION ALL
    -- 2. exactly one complete form per subject, or "the complete form" names
    --    nothing
    SELECT 'complete_form_missing', s.subject,
           (SELECT count(*) FROM report_templates t
             WHERE t.subject = s.subject AND t.complete)::text || ' complete form(s)'
      FROM (SELECT DISTINCT subject FROM report_templates) s
     WHERE (SELECT count(*) FROM report_templates t
             WHERE t.subject = s.subject AND t.complete) <> 1
    UNION ALL
    -- 3. a form does not include a block that is not about its subject
    SELECT 'block_subject_mismatch', t.id || '/' || tb.block_id, t.subject
      FROM report_template_blocks tb
      JOIN report_templates t ON t.id = tb.template_id
      JOIN report_blocks b ON b.id = tb.block_id
     WHERE NOT (t.subject = ANY (b.subjects))
    UNION ALL
    -- 4. a form with no blocks renders an empty document, which is worse than
    --    refusing: it is a report that says nothing and looks like one
    SELECT 'template_empty', t.id, 'no blocks'
      FROM report_templates t
     WHERE NOT EXISTS (SELECT 1 FROM report_template_blocks tb
                        WHERE tb.template_id = t.id)
    UNION ALL
    -- 5. a block whose ordinals skip or start late is a form somebody edited
    --    half way. The renderer reads them in order and would not notice.
    SELECT 'template_ordinals', t.id,
           'ordinals run to ' || max(tb.ordinal)::text || ' over '
           || count(*)::text || ' block(s)'
      FROM report_templates t JOIN report_template_blocks tb ON tb.template_id = t.id
     GROUP BY t.id
    HAVING max(tb.ordinal) <> count(*) OR min(tb.ordinal) <> 1
    UNION ALL
    -- 6. a chain step whose parameters do not fill a slot its mechanism
    --    declares. 034 checks that a mechanism's declared slots are the ones
    --    its sentence uses; this is the other half, and it is 042's because a
    --    renderer is what turns an unfilled slot into a report with `{path}`
    --    printed in it where the path should be.
    SELECT 'step_slot_unfilled', f.label || ' step ' || st.ordinal::text, s
      FROM finding_chain_steps st
      JOIN findings f ON f.id = st.finding_id
      JOIN report_mechanisms m ON m.id = st.mechanism_id
      CROSS JOIN LATERAL unnest(m.slots) s
     WHERE NOT (st.params ? s);
$fn$;

COMMENT ON FUNCTION check_report_projection() IS
  'Ticket 42: the report forms as an invariant. A complete form carries every block its criterion names, each subject has exactly one, no form mixes a block that is not about its subject, and no form is empty or half-numbered. Zero rows is the invariant.';


-- ===========================================================================
-- Z. Wiring
-- ===========================================================================
--
-- No new table, so there is no purge edge, no event exemption and no grant to
-- issue. What this file adds is three columns on two reference tables 034
-- already registered, and the read surface is per-column since ticket 33.

INSERT INTO state_read_surface (table_name, column_name, added_by) VALUES
 ('report_blocks',    'subjects', '42'),
 ('report_templates', 'subject',  '42'),
 ('report_templates', 'complete', '42');

INSERT INTO standing_checks (name, query, owner_ticket, note) VALUES
 ('report_projection', 'SELECT * FROM check_report_projection()', '42',
  'the complete form of each subject carries every block its criterion names, no form mixes subjects, and no form is empty or half-numbered');

DO $$
DECLARE n integer; d text; b text;
BEGIN
    -- The seven blocks this file adds are reachable from a template, which is
    -- 034's first grounding rule and the one an added block breaks by default.
    FOREACH b IN ARRAY ARRAY['scope_block','controls','limitations','chain_header',
                             'chain_composition','chain_transitions','chain_evidence'] LOOP
        IF NOT EXISTS (SELECT 1 FROM report_template_blocks WHERE block_id = b) THEN
            RAISE EXCEPTION 'ph2-42 registered block % and put it in no form', b;
        END IF;
    END LOOP;

    -- Criterion 3 as a property of the text rather than of a run. A later edit
    -- that dropped one of the three keys would leave every new block rendering
    -- nothing, and every fixture that renders a complete form would still pass
    -- if it only asserted that the form has sections.
    FOREACH b IN ARRAY ARRAY['''scope''', '''run''', '''limitations'''] LOOP
        IF (SELECT p.prosrc FROM pg_proc p
             WHERE p.pronamespace = 'public'::regnamespace
               AND p.proname = 'report_source_bundle') NOT LIKE '%' || b || '%' THEN
            RAISE EXCEPTION 'report_source_bundle no longer carries %', b;
        END IF;
    END LOOP;

    -- 040's arm (f) is what criterion 2 leans on for chains, and section 4
    -- argues from its shape. An edit that widened it to every hard code would
    -- make that argument false and this file would not notice.
    IF (SELECT p.prosrc FROM pg_proc p
         WHERE p.pronamespace = 'public'::regnamespace
           AND p.proname = 'rk2_chain_unsoundness')
       !~ 'b\.code IN \(''known_issue'', ''duplicate''\)' THEN
        RAISE EXCEPTION 'rk2_chain_unsoundness no longer asks the two review gates 042 rests on';
    END IF;

    -- `compose_finding_report` makes 034's deferred grounding trigger immediate
    -- for the length of one call, which is only possible while it is deferrable
    -- and named this. Dropping the DEFERRABLE would turn every refusal that
    -- function returns into an error raised from `SET CONSTRAINTS` itself.
    IF NOT EXISTS (SELECT 1 FROM pg_trigger
                    WHERE tgname = 'chain_step_grounding'
                      AND tgrelid = 'finding_chain_steps'::regclass
                      AND tgdeferrable) THEN
        RAISE EXCEPTION 'chain_step_grounding is not a deferrable constraint trigger any more';
    END IF;

    SELECT count(*), string_agg(rule || ' ' || obj || ': ' || detail, '; ')
      INTO n, d FROM check_report_projection();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-42 refuses to finish: % report form problem(s): %', n, d;
    END IF;

    -- The neighbouring check this file's re-created bundle could break. Its
    -- `approval_stale` arm is the one the header warns about, and in a database
    -- with no approval yet it has nothing to say -- so this asserts the other
    -- five arms rather than assuming them.
    SELECT count(*), string_agg(rule || ' ' || obj || ': ' || detail, '; ')
      INTO n, d FROM check_report_grounding();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-42 leaves % report grounding problem(s) behind it: %', n, d;
    END IF;
END $$;
