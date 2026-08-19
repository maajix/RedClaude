-- Ticket 64: a chain report states the impact the chain actually reached.
--
-- Story 158 asks for "chain severity based on demonstrated end impact without
-- double-counting member impact". Ticket 42 built the chain report and left
-- this out: `chain_source_bundle` emits steps, edges, evidence and limitations
-- and no band at all, so the one number a triager reads first was the one thing
-- a chain report did not say. Ticket 42's own note that "`cvss_stale` and
-- `severity_unstated` are about a band no chain report prints" is the record of
-- the omission.
--
-- The band is read off the end of the chain and nowhere else. A chain's steps
-- each carry their own Finding severity, and the two aggregations somebody
-- reaches for first -- the maximum over all members, or the members added up --
-- are both the double count the story forbids: an information leak that
-- unlocked an account takeover is an account takeover, and reporting it as
-- "critical plus a low" claims the leak twice, once on its own report and once
-- inside this one. So the band is the end impact, the earlier steps are printed
-- as the route to it, and the report says in words that they were not added.
--
-- "The end" is structural rather than a depth: a step with no outgoing capability
-- edge is a step nothing was pivoted from, which is what it means to have gone
-- as far as this chain goes. Depth would be a guess -- two steps can sit at the
-- same depth -- and 040 already refuses the cyclic and disconnected shapes that
-- would make "no outgoing edge" mean something else. A chain that ends in more
-- than one place takes the highest of those ends, which is a choice among ends
-- and not a sum of them.
--
-- An ungraded end is said rather than banded. A Finding opens at `info` on basis
-- `undetermined` and stays there until somebody states a severity, so a chain
-- ending at one has no end impact yet -- and `info` printed as the band of a
-- composition that reached an account takeover would be the report understating
-- itself in exactly the way the story is about.

CREATE FUNCTION rk2_chain_severity(p_program uuid, p_chain uuid) RETURNS jsonb
LANGUAGE sql STABLE AS $fn$
    WITH member AS (
        SELECT s.label AS stamp, f.label AS member, f.severity, f.severity_basis,
               f.cvss_vector,
               NOT EXISTS (SELECT 1 FROM chain_edges e
                            WHERE e.chain_id = p_chain
                              AND e.from_stamp_id = cs.stamp_id) AS ends_here
          FROM chain_steps cs
          JOIN pivot_stamps s ON s.id = cs.stamp_id
          JOIN findings f ON f.id = s.finding_id
         WHERE cs.chain_id = p_chain AND cs.program_id = p_program
    )
    SELECT jsonb_build_object(
        -- One band, and the reason it is one band is in the header. `DESC` over
        -- the rank rather than over the word, because 'critical' < 'info' when
        -- text sorts itself.
        'band', (SELECT m.severity FROM member m
                  WHERE m.ends_here
                  ORDER BY rk2_severity_rank(m.severity) DESC, m.stamp
                  LIMIT 1),
        'basis', 'demonstrated_end_impact',
        -- Whether the end has a severity at all. A Finding sits at `info` on
        -- basis `undetermined` until somebody states one, so a chain that
        -- printed that as its band would be reporting "this composition is
        -- informational" when what is true is that nobody has graded where it
        -- ends yet.
        'graded', (SELECT coalesce(bool_and(m.severity_basis <> 'undetermined'), false)
                     FROM member m WHERE m.ends_here),
        'ends', (SELECT coalesce(jsonb_agg(jsonb_build_object(
                     'stamp', m.stamp, 'member', m.member, 'band', m.severity,
                     'basis', m.severity_basis, 'vector', m.cvss_vector,
                     'score', CASE WHEN m.cvss_vector IS NULL THEN NULL
                                   ELSE cvss31_base_score(m.cvss_vector) END)
                     ORDER BY m.stamp), '[]'::jsonb)
                  FROM member m WHERE m.ends_here),
        -- The route, stated so that a reader can see which bands were left out
        -- and check that they were. A rule nobody can audit is a rule nobody
        -- can tell was followed.
        'carried', (SELECT coalesce(jsonb_agg(jsonb_build_object(
                        'stamp', m.stamp, 'member', m.member, 'band', m.severity)
                        ORDER BY m.stamp), '[]'::jsonb)
                     FROM member m WHERE NOT m.ends_here));
$fn$;

COMMENT ON FUNCTION rk2_chain_severity(uuid, uuid) IS
  'Ticket 64, story 158: the band a chain demonstrated, taken from the steps nothing was pivoted from and from no other member. The members on the route are listed under `carried` so that a reader can see what was deliberately not added.';


-- The bundle gains one key. Re-created whole rather than patched, because the
-- body is one RETURN of one object and 042's argument for each part of it is in
-- the comment above the original.
CREATE OR REPLACE FUNCTION chain_source_bundle(p_chain uuid, p_template text)
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
        'severity', rk2_chain_severity(p, p_chain),
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
  'Ticket 42, extended by 64: everything a kill chain report may say, and the whole of it. An unsound chain answers with the reason and no steps, which is 040''s decision restated where the renderer reads it; a template that is not a chain form answers NULL. Since 64 it also carries the band the chain demonstrated at its end.';


-- The block, and the form it goes in. A chain report that computed a band and
-- printed it nowhere would be story 158 answered in the database and not to the
-- operator, and criterion 3's list is where "the complete form says this" is
-- written down.
INSERT INTO report_blocks (id, name, description, subjects) VALUES
 ('chain_severity','Severity',
  'the band the chain demonstrated at its end, the step it was demonstrated at, and the earlier steps'' own bands -- listed as the route rather than added to it.',
  ARRAY['chain']);

CREATE OR REPLACE FUNCTION rk2_report_required_blocks(p_subject text) RETURNS text[]
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
        -- nobody wrote about the composition. `chain_severity` is story 158's,
        -- and it is required for the reason `severity_block` is required of a
        -- Finding: a submission with no band is a submission a triager cannot
        -- rank.
        WHEN 'chain'   THEN ARRAY['scope_block','chain_header','chain_composition',
                                  'chain_transitions','chain_evidence',
                                  'chain_severity','limitations']
    END
$fn$;

-- Deleted and re-inserted whole for 042's reason: the ordinal is half the
-- primary key, so inserting in the middle would collide on the way past.
DELETE FROM report_template_blocks WHERE template_id = 'platform.chain_long_form';

INSERT INTO report_template_blocks (template_id, ordinal, block_id) VALUES
 ('platform.chain_long_form',1,'chain_header'),
 ('platform.chain_long_form',2,'scope_block'),
 ('platform.chain_long_form',3,'chain_composition'),
 ('platform.chain_long_form',4,'chain_transitions'),
 ('platform.chain_long_form',5,'chain_evidence'),
 ('platform.chain_long_form',6,'chain_severity'),
 ('platform.chain_long_form',7,'limitations');


DO $$
DECLARE n integer; d text;
BEGIN
    -- The block is registered and reachable from a form, which is 034's first
    -- grounding rule and the one an added block breaks by default.
    IF NOT EXISTS (SELECT 1 FROM report_template_blocks WHERE block_id = 'chain_severity') THEN
        RAISE EXCEPTION 'ph2-64 registered chain_severity and put it in no form';
    END IF;

    -- The band has to reach the renderer, and the renderer reads the bundle.
    IF (SELECT p.prosrc FROM pg_proc p
         WHERE p.pronamespace = 'public'::regnamespace
           AND p.proname = 'chain_source_bundle') NOT LIKE '%rk2_chain_severity%' THEN
        RAISE EXCEPTION 'chain_source_bundle does not carry the chain severity';
    END IF;

    SELECT count(*), string_agg(rule || ' ' || obj || ': ' || detail, '; ')
      INTO n, d FROM check_report_projection();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-64 refuses to finish: % report form problem(s): %', n, d;
    END IF;
END $$;
