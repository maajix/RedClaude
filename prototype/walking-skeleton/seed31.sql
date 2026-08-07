-- Ticket 31 seed: the surface of ticket 05's fixture pair, expressed in the
-- ticket 06/33 corpus.
--
-- Nothing here is a shortcut around a decision. Every row goes through the same
-- session-helper contract the runtime uses (`app.actor_kind`), the scope
-- document is published before a single receipt can exist (ticket 26/33), and
-- the surface is the *real* fixture's surface: two identities, three endpoints,
-- one note that belongs to userB.
--
-- Two programs, because one of the nine proofs is that a ceiling stops a run:
--   t31-main     token_budget 200000  -- the skeleton
--   t31-exhaust  token_budget   5000  -- seeded to be exhausted, nothing else

SET client_min_messages = warning;
SELECT set_config('app.actor_kind', 'runtime', false);

INSERT INTO programs (id, slug, name, platform, token_budget) VALUES
    ('31111111-3111-7111-8111-111111111111','t31','Ticket 31 skeleton','hackerone', 200000),
    ('31222222-3222-7222-8222-222222222222','t31x','Ticket 31 budget floor','hackerone', 5000);

INSERT INTO program_scope_versions
       (program_id, version, policy, policy_sha256, default_tier, reason) VALUES
    ('31111111-3111-7111-8111-111111111111', 1,
     '{"targets":["127.0.0.1"],"note":"ticket 05 fixture pair on loopback"}'::jsonb,
     repeat('1',64), 'standard', 'ticket 31 walking skeleton'),
    ('31222222-3222-7222-8222-222222222222', 1,
     '{"targets":["127.0.0.1"]}'::jsonb, repeat('2',64), 'standard', 'ticket 31 budget floor');

-- MEASURED, and the reason `port` is filled in here: the first live run put
-- `http://127.0.0.1/api/notes/1` on the wire -- port 80 -- because the named
-- `scope` view this skeleton hands the agent projected host and no port, and
-- the agent had nothing else to go on. That was a defect in THIS prototype's
-- view, not in ticket 26: `applications.base_url` carries the port and the
-- `endpoints` view now joins it.
--
-- Port matching itself is correct and was measured to be so once a port was
-- present (see the note on `scope_port` below):
--   scope_class_of(..., 18831, ...) = target
--   scope_class_of(..., 80,    ...) = denied
--   scope_class_of(..., 22,    ...) = denied
-- The earlier reading (`port 80 classified target`) was taken while this
-- column was NULL, and NULL means "any port" by design. No divergence.
INSERT INTO program_scope_rules
       (program_id, version, ord, effect, effect_rank, pattern_kind,
        pattern_text, match_key, port, spec_kind, spec_len) VALUES
    ('31111111-3111-7111-8111-111111111111', 1, 1, 'target', 2, 'exact',
     '127.0.0.1','127.0.0.1', 18831, 2, length('127.0.0.1')),
    ('31222222-3222-7222-8222-222222222222', 1, 1, 'target', 2, 'exact',
     '127.0.0.1','127.0.0.1', 18831, 2, length('127.0.0.1'));

-- ---- surface: what ticket 05's fixture actually exposes --------------------
-- MEASURED, and the reason `scope_port` is filled in on every addressable
-- entity: `classify_entity` passes `coalesce(e.scope_port, 443)` into
-- `scope_class_of`, so an entity that does not carry a port is classified
-- against 443. With the rule above narrowed to 18831 every entity whose
-- `scope_port` was NULL flipped to `in_scope = false`, `rank_pass` abandoned
-- all four main tasks with `out_of_scope`, and the skeleton stopped dead at
-- P1. Recorded as D-26-ENTITY-PORT-443: a port-qualified scope rule silently
-- de-scopes every entity that recon inserted without a port, and recon has no
-- reason to set one.
INSERT INTO entities (id, program_id, type, label, dedup_key,
                      scope_selector_kind, scope_selector, scope_port) VALUES
 ('31aaaaaa-0000-7000-8000-000000000001','31111111-3111-7111-8111-111111111111','application','APP','http://127.0.0.1:18831/','host','127.0.0.1',18831),
 ('31aaaaaa-0000-7000-8000-000000000002','31111111-3111-7111-8111-111111111111','endpoint','EP_NOTE','GET /api/notes/{id}','host','127.0.0.1',18831),
 ('31aaaaaa-0000-7000-8000-000000000003','31111111-3111-7111-8111-111111111111','endpoint','EP_NOTES','GET /api/notes','host','127.0.0.1',18831),
 ('31aaaaaa-0000-7000-8000-000000000004','31111111-3111-7111-8111-111111111111','endpoint','EP_PROFILE','GET /api/profile','host','127.0.0.1',18831),
 ('31aaaaaa-0000-7000-8000-000000000005','31111111-3111-7111-8111-111111111111','identity','ID_A','identity:userA',NULL,NULL,NULL),
 ('31aaaaaa-0000-7000-8000-000000000006','31111111-3111-7111-8111-111111111111','identity','ID_B','identity:userB',NULL,NULL,NULL),
 ('31bbbbbb-0000-7000-8000-000000000001','31222222-3222-7222-8222-222222222222','application','XAPP','http://127.0.0.1:18831/','host','127.0.0.1',18831),
 ('31bbbbbb-0000-7000-8000-000000000002','31222222-3222-7222-8222-222222222222','endpoint','XEP','GET /api/notes/{id}','host','127.0.0.1',18831),
 ('31bbbbbb-0000-7000-8000-000000000005','31222222-3222-7222-8222-222222222222','identity','XID_A','identity:userA',NULL,NULL,NULL);

INSERT INTO applications (entity_id, base_url, kind) VALUES
 ('31aaaaaa-0000-7000-8000-000000000001','http://127.0.0.1:18831/','api'),
 ('31bbbbbb-0000-7000-8000-000000000001','http://127.0.0.1:18831/','api');

INSERT INTO endpoints (entity_id, application_id, method, path_template) VALUES
 ('31aaaaaa-0000-7000-8000-000000000002','31aaaaaa-0000-7000-8000-000000000001','GET','/api/notes/{id}'),
 ('31aaaaaa-0000-7000-8000-000000000003','31aaaaaa-0000-7000-8000-000000000001','GET','/api/notes'),
 ('31aaaaaa-0000-7000-8000-000000000004','31aaaaaa-0000-7000-8000-000000000001','GET','/api/profile'),
 ('31bbbbbb-0000-7000-8000-000000000002','31bbbbbb-0000-7000-8000-000000000001','GET','/api/notes/{id}');

-- `secret_ref` is a *reference*. The password itself lives in the proxy
-- process and is injected on the wire; nothing that an agent can read ever
-- holds it. That is the standing constraint, and this column is where it shows.
INSERT INTO identities (entity_id, slot_name, class, secret_ref) VALUES
 ('31aaaaaa-0000-7000-8000-000000000005','userA','user','op://BugBounty Dynamic/t31-userA/password'),
 ('31aaaaaa-0000-7000-8000-000000000006','userB','user','op://BugBounty Dynamic/t31-userB/password'),
 ('31bbbbbb-0000-7000-8000-000000000005','userA','user','op://BugBounty Dynamic/t31-userA/password');

-- ---- the hypothesis the skeleton is going to test --------------------------
INSERT INTO hypotheses (id, program_id, label, subject_entity_id,
                        identity_a_entity_id, identity_b_entity_id,
                        property_class, statement) VALUES
 ('31cccccc-0000-7000-8000-000000000001','31111111-3111-7111-8111-111111111111','H1',
  '31aaaaaa-0000-7000-8000-000000000002',
  '31aaaaaa-0000-7000-8000-000000000005','31aaaaaa-0000-7000-8000-000000000006',
  'authorization.object_ownership',
  'userA can read a note owned by userB through GET /api/notes/{id}'),
 ('31cccccc-0000-7000-8000-000000000002','31222222-3222-7222-8222-222222222222','XH1',
  '31bbbbbb-0000-7000-8000-000000000002',
  '31bbbbbb-0000-7000-8000-000000000005',NULL,
  'authorization.object_ownership',
  'the same claim, on a program whose budget cannot pay for the answer');

INSERT INTO hypothesis_transitions (program_id, hypothesis_id, from_status, to_status, actor_kind) VALUES
 ('31111111-3111-7111-8111-111111111111','31cccccc-0000-7000-8000-000000000001','proposed','testable','llm');
INSERT INTO hypothesis_transitions (program_id, hypothesis_id, from_status, to_status, actor_kind) VALUES
 ('31222222-3222-7222-8222-222222222222','31cccccc-0000-7000-8000-000000000002','proposed','testable','llm');

-- ---- tasks -----------------------------------------------------------------
-- Four on the main program, not one. A slate of one proves nothing about
-- ranking, and the ranking is the thing the replay proof re-derives.
INSERT INTO tasks (id, program_id, label, kind, subject_entity_id, hypothesis_id,
                   expected_information_gain, potential_impact, novelty,
                   estimated_cost, confidence_of_execution, created_at) VALUES
 ('31dddddd-0000-7000-8000-000000000001','31111111-3111-7111-8111-111111111111','T_HUNT','hunt',
  '31aaaaaa-0000-7000-8000-000000000002','31cccccc-0000-7000-8000-000000000001',
  0.90, 0.80, 1.00, 1.0, 0.90, '2026-08-07 10:00:00+00'),
 ('31dddddd-0000-7000-8000-000000000002','31111111-3111-7111-8111-111111111111','T_RECON','recon',
  '31aaaaaa-0000-7000-8000-000000000001',NULL,
  0.60, 0.20, 0.80, 1.0, 0.90, '2026-08-07 10:00:01+00'),
 ('31dddddd-0000-7000-8000-000000000003','31111111-3111-7111-8111-111111111111','T_RECON2','recon',
  '31aaaaaa-0000-7000-8000-000000000004',NULL,
  0.30, 0.10, 0.50, 2.0, 0.80, '2026-08-07 10:00:02+00'),
 -- Deliberately unrankable: no gain, no impact. `rank_pass` must leave its
 -- priority NULL and `rank_candidates` must not offer it.
 ('31dddddd-0000-7000-8000-000000000004','31111111-3111-7111-8111-111111111111','T_UNRANKED','recon',
  '31aaaaaa-0000-7000-8000-000000000003',NULL,
  NULL, NULL, 0.50, 1.0, 0.50, '2026-08-07 10:00:03+00'),
 -- MEASURED, and the reason these two costs differ: `rank_candidates` filters
 -- on `b.tokens_left >= t.estimated_cost * w.cost_reference_tokens`, and
 -- `scheduler_weights.cost_reference_tokens` is 200000. On a 5000-token
 -- program a task costing 1.0 reference-runs (200000 tokens) is unaffordable
 -- and never reaches a slate at all -- so a task seeded at 1.0 could not be
 -- claimed, and the per-run ceiling could never be reached to be tested.
 -- XT_HUNT is therefore seeded at 0.02 (4000 tokens, affordable), and XT_BIG at
 -- 1.0 exists to prove the other half: the unaffordable one is never offered.
 ('31eeeeee-0000-7000-8000-000000000001','31222222-3222-7222-8222-222222222222','XT_HUNT','hunt',
  '31bbbbbb-0000-7000-8000-000000000002','31cccccc-0000-7000-8000-000000000002',
  0.90, 0.80, 1.00, 0.02, 0.90, '2026-08-07 10:00:00+00'),
 ('31eeeeee-0000-7000-8000-000000000002','31222222-3222-7222-8222-222222222222','XT_BIG','recon',
  '31bbbbbb-0000-7000-8000-000000000001',NULL,
  0.90, 0.80, 1.00, 1.0, 0.90, '2026-08-07 10:00:01+00');

SELECT set_scope_version('31111111-3111-7111-8111-111111111111', 1);
SELECT set_scope_version('31222222-3222-7222-8222-222222222222', 1);
