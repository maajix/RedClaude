-- ===========================================================================
-- Production harness 43 -- an evidence bundle leaves with what can be checked
-- ===========================================================================
-- This file is the half of 043 that belongs in the schema. The other halves are
-- `src/redkraken/evidence.py`, which packs a bundle, and
-- `src/redkraken/verifier.py`, which checks one and imports nothing -- not even
-- from this package -- so that the copy shipped inside a bundle runs on a
-- machine that has this repository, this database and this key material nowhere.
--
-- What a bundle is for. 042 renders a document. A document is a claim, and a
-- triager on the other side of it has no way to tell a rendered claim from a
-- typed one. The bundle is the difference: the same document, plus the rows it
-- was projected from, plus the bytes those rows name, plus a hash of each so
-- that every one of them can be held against the others by somebody who cannot
-- reach this harness at all.
--
-- The six criteria, and where each is met:
--
--   1. report, replay specification, assertion outcomes, Receipt metadata,
--      redacted Agent-view Artifacts and content hashes
--      -- `evidence_bundle_files` registers the files a bundle of each subject
--      carries, `evidence_artifacts` names the bytes, and the manifest carries a
--      hash of every file including the artifacts.
--   2. wire credentials, capabilities, cookies, secret headers, runtime keys
--      and unrelated Program material excluded by default
--      -- `evidence_artifacts` selects `agent_visible` and unencrypted rows and
--      nothing else, every read here is bound by `rk2_program_required()`, and
--      `evidence_exclusions` counts what was left behind rather than leaving the
--      absence to be inferred.
--   3. a standalone verifier, no database
--      -- `verifier.py`, and section 2 requires it to be one of the files a
--      bundle carries so that a bundle cannot ship without the thing that checks
--      it.
--   4. export rechecks soundness and refuses stale, invalidated or gated
--      material
--      -- nothing new: the export reads through 042's `read_finding_report` and
--      `read_chain_report` and renders through 042's renderer, which is where
--      `report_blockers` and `rk2_chain_unsoundness` already decide. What this
--      file adds is the staleness question 042 had no reason to ask -- see the
--      note on `evidence_stale_rendering` in section 4.
--   5. repeated export from identical rows is deterministic apart from
--      packaging metadata
--      -- every read here is ordered, and the manifest's own digest is taken
--      over everything in it except the one object that holds the wall clock.
--      034's argument for leaving `blockers` out of the source digest, applied
--      to the pair of facts that cannot be a property of the rows.
--   6. synthetic credential markers absent, secret scanning passes
--      -- `redaction_rules` gets the two columns that make it checkable: a probe
--      the pattern must match and a counter-probe it must not. A rule that
--      matches nothing is a redaction that fails open, and 024 already said in
--      writing that a redaction failing open is worse than none. A rule that
--      matches everything is a redaction that fails closed, which sounds safe
--      and is not: the scan runs over the whole bundle, and a pattern that
--      claims a timestamp or a hash refuses every export until somebody turns
--      the rule off.
-- ===========================================================================


-- ---------------------------------------------------------------------------
-- 1. A redaction rule carries its own witness
-- ---------------------------------------------------------------------------
-- 034 wrote six patterns and no reader. This ticket is the reader, and it
-- applies them in Python, over the bytes, because the bytes are in the process
-- and not in the database. That split is the hazard: the pattern is stored as a
-- POSIX regular expression and applied by a different engine, and the failure
-- mode is silent -- a pattern that stops matching redacts nothing and produces
-- a bundle that looks exactly like a clean one.
--
-- The probe is what makes that answerable from both sides. `check_evidence_-
-- export` asserts `probe ~ pattern` in POSIX; `tests/test_evidence.py` asserts
-- the same pair under `re`. Two engines agreeing on one string is a check; one
-- engine is a hope.
--
-- The counter-probe answers the other direction, which a probe cannot. A probe
-- only witnesses that a rule still fires. `[0-9 ().-]+` fires on everything and
-- would pass every probe in this table, and a rule that claims everything is not
-- a safe rule: the rescan runs over the whole bundle, so a pattern that claims a
-- timestamp refuses every export until somebody turns the rule off -- and a rule
-- turned off during an incident is a redaction that was never there.
--
-- Both are synthetic and are meant to be. Anything real here would put a
-- credential in a migration, which is the thing this whole file exists to stop.

ALTER TABLE redaction_rules ADD COLUMN probe text;
ALTER TABLE redaction_rules ADD COLUMN counter_probe text;

UPDATE redaction_rules SET probe = v.probe, counter_probe = v.counter_probe
  FROM (VALUES
    ('email',       'alice@example.com',
                    'app.example.com/api/orders'),
    ('phone',       '+1 (555) 123-4567',
                    '2026-08-16T09:15:33Z'),
    ('bearer',      'Bearer AbCdEf0123456789xyz',
                    'bearer token withheld'),
    ('jwt',         'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTYifQ.c2lnbmF0dXJlX2hlcmU',
                    'eyJub3QtYS1qd3Qi.only-two-parts'),
    ('card',        '4111 1111 1111 1111',
                    '9f8e1234567890123456ab1234567890123456cd1234567890123456ef123456'),
    ('national_id', '123-45-6789',
                    '2026-08-16')
  ) AS v(id, probe, counter_probe)
 WHERE redaction_rules.id = v.id;

-- What the two columns found on their first run, and the reason both exist.
--
-- `\b`, first. 034 wrote `card` and `national_id` with `\b` for a word boundary.
-- That is what `\b` means to Python's `re`, and it is not what it means to a
-- POSIX ARE: there `\b` is the backspace character, U+0008. Both patterns
-- therefore matched a payment card number in the exporter and matched nothing at
-- all in the database -- and nothing in this tree read them from SQL until now,
-- so nothing objected. Left alone, `check_evidence_export` would have reported
-- those two rules as broken forever while they worked, which is a check that
-- trains an operator to ignore it.
--
-- Then the counter-probes, which are the more expensive find. A bundle is mostly
-- ISO timestamps and SHA-256 hashes, and 034's `phone` claimed both: `2026-08-16`
-- is nine digits and separators, and about two hashes in five carry a digit run
-- long enough. `card` claimed roughly one hash in fifty. The exporter redacts
-- packaged artifact bytes only, but the verifier rescans every packed file, so
-- what those two rules actually did was refuse a randomly chosen 40% of exports
-- with `redaction_incomplete` pointing at a hash. This was not theory; it is what
-- the first end-to-end export in this ticket did.
--
-- All three rewrites say the constraint both engines spell the same way. A
-- lookaround asserts without consuming, which matters here as much as the
-- portability does: `(^|[^0-9])` would eat the character before the number and
-- the marker would stand where a digit's neighbour used to be. The class is
-- `[0-9A-Za-z]` and not `[0-9]` because a hash is digits sitting against letters;
-- refusing to start mid-token is what keeps hex out. `phone` additionally counts
-- digits rather than characters -- ten digits, not ten of anything -- so a date's
-- eight cannot reach the threshold on the strength of its dashes.
UPDATE redaction_rules SET pattern = v.pattern
  FROM (VALUES
    ('phone',       '(?<![0-9A-Za-z])\+?[0-9](?:[0-9 ().-]*[0-9]){9,}(?![0-9A-Za-z])'),
    ('card',        '(?<![0-9A-Za-z])(?:[0-9]{4}[ -]?){3}[0-9]{4}(?![0-9A-Za-z])'),
    ('national_id', '(?<![0-9A-Za-z])[0-9]{3}-[0-9]{2}-[0-9]{4}(?![0-9A-Za-z])')
  ) AS v(id, pattern)
 WHERE redaction_rules.id = v.id;

-- The identifier travels into every bundle, inside the marker that stands where
-- a match was removed. `verifier.MARKER` is the grammar of that marker and it
-- admits `[a-z_]+`; a rule identifier outside that would produce markers the
-- verifier cannot recognise, and an unrecognised marker is read by the rescan as
-- exactly the thing it was put there to remove.
ALTER TABLE redaction_rules
    ALTER COLUMN probe SET NOT NULL,
    ALTER COLUMN counter_probe SET NOT NULL,
    ADD CONSTRAINT redaction_rules_probe_present CHECK (probe <> ''),
    ADD CONSTRAINT redaction_rules_counter_probe_present CHECK (counter_probe <> ''),
    ADD CONSTRAINT redaction_rules_id_marker_safe CHECK (id ~ '^[a-z_]+$');

COMMENT ON COLUMN redaction_rules.probe IS
    'A synthetic string this rule''s pattern must match. Ticket 43: the pattern is stored here and applied by `re` in the exporter, so the one thing that must not drift is checked from both engines against one string.';

COMMENT ON COLUMN redaction_rules.counter_probe IS
    'A synthetic string this rule''s pattern must not match, holding the false positive that would otherwise bite: a timestamp for `phone`, a hash for `card`. Ticket 43: the rescan reads every packed file, so a rule that over-matches refuses exports rather than leaking, and gets switched off.';


-- ---------------------------------------------------------------------------
-- 2. What a complete bundle carries
-- ---------------------------------------------------------------------------
-- The registry, on 034's argument for `report_blocks`: the shape of what leaves
-- this harness is a property of the harness, stated once, rather than a tuple in
-- a Python module that a check would have to be told about separately.
--
-- Not `required boolean`. Every row here is a file the bundle carries; a file
-- that may be absent is a file the manifest would have to describe as optional,
-- and a verifier that accepts an optional absence cannot tell an incomplete
-- bundle from a complete one. What differs between the two subjects is which
-- rows exist, and that is the whole of the difference -- a chain has no single
-- validating Test run, so there is no assertion outcome for a chain bundle to
-- carry, and inventing an empty file for it would be a bundle claiming to
-- answer a question nobody can ask of a chain.
--
-- `spec.json` is on both sides and was not at first. A chain has no one
-- specification, but it has one per step, and 042's chain report prints the
-- digest of each -- so a chain bundle without them carried the identity of a
-- document it did not ship. `evidence.py` writes the files this table names and
-- decides nothing on its own, so a subject gains a file by gaining a row here.

CREATE TABLE evidence_bundle_files (
    subject text NOT NULL CHECK (subject IN ('finding', 'chain')),
    path    text NOT NULL CHECK (path ~ '^[a-z0-9_.]+$'),
    purpose text NOT NULL,
    PRIMARY KEY (subject, path)
);

COMMENT ON TABLE evidence_bundle_files IS
    'Ticket 43 criterion 1: the files a bundle of each subject carries. The manifest is not among them -- it is the index, and a document cannot index itself -- and `artifacts/` is not, because which artifacts exist is a fact about one Finding rather than about the form.';

INSERT INTO evidence_bundle_files (subject, path, purpose) VALUES
 ('finding', 'report.md',
  '042''s document, byte for byte: the thing a human reads and a Program is sent'),
 ('finding', 'source.json',
  'the projection the document was rendered from, so a reader can re-derive every sentence in it rather than believe it'),
 ('finding', 'spec.json',
  'criterion 1''s replay specification: the validating Test''s own actions, with the digest that is its identity'),
 ('finding', 'assertions.json',
  'criterion 1''s assertion outcomes: what the validating run answered, which is the half a specification cannot carry'),
 ('finding', 'receipts.json',
  'criterion 1''s Receipt metadata: method, path, status and arrival for every exchange the Finding cites'),
 ('finding', 'artifacts.json',
  'criterion 1''s content hashes: for each packaged artifact, the hash of the Agent view and the hash of what this bundle carries after redaction'),
 ('finding', 'verify.py',
  'criterion 3''s verifier, shipped inside what it verifies so that a recipient needs this repository for nothing'),
 ('chain', 'report.md',
  '042''s chain document, byte for byte'),
 ('chain', 'source.json',
  'the projection the document was rendered from'),
 ('chain', 'spec.json',
  'criterion 1''s replay specification, one per step: the specification behind each transition, so that the digest 042 prints against a step is the digest of something the bundle carries'),
 ('chain', 'receipts.json',
  'the transition Receipt of every step, which is what a chain cites in place of one validating run'),
 ('chain', 'artifacts.json',
  'the same content hashes, over the artifacts those transitions name'),
 ('chain', 'verify.py',
  'criterion 3''s verifier');

-- The files no bundle may be without, whichever subject it is about. Stated as
-- a function rather than as a literal inside the check, on 042's argument for
-- `rk2_report_required_blocks`: a criterion written into a check is a criterion
-- that stops being checked the day somebody edits the check.
CREATE FUNCTION rk2_evidence_required_files() RETURNS text[]
LANGUAGE sql IMMUTABLE AS $fn$
    -- The document, what it was projected from, what would have to be re-run to
    -- get it again, the exchanges behind it, the hashes of the bytes, and the
    -- thing that checks all five. `assertions.json` is not here because a chain
    -- has no single validating run to have answered anything, and this list is
    -- what every subject owes.
    SELECT ARRAY['report.md', 'source.json', 'spec.json', 'receipts.json',
                 'artifacts.json', 'verify.py']
$fn$;

COMMENT ON FUNCTION rk2_evidence_required_files() IS
    'Ticket 43: the files a bundle of any subject carries. In one place so that the registry and the check cannot disagree.';


-- ---------------------------------------------------------------------------
-- 3. Which exchanges a bundle is about
-- ---------------------------------------------------------------------------
-- Two readers, because a Finding and a chain gather their Receipts differently,
-- and then one function for each thing done with them. The alternative -- a
-- `finding_...` and a `chain_...` of everything below -- would be the same two
-- queries written four times, and the pair that drifts first is always the pair
-- that decides what may leave.

CREATE FUNCTION finding_evidence_receipts(p_finding uuid) RETURNS uuid[]
LANGUAGE sql STABLE AS $fn$
    SELECT coalesce(array_agg(DISTINCT fcr.receipt_id), '{}'::uuid[])
      FROM finding_cited_receipts fcr
     WHERE fcr.finding_id = p_finding
       AND fcr.program_id = rk2_program_required();
$fn$;

COMMENT ON FUNCTION finding_evidence_receipts(uuid) IS
    'Ticket 43: every Receipt one Finding of the bound Program cites, once. 034''s view already unions the three ways a Finding reaches one; this adds the Program and the deduplication.';

CREATE FUNCTION chain_evidence_receipts(p_chain uuid) RETURNS uuid[]
LANGUAGE sql STABLE AS $fn$
    SELECT coalesce(array_agg(DISTINCT s.transition_receipt_id), '{}'::uuid[])
      FROM chain_steps cs
      JOIN pivot_stamps s ON s.id = cs.stamp_id
      JOIN chains c ON c.id = cs.chain_id
     WHERE cs.chain_id = p_chain
       AND c.program_id = rk2_program_required();
$fn$;

COMMENT ON FUNCTION chain_evidence_receipts(uuid) IS
    'Ticket 43: the transition Receipt of every step of one chain of the bound Program. A chain cites the exchange that showed each pivot; the members'' own cited Receipts belong to the members'' own bundles.';

-- Criterion 1's replay specification, for both subjects and in one shape.
--
-- A Finding has one, and the source bundle already carries it -- but reading it
-- from there and the chain's from here would make `spec.json` two documents
-- under one name, and a recipient would have to know which subject a bundle is
-- about before knowing how to read a file of it.
--
-- A chain has one per step and no single validating run, which is what 042
-- already says by printing `specification sha256` against each transition and
-- nothing else. That line is a digest of something the bundle did not carry: a
-- recipient could read the number and had nothing to hold it against. These two
-- are what make it checkable.
CREATE FUNCTION finding_evidence_specifications(p_finding uuid)
RETURNS TABLE (label text, sha256 text, spec jsonb)
LANGUAGE sql STABLE AS $fn$
    SELECT t.label, t.spec_sha256, t.spec
      FROM findings f
      JOIN test_runs tr ON tr.id = f.validated_by_test_run_id
      JOIN tests t ON t.id = tr.test_id
     WHERE f.id = p_finding
       AND f.program_id = rk2_program_required();
$fn$;

COMMENT ON FUNCTION finding_evidence_specifications(uuid) IS
    'Ticket 43 criterion 1: the specification the run that validated this Finding replayed. No rows when nothing has validated it, which is a Finding 042 refuses to render in the first place.';

CREATE FUNCTION chain_evidence_specifications(p_chain uuid)
RETURNS TABLE (label text, sha256 text, spec jsonb)
LANGUAGE sql STABLE AS $fn$
    SELECT t.label, t.spec_sha256, t.spec
      FROM chain_steps cs
      JOIN chains c ON c.id = cs.chain_id
      JOIN pivot_stamps s ON s.id = cs.stamp_id
      JOIN test_runs tr ON tr.id = s.test_run_id
      JOIN tests t ON t.id = tr.test_id
     WHERE cs.chain_id = p_chain
       AND c.program_id = rk2_program_required()
     ORDER BY t.label;
$fn$;

COMMENT ON FUNCTION chain_evidence_specifications(uuid) IS
    'Ticket 43 criterion 1: the specification behind every step of one chain. 042''s chain report prints a specification digest per transition; without this the bundle would carry the digest of a document it did not ship.';

-- The bytes a bundle may carry, and the whole of what it may carry.
--
-- Criterion 2 is met by what this does not select rather than by anything the
-- exporter checks afterwards. `agent_visible` and `NOT encrypted` are the two
-- halves of one fact -- 005's CHECK makes every credential-bearing artifact
-- encrypted, so either alone would do, and both are written because a reader
-- asking "could a sealed wire artifact come out of here" should not have to go
-- and read a CHECK in another file to answer it.
--
-- `purged_at IS NULL` because a purged artifact is one somebody decided this
-- harness should no longer hold, and packing it into a document that leaves
-- would be the one place that decision could be undone.
CREATE FUNCTION evidence_artifacts(p_receipts uuid[])
RETURNS TABLE (receipt text, direction text, sha256 text,
               byte_size bigint, content_type text)
LANGUAGE sql STABLE AS $fn$
    SELECT r.label, v.direction, a.sha256, a.byte_size, a.content_type
      FROM receipts r
      CROSS JOIN LATERAL (VALUES ('request',  r.request_agent_sha),
                                 ('response', r.response_agent_sha)) AS v(direction, sha)
      JOIN artifacts a ON a.sha256 = v.sha
     WHERE r.id = ANY (p_receipts)
       AND r.program_id = rk2_program_required()
       AND a.visibility = 'agent_visible'
       AND NOT a.encrypted
       AND a.purged_at IS NULL
     ORDER BY r.label, v.direction;
$fn$;

COMMENT ON FUNCTION evidence_artifacts(uuid[]) IS
    'Ticket 43 criteria 1 and 2: the Agent-view bytes behind these Receipts, and nothing else. A sealed wire artifact cannot come out of here, because the visibility is in the WHERE and not in a rule the caller is trusted to apply.';

-- Receipt metadata, criterion 1's fourth item. The query string is deliberately
-- not here: 009 records `query_sha256` and never the query itself, and a bundle
-- that reconstructed one would be putting back exactly what that decision took
-- out.
CREATE FUNCTION evidence_receipts(p_receipts uuid[])
RETURNS TABLE (receipt text, lane text, decision text, method text,
               scheme text, host text, port integer, path text,
               query_sha256 text, status_code integer, arrival text,
               request_sha text, response_sha text)
LANGUAGE sql STABLE AS $fn$
    SELECT r.label, r.lane, r.decision, r.method,
           r.scheme, r.host, r.port, r.path,
           r.query_sha256, r.status_code,
           to_char(r.ts_arrival AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
           r.request_agent_sha, r.response_agent_sha
      FROM receipts r
     WHERE r.id = ANY (p_receipts)
       AND r.program_id = rk2_program_required()
     ORDER BY r.ts_arrival, r.label;
$fn$;

COMMENT ON FUNCTION evidence_receipts(uuid[]) IS
    'Ticket 43 criterion 1: what a triager needs to place each exchange -- lane, decision, method, authority, path, status and arrival -- with the query as its digest and never as its text.';

-- What was left behind, counted. An absence nobody states is an absence a
-- reader has to take on trust, and criterion 2's list is exactly the material a
-- reader would most want to know had been considered.
--
-- Only non-zero rows come out. A bundle that reported "0 wire artifacts
-- withheld" for a Finding whose exchanges carried no Identity would be filling
-- the section that matters with lines that mean nothing.
-- The last two arms are the ones `evidence_artifacts` makes necessary. That
-- function withholds an Agent-view artifact for two reasons of its own -- the
-- row is credential-bearing, or somebody purged it -- and 042's report prints
-- the hash of an artifact it can only cite by hash. Without these, a reader
-- comparing the document against `artifacts.json` finds a hash the index does
-- not carry and no sentence anywhere saying why.
--
-- One CTE and not the same predicate five times. The gathering functions were
-- written as a pair for exactly this reason: the copy that drifts first is
-- always the copy that decides what may leave, and a bundle whose exclusion
-- lines were computed over a different set of exchanges than its contents would
-- be a disclosure about a bundle nobody exported.
CREATE FUNCTION evidence_exclusions(p_receipts uuid[])
RETURNS TABLE (code text, detail text, items bigint)
LANGUAGE sql STABLE AS $fn$
    WITH cited AS (
        SELECT r.*
          FROM receipts r
         WHERE r.id = ANY (p_receipts)
           AND r.program_id = rk2_program_required()
    ),
    named AS (
        SELECT v.sha, v.view
          FROM cited r
          CROSS JOIN LATERAL (VALUES ('wire', r.request_wire_sha),
                                     ('wire', r.response_wire_sha),
                                     ('agent', r.request_agent_sha),
                                     ('agent', r.response_agent_sha)) AS v(view, sha)
         WHERE v.sha IS NOT NULL
    ),
    held AS (
        SELECT DISTINCT n.view, a.sha256, a.visibility, a.encrypted, a.purged_at
          FROM named n JOIN artifacts a ON a.sha256 = n.sha
    )
    SELECT 'wire_artifact',
           'the exact bytes that crossed the network, sealed under a key this '
             || 'bundle does not carry; the Agent view of the same exchange is '
             || 'packaged instead',
           count(*)
      FROM held
     WHERE view = 'wire' AND visibility = 'credential_bearing'
    HAVING count(*) > 0
    UNION ALL
    SELECT 'identity_material',
           'Identity slots were leased for these exchanges; no credential, '
             || 'cookie or required header value for any of them is in this bundle',
           count(DISTINCT identity_entity_id)
      FROM cited
     WHERE identity_entity_id IS NOT NULL
    HAVING count(*) > 0
    UNION ALL
    SELECT 'query_string',
           'these exchanges carried a query string; the harness recorded its '
             || 'digest and never its text, so the bundle carries the digest',
           count(*)
      FROM cited
     WHERE query_sha256 IS NOT NULL
    HAVING count(*) > 0
    UNION ALL
    SELECT 'sealed_agent_view',
           'the Agent view of these exchanges is itself credential-bearing and '
             || 'sealed; the report cites it by hash and the bundle carries the '
             || 'hash and not the bytes',
           count(*)
      FROM held
     WHERE view = 'agent' AND (visibility = 'credential_bearing' OR encrypted)
    HAVING count(*) > 0
    UNION ALL
    SELECT 'purged_artifact',
           'these Agent-view artifacts were purged from this harness; a bundle '
             || 'carrying them would be the one place that decision could be undone',
           count(*)
      FROM held
     WHERE view = 'agent' AND purged_at IS NOT NULL
    HAVING count(*) > 0;
$fn$;

COMMENT ON FUNCTION evidence_exclusions(uuid[]) IS
    'Ticket 43 criterion 2: what these exchanges hold that a bundle does not carry, as a count and a reason. Stated rather than left to be inferred -- a reader cannot tell material that was excluded from material that was never there, and the two Agent-view arms are the ones `evidence_artifacts` withholds silently without them.';


-- ---------------------------------------------------------------------------
-- 4. Staleness, which 042 had no reason to ask about
-- ---------------------------------------------------------------------------
-- Criterion 4 says the export "refuses stale, invalidated or review-gated
-- material". Two of the three are already refused: the export renders through
-- 042, and 042 refuses on `report_blockers` and on `rk2_chain_unsoundness`,
-- which is where `invalidated`, `candidate`, `duplicate` and `known_issue` are
-- decided.
--
-- Stale is the third and it is not the same question. A rendering somebody read
-- and approved is a row in `report_renderings` carrying the source digest it was
-- made from, and 034's approval gate compares that against the digest now. A
-- bundle exported after the rows moved would carry a fresh document under a
-- label a human approved a different document for -- which is the one way a
-- correct renderer can still put an unapproved claim in front of a Program.
--
-- This answers the comparison and does not make it. Whether a Finding with no
-- rendering at all may be exported is the exporter's decision, and it is yes:
-- an approval is a step in submitting, not a precondition for packaging what
-- holds right now.
CREATE FUNCTION evidence_stale_rendering(p_finding uuid, p_template text)
RETURNS jsonb LANGUAGE sql STABLE AS $fn$
    SELECT jsonb_build_object(
             'rendering',     rr.id,
             'rendered_at',   to_char(rr.rendered_at AT TIME ZONE 'UTC',
                                      'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
             'approved',      EXISTS (SELECT 1 FROM finding_transitions ft
                                       WHERE ft.approved_rendering_id = rr.id),
             'source_digest', rr.source_digest,
             'digest_now',    finding_source_digest(p_finding, p_template),
             'stale',         rr.source_digest
                                IS DISTINCT FROM finding_source_digest(p_finding, p_template))
      FROM report_renderings rr
     WHERE rr.finding_id = p_finding
       AND rr.template_id = p_template
       AND rr.program_id = rk2_program_required()
     -- The most recent one. Two renderings of one Finding under one form differ
     -- only in when they were made, and the question is about the document a
     -- human most recently read.
     ORDER BY rr.rendered_at DESC, rr.id DESC
     LIMIT 1;
$fn$;

COMMENT ON FUNCTION evidence_stale_rendering(uuid, text) IS
    'Ticket 43 criterion 4: the last filed rendering of this Finding under this form, and whether the source it was made from is still the source. NULL when nothing has been filed, which is not staleness -- it is a Finding nobody has read yet.';


-- ---------------------------------------------------------------------------
-- 5. The rules, as a query
-- ---------------------------------------------------------------------------

CREATE FUNCTION check_evidence_export()
RETURNS TABLE (rule text, obj text, detail text)
LANGUAGE sql STABLE AS $fn$
    -- 1. every redaction rule still matches the string it was written for. A
    --    pattern that matches nothing removes nothing and leaves a bundle that
    --    is indistinguishable from a redacted one.
    SELECT 'rule_matches_no_probe', r.id, r.probe
      FROM redaction_rules r
     WHERE r.probe !~ r.pattern
    UNION ALL
    -- 2. and still declines the string it was written to leave alone. Arm 1 on
    --    its own is satisfied by `.`, and the cost of over-matching is not a leak
    --    but a refusal: the verifier rescans every packed file, so a rule that
    --    claims timestamps stops every export until an operator disables it.
    SELECT 'rule_matches_counter_probe', r.id, r.counter_probe
      FROM redaction_rules r
     WHERE r.counter_probe ~ r.pattern
    UNION ALL
    -- 3. a bundle of each subject carries every file criterion 1 needs it to.
    --    One row deleted from the registry is one file the exporter stops
    --    writing and the verifier stops asking for, and nothing else in the
    --    tree would object.
    SELECT 'bundle_incomplete', s.subject, f
      FROM (SELECT DISTINCT subject FROM report_templates) s
      CROSS JOIN LATERAL unnest(rk2_evidence_required_files()) f
     WHERE NOT EXISTS (SELECT 1 FROM evidence_bundle_files b
                        WHERE b.subject = s.subject AND b.path = f)
    UNION ALL
    -- 4. a registered file for a subject no form is about. The CHECK constrains
    --    the vocabulary; this asks the other question, which is whether anything
    --    can be rendered for that subject at all.
    SELECT 'file_of_unrendered_subject', b.subject || '/' || b.path, b.purpose
      FROM evidence_bundle_files b
     WHERE NOT EXISTS (SELECT 1 FROM report_templates t WHERE t.subject = b.subject);
$fn$;

COMMENT ON FUNCTION check_evidence_export() IS
    'Ticket 43: what may leave, as an invariant. Every redaction rule matches its own probe and declines its own counter-probe, every subject that can be rendered carries every file a bundle owes, and no file is registered for a subject nothing renders. Zero rows is the invariant.';


-- ===========================================================================
-- Z. Wiring
-- ===========================================================================

INSERT INTO program_global_tables (table_name, reason) VALUES
    ('evidence_bundle_files',
     'the shape of what leaves this harness is a property of the harness, not of a target');

INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('evidence_bundle_files', 'reference',
     'the files a bundle carries, changed only by migration', '43');

-- Section 2's registry is read and never written by the runtime. The default
-- privileges 029 issues would leave the runtime able to delete the row that
-- makes `verify.py` a file every bundle carries, which is the one edit that
-- would turn an unverifiable bundle into a complete-looking one.
--
-- Two verbs and not three, for 20260819T000000Z's reason about
-- `severity_unlock_weights`: `readwrite_on_every_managed_table` asserts the
-- runtime keeps SELECT and INSERT on every managed table, and a table it cannot
-- INSERT into fails the gate the whole harness opens on. The retained verb is
-- not a way in. The CHECK on `subject` admits two values and the CHECK on `path`
-- admits one filename shape, so an INSERT can only add a file the exporter does
-- not write -- and `_written` refuses when the registry owes a file the export
-- does not produce. That is an export that stops rather than an export that
-- leaves something out, which is the direction this table exists to fail in.
GRANT SELECT ON evidence_bundle_files TO rk2_runtime, rk2_human;
REVOKE UPDATE, DELETE ON evidence_bundle_files FROM rk2_runtime;
REVOKE ALL ON evidence_bundle_files FROM rk2_state, rk2_proxy;

GRANT EXECUTE ON FUNCTION rk2_evidence_required_files() TO rk2_runtime, rk2_human;
GRANT EXECUTE ON FUNCTION finding_evidence_receipts(uuid) TO rk2_runtime, rk2_human;
GRANT EXECUTE ON FUNCTION chain_evidence_receipts(uuid) TO rk2_runtime, rk2_human;
GRANT EXECUTE ON FUNCTION finding_evidence_specifications(uuid) TO rk2_runtime, rk2_human;
GRANT EXECUTE ON FUNCTION chain_evidence_specifications(uuid) TO rk2_runtime, rk2_human;
GRANT EXECUTE ON FUNCTION evidence_artifacts(uuid[]) TO rk2_runtime, rk2_human;
GRANT EXECUTE ON FUNCTION evidence_receipts(uuid[]) TO rk2_runtime, rk2_human;
GRANT EXECUTE ON FUNCTION evidence_exclusions(uuid[]) TO rk2_runtime, rk2_human;
GRANT EXECUTE ON FUNCTION evidence_stale_rendering(uuid, text) TO rk2_runtime, rk2_human;
GRANT EXECUTE ON FUNCTION check_evidence_export() TO rk2_runtime, rk2_human;

-- The columns section 1 added, published to the Agent state surface beside the
-- five 034 published. Both are synthetic strings and say nothing about a target;
-- withholding them would make the read surface disagree with the table for no
-- reason anyone could state.
INSERT INTO state_read_surface (table_name, column_name, added_by) VALUES
 ('redaction_rules', 'probe', '43'),
 ('redaction_rules', 'counter_probe', '43');

INSERT INTO standing_checks (name, query, owner_ticket, note) VALUES
 ('evidence_export', 'SELECT * FROM check_evidence_export()', '43',
  'every redaction rule matches its own probe and declines its own counter-probe, and a bundle of every renderable subject carries the document, its source, the receipts, the hashes and the verifier');

DO $$
DECLARE n integer;
BEGIN
    SELECT count(*) INTO n FROM redaction_rules
     WHERE probe IS NULL OR probe = '' OR counter_probe IS NULL OR counter_probe = '';
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-43 left % redaction rule(s) without both witnesses', n;
    END IF;

    SELECT count(*) INTO n FROM check_evidence_export();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-43 installed a check its own corpus fails, % row(s)', n;
    END IF;
END $$;
