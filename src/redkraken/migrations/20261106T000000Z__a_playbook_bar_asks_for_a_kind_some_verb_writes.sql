-- ---------------------------------------------------------------------------
-- 20261106T000000Z__a_playbook_bar_asks_for_a_kind_some_verb_writes.sql
--                                          (ticket 166, for five Playbooks)
--
-- Ticket 166 measured the wall and named two ways through it. This takes the
-- second one -- narrow the corpus rows to kinds a verb can reach -- and takes
-- it for the five Playbooks Arbeitsblock 3 grades and for no others. The first
-- way, teaching `close_test_replay` to class a control leg, is still open and
-- still ticket 166's.
--
-- What the wall is. `enforce_playbook_evidence()` fires BEFORE INSERT ON
-- `hypothesis_transitions` and raises on the first row `playbook_evidence_unmet()`
-- returns, comparing `observations.kind` against `playbook_evidence.observation_kind`
-- for the selected Playbook. The only kinds any writer produces on a claim are
-- `response_invariant` and `response_differential`: `close_test_replay` derives
-- one or the other from whether the assertions naming the action differ, and it
-- writes the Observation and the `hypothesis_evidence` edge in the same loop.
-- `rk2_promote_hypotheses` is the only other writer of that edge and refuses one
-- once the claim is past `proposed`, which it is by the time a Test is running.
-- So a bar naming any other kind is a bar no run can clear.
--
-- All five of these named one. `attack-surface` wanted `content_match` on the
-- variant, `object-ownership` `credential_effect` on the control,
-- `browser-script` `reflected_input` on both its variant rows, `cookies`
-- `header_policy_observed` on the control and `credential_effect` on the
-- variant, and `payment-workflows` `state_change` on both. Every one of those
-- readings is the right reading and none of them is reachable, so what the bars
-- did was make the Playbook unsatisfiable rather than strict.
--
-- What is lost, said plainly. A control row that named `credential_effect` said
-- "the second session was working"; a control row naming `response_invariant`
-- says "the control leg of the Test did not differ". The second is weaker and
-- it is what the instrument actually records. The `control` role itself is
-- untouched -- every one of the five still cannot claim from a single reading,
-- which is the rule the corpus exists for -- and the bodies still instruct the
-- reading the old kind described. Ticket 166 owns putting the distinction back.
--
-- The five source digests move again because `bb:evidence` is in the document
-- `playbooks.source_sha256` is a digest of, so `20261105T000000Z`'s four pairs
-- are superseded here and `object-ownership` joins them. Last write wins in
-- apply order, which is the shape `tools/check_coverage.py` reads.
-- ---------------------------------------------------------------------------

DO $$
DECLARE n integer;
BEGIN
    DELETE FROM playbook_evidence e
     USING playbooks p
     WHERE e.playbook_id = p.id
       AND p.path IN ('playbooks/attack-surface/playbook.md',
                      'playbooks/object-ownership/playbook.md',
                      'playbooks/browser-script/playbook.md',
                      'playbooks/cookies/playbook.md',
                      'playbooks/payment-workflows/playbook.md');
    GET DIAGNOSTICS n = ROW_COUNT;
    IF n <> 15 THEN
        RAISE EXCEPTION 'ticket 166: removed % evidence row(s) and meant fifteen', n;
    END IF;

    -- `attack-surface` keeps a differing control: its control is the answer to a
    -- path nobody deployed, and the claim is that the candidate did not answer
    -- like it. The other four take the shape the thirteen satisfiable Playbooks
    -- already have.
    INSERT INTO playbook_evidence
            (playbook_id, to_status, role, observation_kind, polarity, min_count)
    SELECT p.id, v.to_status, v.role, v.kind, v.polarity, v.min_count
      FROM playbooks p, (VALUES
            ('refuted',   'variant', 'response_invariant',    'refutes',  1),
            ('supported', 'control', 'response_differential', 'supports', 1),
            ('supported', 'variant', 'response_differential', 'supports', 1))
            AS v(to_status, role, kind, polarity, min_count)
     WHERE p.path = 'playbooks/attack-surface/playbook.md';

    INSERT INTO playbook_evidence
            (playbook_id, to_status, role, observation_kind, polarity, min_count)
    SELECT p.id, v.to_status, v.role, v.kind, v.polarity, v.min_count
      FROM playbooks p, (VALUES
            ('refuted',   'variant', 'response_invariant',    'refutes',  1),
            ('supported', 'control', 'response_invariant',    'supports', 1),
            ('supported', 'variant', 'response_differential', 'supports', 1))
            AS v(to_status, role, kind, polarity, min_count)
     WHERE p.path IN ('playbooks/object-ownership/playbook.md',
                      'playbooks/browser-script/playbook.md',
                      'playbooks/cookies/playbook.md',
                      'playbooks/payment-workflows/playbook.md');

    SELECT count(*) INTO n
      FROM playbook_evidence e
      JOIN playbooks p ON p.id = e.playbook_id
     WHERE p.path IN ('playbooks/attack-surface/playbook.md',
                      'playbooks/object-ownership/playbook.md',
                      'playbooks/browser-script/playbook.md',
                      'playbooks/cookies/playbook.md',
                      'playbooks/payment-workflows/playbook.md')
       AND e.observation_kind NOT IN ('response_invariant', 'response_differential');
    IF n <> 0 THEN
        RAISE EXCEPTION 'ticket 166: % bar row(s) still name a kind no verb writes', n;
    END IF;

    UPDATE playbooks p
       SET source_sha256 = v.source_sha256,
           version       = v.version
      FROM (VALUES
            ('playbooks/attack-surface/playbook.md',
             'f8c3999ac719079bdcc0362217ef65613b8ecf4dd19f29ed93281408d642832a',
             '9d76820022e8be2d78aa384a324e2a97f82733feace4cb19832b724b16e4212b'),
            ('playbooks/object-ownership/playbook.md',
             'de2e7b18b6512d85ffc3bd6610ef6643db1a99648c5b8a64a378f171b83d96c0',
             'ec4116fd5aad60bc22f420464dc17854d7a937011250907ea0acd6745268d641'),
            ('playbooks/browser-script/playbook.md',
             '02aadf4a0c896946f406bdaf59b3a37698acf74037c2a64e32153d3ad003aabb',
             'db411905ce198601ce75c9299f1dabdcbdcc57418fcc8525097823e7ce609731'),
            ('playbooks/cookies/playbook.md',
             '17d1dd7334621befaf33480252d76bada195475f2210911d3e624f826b473ca9',
             'dbabd3818e56a7ce8e1a72248b3ce12e5516dc71e08bf0a59d0fd038d8af22c4'),
            ('playbooks/payment-workflows/playbook.md',
             '8a4cf56e7d9f7fd49c65fe21f8cc30ec6c0b02d5848b56718a7815bb39560f00',
             '22fc05c73ed39670c407772a21ae6dc0d62bf98d9ba2656d9b802fcfd984f347')
           ) AS v(path, source_sha256, version)
     WHERE p.path = v.path;

    GET DIAGNOSTICS n = ROW_COUNT;
    IF n <> 5 THEN
        RAISE EXCEPTION 'ticket 166: re-froze % Playbook row(s) and meant five', n;
    END IF;
END $$;
