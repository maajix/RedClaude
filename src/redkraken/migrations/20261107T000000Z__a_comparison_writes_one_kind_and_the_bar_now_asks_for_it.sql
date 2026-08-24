-- ---------------------------------------------------------------------------
-- 20261107T000000Z__a_comparison_writes_one_kind_and_the_bar_now_asks_for_it.sql
--                                          (ticket 166, for five Playbooks)
--
-- 20261106T000000Z narrowed the five graded Playbooks to the two kinds a verb
-- writes and still got the rows wrong. This corrects them. The correction is
-- the second half of the same reading, and it is the half `tests.test_vertical`
-- found:
--
--     playbook playbooks/object-ownership/playbook.md requires 1 x
--     (role=control, kind=response_invariant) for supported, found 0
--
-- What was missed. `close_test_replay` derives the kind of an action's
-- Observation from whether ANY `status_differs` or `body_differs` assertion
-- names that action -- and it matches the assertion's `action` AND its
-- `against`, so a comparison marks BOTH of its legs. A control leg that a
-- differential is measured against is therefore `response_differential` too.
-- `response_invariant` is only ever written for an action no comparison names.
--
-- What follows from it. The kind is a property of the Test specification, not
-- of the outcome, so one specification produces the same kinds whether its
-- assertions hold or fail. A Playbook that asks for `response_differential` on
-- the variant for `supported` and `response_invariant` on the same variant for
-- `refuted` is therefore asking one specification to write two kinds for one
-- action, and exactly one of its two outcomes can ever be reached. That is the
-- shape the corpus repeated. Here it is replaced, for these five only, by the
-- shape `client-side-path-traversal` and `web-cache` already ship: every row
-- names `response_differential`, which is the one kind a Playbook whose whole
-- method is a comparison can actually produce.
--
-- What this still refuses. Both `supported` rows remain, in two roles, so none
-- of the five can claim from a single reading -- the rule the control row
-- exists for. What it no longer says is which reading the control was: ticket
-- 166 owns teaching `close_test_replay` to class a control leg, and owns the
-- other twenty-five Playbooks that carry the contradictory pair.
--
-- The five digests move again because `bb:evidence` is in the document
-- `playbooks.source_sha256` is a digest of, so 20261106T000000Z's five pairs
-- are superseded here. Last write wins in apply order, which is the shape
-- `tools/check_coverage.py` reads.
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

    INSERT INTO playbook_evidence
            (playbook_id, to_status, role, observation_kind, polarity, min_count)
    SELECT p.id, v.to_status, v.role, v.kind, v.polarity, v.min_count
      FROM playbooks p, (VALUES
            ('refuted',   'variant', 'response_differential', 'refutes',  1),
            ('supported', 'control', 'response_differential', 'supports', 1),
            ('supported', 'variant', 'response_differential', 'supports', 1))
            AS v(to_status, role, kind, polarity, min_count)
     WHERE p.path IN ('playbooks/attack-surface/playbook.md',
                      'playbooks/object-ownership/playbook.md',
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
       AND e.observation_kind <> 'response_differential';
    IF n <> 0 THEN
        RAISE EXCEPTION 'ticket 166: % bar row(s) still name a kind the comparison does not write', n;
    END IF;

    UPDATE playbooks p
       SET source_sha256 = v.source_sha256,
           version       = v.version
      FROM (VALUES
            ('playbooks/attack-surface/playbook.md',
             'db45360a47fa2aa22fb291664a94fadd9ec195eec3c6cb1414411e96498e819b',
             '91bb8210e0fd515aa69c9b6d75e46ccbda185ef6ff8960dc5b2b0897cb4f491a'),
            ('playbooks/object-ownership/playbook.md',
             'c4fb1ec47b89e431a65a796e28b367a43705d8a9e2b3304e1d067ba95ae261bb',
             'c8c808bc2dc083ec637ec7a2b90005072cf5e8db6ca8850229ad48d47bed99d5'),
            ('playbooks/browser-script/playbook.md',
             '3f4982af4dcf34a8875ae1912410da4888615f6bd2e467ee4a45d06af97ea2e0',
             '0dd9f3ece33a4ec11a831b7ee3644ca8b777c528a42151caebe15de92014b2e8'),
            ('playbooks/cookies/playbook.md',
             '2f4b70f1795d18d63f74617bc516282210938de2c792bcac7e23609a7c64820e',
             'fbdeeeffc6e3b6a5006bc16865334f5ead6a34823ba9882b6ff99bdd77eda750'),
            ('playbooks/payment-workflows/playbook.md',
             'ff2341884cfdf4ca0f3358d67fbb739a8c0503a3e6993ea90e130c440e3f9648',
             '494358c628fd4077226815d8419a471a1d22e0600361418d287b15f73094dbb3')
           ) AS v(path, source_sha256, version)
     WHERE p.path = v.path;

    GET DIAGNOSTICS n = ROW_COUNT;
    IF n <> 5 THEN
        RAISE EXCEPTION 'ticket 166: re-froze % Playbook row(s) and meant five', n;
    END IF;
END $$;
