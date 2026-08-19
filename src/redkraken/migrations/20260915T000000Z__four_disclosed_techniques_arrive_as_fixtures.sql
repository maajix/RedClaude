-- ---------------------------------------------------------------------------
-- 20260915T000000Z__four_disclosed_techniques_arrive_as_fixtures.sql
--                                                                   (ticket 79)
--
-- Ticket 79 reads publicly disclosed work and asks what of it this corpus
-- cannot grade. Sixteen techniques were read; twelve resolved without a file --
-- five already graded by a shipped fixture, three refused with a reason, four
-- filed as ungradeable because what a grade would measure here is the harness's
-- own containment rather than a target. The remaining four are these, and they
-- are the four Property classes that had a Playbook and no case to grade it
-- with:
--
--   `authentication.recovery_flow`              recovery-flow-pair
--   `information_disclosure.identifier_oracle`  identifier-oracle-pair
--   `rate_limiting.per_origin`                  per-origin-limit-pair
--   `rate_limiting.resource_cost`               resource-cost-pair
--
-- After this the corpus covers every declared class except the four the
-- transport register already settles: 025 records `request_framing` and
-- `datagram_transport` as `unmakeable` and `tls_configuration` and
-- `certificate_trust` as `probe_only`, each because the reading would land on
-- the proxy, the run CA or a protocol the door does not forward. The intake
-- ledger files those four with the same reasons the register gives, so the two
-- agree by construction rather than by anybody remembering to keep them level:
-- `tools/check_intake` refuses a row that claims a fixture for a class this
-- schema says is not agent-makeable.
--
-- Nothing here is a Playbook. The binding between a Playbook and the fixtures
-- that grade it is total and derived (050), so four new fixtures widen what
-- every Playbook is graded against without any Playbook naming one, which is
-- the direction that keeps a Playbook from choosing its own examination. Four
-- Playbooks that could previously only be graded on out-of-class negatives now
-- have an in-class case, and their evaluations will say so or fail.
--
-- The provenance is in each fixture document and the row that produced it is in
-- `baseline/technique-intake.tsv`: a source read on a stated date, the digest of
-- what was read, the class it maps to, and a restatement of the shape in this
-- repository's own words. No report prose, no screenshots and no payload dumps
-- entered the tree, and nothing under `src/` gained a way to fetch a writeup --
-- retrieval was a maintainer act whose only result is these files.
--
-- A new file rather than an edit to an earlier one: a recorded migration whose
-- file has changed is schema drift and `rk db migrate` refuses the whole corpus
-- for it.
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- 1. The four fixtures, as rows
-- ===========================================================================

-- Both digests, for the reason 050 gives: `source_sha256` is what was served
-- and `ground_truth_sha256` is how it was graded, and they move separately. An
-- edit to either without an edit to a migration is drift, and the catalogue
-- test in `tests/test_database.py` is what catches it.
INSERT INTO fixtures (id, kind, path, source_sha256, ground_truth_sha256) VALUES
 ('identifier-oracle-pair', 'own_pair',
  'fixtures/identifier-oracle-pair/fixture.md',
  '3bf80a80f61af4e7e76a55274d1582036a06eeac32a02c839eaa15d5df4ab855',
  '0bd3c61d5bc52fb73b832272dd1be645150bc21cd656e2eae3ade3c8349803d7'),
 ('per-origin-limit-pair', 'own_pair',
  'fixtures/per-origin-limit-pair/fixture.md',
  '95e4ee63ae8403da5bf72e7a650fd29a61cdf3ee070f81a713409cfe9c5c9f70',
  'fafe9ae076cc546dd56d4db7ad74438e6659071f39a216e8ce04a218c18f12c8'),
 ('recovery-flow-pair', 'own_pair',
  'fixtures/recovery-flow-pair/fixture.md',
  '742ced004434665bfc5c785d49aceb7a715baecebdb9f7a36440904ea4ecf618',
  'c829ac113c3ab2037085cd33262d22bb3cf72c9f28952515219631c55e1897e1'),
 ('resource-cost-pair', 'own_pair',
  'fixtures/resource-cost-pair/fixture.md',
  'b4e8faa6c6b6bb3d8008a9dca98f98c677d739e9150d99b3fd316919d2aa99ad',
  'fb398fbfb491b636c890a50326875325e3526bddb3e8c53e56adf07452492fc1')
ON CONFLICT (id) DO UPDATE SET
    kind                = excluded.kind,
    path                = excluded.path,
    source_sha256       = excluded.source_sha256,
    ground_truth_sha256 = excluded.ground_truth_sha256;


-- ===========================================================================
-- 2. One class each
-- ===========================================================================

-- One, for 050's reason: a fixture claiming two classes cannot say which of
-- them a Playbook that fired on it read. Each of these four was written from a
-- disclosure describing one shape, and the fixture document argues in its own
-- words why the neighbouring classes are not merely absent from its ground
-- truth but could not be true of what it serves.
INSERT INTO fixture_classes (fixture_id, property_class) VALUES
 ('identifier-oracle-pair', 'information_disclosure.identifier_oracle'),
 ('per-origin-limit-pair', 'rate_limiting.per_origin'),
 ('recovery-flow-pair', 'authentication.recovery_flow'),
 ('resource-cost-pair', 'rate_limiting.resource_cost')
ON CONFLICT (fixture_id, property_class) DO NOTHING;
