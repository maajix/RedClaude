-- ===========================================================================
-- Production harness 06 -- one Artifact, stored by hash, reachable from one
-- Program
-- ===========================================================================
-- 005 built `artifacts`: a content-addressed store keyed by the SHA-256 of the
-- plaintext, deliberately program-global because the same bytes seen by two
-- Programs are one row. 020 built the reachability rule that keeps that global
-- table from becoming a global read -- the agent connection may select an
-- artifact only if some row of its own Program refers to it -- and implemented
-- the reference side as a view over four `receipts` columns.
--
-- Which means that today the only way for a Program to hold an artifact is to
-- have made an HTTP request. Nothing else can refer to one. A tool's output, a
-- fetched script, a file an operator hands the harness: there is a row for the
-- bytes and no row that says whose bytes they are, so the artifact is stored,
-- global, and unreachable from every session.
--
-- `artifact_references` is that missing half. One labelled, immutable row per
-- (Program, hash, kind), which is what ticket 06 means by "distinct
-- Program-scoped references where appropriate": storing identical plaintext
-- from two Programs deduplicates the bytes and does not deduplicate the claim.
-- Reachability is the reference, so a bare hash from another Program still
-- answers with nothing -- not because a query filters it out, but because the
-- policy on `artifacts` asks `artifact_refs` and `artifact_refs` is now
-- row-level-security-scoped on both of its arms.
--
-- Three consequences worth stating before the DDL:
--
--   * The reference carries the label and the artifact carries the bytes. An
--     agent cites `AF1`; the hash is reported next to it because §6 of the spec
--     allows identifiers, lengths and digests to travel, but nothing on the
--     agent surface takes a hash as an argument. A verb that did would be a verb
--     that reads across Programs whenever the caller already knows a hash, which
--     for a content-addressed store means "whenever the caller can guess the
--     bytes".
--   * A reference is never made to credential-bearing or encrypted material.
--     Those are §6's other half -- wire artifacts, authenticated encryption,
--     key material outside the database -- and they belong to ticket 07. The
--     standing check below refuses the combination outright rather than relying
--     on the `artifacts` policy's predicate to keep filtering it, because the
--     property wanted here is that no label ever points at a secret, not that
--     one particular SELECT happens to exclude it.
--   * The foreign key to `artifacts` is NO ACTION on purpose. A reference whose
--     bytes have been deleted is exactly the "missing backing data" case ticket
--     06 asks to fail closed on, and the cheapest way to fail closed is for the
--     delete not to happen. `artifacts_due_for_purge` is widened below so the
--     purge path never proposes one.
-- ===========================================================================


-- ---------------------------------------------------------------------------
-- 1. The reference
-- ---------------------------------------------------------------------------
-- `kind` says why this Program holds these bytes, and is the third component of
-- the uniqueness rule: the same file stored twice by one Program is one
-- reference, and the same file arriving once as a tool's output and once as
-- fetched source is two, because those are two claims about the same bytes.

CREATE TABLE artifact_references (
    id         uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    label      text NOT NULL,
    sha256     text NOT NULL REFERENCES artifacts(sha256),
    kind       text NOT NULL DEFAULT 'runtime'
                    CHECK (kind IN ('runtime','tool_output','source')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (program_id, label),
    UNIQUE (program_id, sha256, kind)
);

COMMENT ON TABLE artifact_references IS
    'Which Program holds which content-addressed artifact, and why. Storage deduplicates across Programs; this table does not, and it is what reachability is decided on.';
COMMENT ON COLUMN artifact_references.sha256 IS
    'SHA-256 of the exact plaintext bytes. NO ACTION, not CASCADE: a reference whose bytes were deleted is the failure this ticket exists to make impossible.';

INSERT INTO label_prefixes (kind, prefix) VALUES ('artifact_references', 'AF');

CREATE TRIGGER artifact_references_assign_label BEFORE INSERT ON artifact_references
    FOR EACH ROW EXECUTE FUNCTION assign_label();

-- Immutable. A reference is a statement that a Program saw these exact bytes;
-- changing which bytes it names afterwards would rewrite history, and the
-- digest that made it citable would no longer be the digest of anything.
CREATE TRIGGER artifact_references_immutable
    BEFORE UPDATE OR DELETE ON artifact_references
    FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_purging();

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('artifact_references', 'program_id', 'program-scoped: the purge root');


-- ---------------------------------------------------------------------------
-- 2. Creating one is audited, and the audit carries no bytes
-- ---------------------------------------------------------------------------
-- The row is the whole payload: a program, a label, a hash, a kind and an
-- instant. §6 of the spec allows identifiers, lengths and digests into the log
-- and nothing else, and the way to mean it is for the table the event is built
-- from to hold nothing else. There is no `redacted_columns` entry because there
-- is no column here that would need one.
--
-- `artifacts` itself stays exempt, and its classification stops being
-- `undecided`. It is program-global, so it has no Program to emit into and the
-- log has nowhere to put the event; what an operator actually wants to audit is
-- who came to hold the bytes, which is this table. The hash is in this payload
-- and the length is the one join away from it that `artifacts` has always been,
-- so nothing an operator has to reconstruct is lost by the exemption.

INSERT INTO event_types (id, family, subject_table, description) VALUES
    ('artifact.referenced', 'row', 'artifact_references',
     'a Program came to hold a content-addressed artifact');

INSERT INTO event_table_config
    (table_name, created_type, updated_type, ignored_columns, redacted_columns) VALUES
    ('artifact_references', 'artifact.referenced', NULL, '{}', '{}');

UPDATE event_table_exempt
   SET exempt_kind = 'bookkeeping',
       reason = 'content-addressed store, program-global, so an event has no Program to belong to; artifact.referenced on artifact_references records who came to hold the bytes, with the hash and without the bytes',
       owner_ticket = 'ph2-06'
 WHERE table_name = 'artifacts';

SELECT attach_event_triggers();


-- ---------------------------------------------------------------------------
-- 3. Reachability now has two arms
-- ---------------------------------------------------------------------------
-- Same four columns, so the `artifacts` policy 020 wrote and the scheduler's
-- `analyze` gate in 023 keep working unchanged. Both arms are scoped by row
-- level security on the tables underneath, which is what makes the policy that
-- reads this view an isolation boundary rather than a filter.

CREATE OR REPLACE VIEW artifact_refs WITH (security_invoker = true) AS
    SELECT program_id, request_agent_sha AS sha256,
           'receipt_request'::text AS ref_kind, label AS ref_label
      FROM receipts WHERE request_agent_sha IS NOT NULL
    UNION ALL
    SELECT program_id, response_agent_sha AS sha256,
           'receipt_response'::text AS ref_kind, label AS ref_label
      FROM receipts WHERE response_agent_sha IS NOT NULL
    UNION ALL
    SELECT program_id, sha256, kind AS ref_kind, label AS ref_label
      FROM artifact_references;

COMMENT ON VIEW artifact_refs IS
    'Every path by which a Program reaches an artifact: the four receipt columns and the reference table. The policy on `artifacts` is this view, so a bare hash reveals nothing without one of these rows.';

-- The purge path learns the second arm too. Without this an artifact a live
-- Program still refers to would be proposed for deletion, and the NO ACTION key
-- above would turn that into a refused delete at the end of a purge rather than
-- a decision not to propose it.
CREATE OR REPLACE VIEW artifacts_due_for_purge AS
SELECT a.sha256
  FROM artifacts a
 WHERE a.purged_at IS NULL
   AND NOT EXISTS (
        SELECT 1 FROM receipts r JOIN programs p ON p.id = r.program_id
         WHERE (a.sha256 IN (r.request_agent_sha, r.request_wire_sha,
                             r.response_agent_sha, r.response_wire_sha))
           AND (p.purge_after IS NULL OR p.purge_after > now()))
   AND NOT EXISTS (
        SELECT 1 FROM artifact_references x JOIN programs p ON p.id = x.program_id
         WHERE x.sha256 = a.sha256
           AND (p.purge_after IS NULL OR p.purge_after > now()));


-- ---------------------------------------------------------------------------
-- 4. What the agent connection sees
-- ---------------------------------------------------------------------------
-- 020's `v_artifacts` projected the store: every row of `artifacts` the policy
-- let through, plus a global `ref_count` computed across Programs. The count is
-- the problem. It answers "how many other things hold these bytes", which for a
-- content-addressed store with one shared namespace is a question about other
-- Programs, and it is the only number in the whole agent surface that is not a
-- fact about the session's own rows. Nothing reads the view today, so the
-- cheapest time to remove it is before something does.
--
-- What replaces it is the reference, joined to the length and type of what it
-- names. No uuid, per 020's rule 5; no `visibility`, `encrypted` or `purged_at`,
-- because the check below makes all three constant across everything this view
-- can return, and a column whose value is fixed by an invariant is a column that
-- invites the model to reason about the cases the invariant already excluded.

DROP VIEW v_artifacts;
DELETE FROM state_read_surface WHERE table_name IN ('v_artifacts', 'artifact_refs');

CREATE VIEW v_artifacts WITH (security_invoker = true) AS
    SELECT x.label,
           x.kind,
           x.sha256,
           a.byte_size,
           a.content_type,
           rk2_instant(x.created_at) AS created_at
      FROM artifact_references x
      JOIN artifacts a ON a.sha256 = x.sha256;

COMMENT ON VIEW v_artifacts IS
    'The artifacts this Program holds, by label. The hash is reported and is never an argument: a verb taking one would read across Programs whenever the caller could guess the bytes.';

-- Per column, like the rest of the surface. `artifact_references.program_id` is
-- readable for the same reason `entities.program_id` is -- row level security
-- scopes it to the identifier the session is already bound to -- and it is here
-- because `artifact_refs` selects it and a security_invoker view is read with
-- the caller's own privileges.
INSERT INTO state_read_surface (table_name, column_name, added_by) VALUES
    ('artifact_references', 'program_id',   'ph2-06'),
    ('artifact_references', 'label',        'ph2-06'),
    ('artifact_references', 'sha256',       'ph2-06'),
    ('artifact_references', 'kind',         'ph2-06'),
    ('artifact_references', 'created_at',   'ph2-06'),
    ('artifact_refs',       'program_id',   'ph2-06'),
    ('artifact_refs',       'sha256',       'ph2-06'),
    ('artifact_refs',       'ref_kind',     'ph2-06'),
    ('artifact_refs',       'ref_label',    'ph2-06'),
    ('v_artifacts',         'label',        'ph2-06'),
    ('v_artifacts',         'kind',         'ph2-06'),
    ('v_artifacts',         'sha256',       'ph2-06'),
    ('v_artifacts',         'byte_size',    'ph2-06'),
    ('v_artifacts',         'content_type', 'ph2-06'),
    ('v_artifacts',         'created_at',   'ph2-06');


-- ---------------------------------------------------------------------------
-- 5. The four rules, as a query that returns the violations
-- ---------------------------------------------------------------------------

CREATE FUNCTION check_artifact_reachability()
RETURNS TABLE (problem text, object text, detail text)
LANGUAGE sql STABLE AS $$
    -- 1. every reference names bytes that are still there. This is the database
    --    half of "missing backing data fails closed"; the filesystem half is
    --    `rk artifact audit`, which re-hashes what it reads and cannot be
    --    asked from inside the server.
    SELECT 'artifact_reference_dangling', x.label,
           'references ' || x.sha256 || ', which is ' ||
           CASE WHEN a.sha256 IS NULL THEN 'not in the store'
                ELSE 'purged at ' || a.purged_at::text END
      FROM artifact_references x
      LEFT JOIN artifacts a ON a.sha256 = x.sha256
     WHERE a.sha256 IS NULL OR a.purged_at IS NOT NULL

  UNION ALL
    -- 2. no label points at a secret. Credential-bearing and encrypted material
    --    is reached through the wire columns of a receipt and decrypted by the
    --    proxy, never by a Program citing a short name (§6, ticket 07).
    SELECT 'artifact_reference_to_secret', x.label,
           'references ' || a.visibility ||
           CASE WHEN a.encrypted THEN ', encrypted' ELSE '' END ||
           ' material; a reference is an agent-reachable name'
      FROM artifact_references x
      JOIN artifacts a ON a.sha256 = x.sha256
     WHERE a.visibility <> 'agent_visible' OR a.encrypted

  UNION ALL
    -- 3. the reference cannot be orphaned by deleting the bytes. Anything but
    --    NO ACTION or RESTRICT here would let a purge produce rule 1's state
    --    instead of refusing.
    SELECT 'artifact_reference_orphanable', con.conname,
           'ON DELETE ' || con.confdeltype::text || ': deleting an artifact would leave a reference behind'
      FROM pg_constraint con
      JOIN pg_class src ON src.oid = con.conrelid
      JOIN pg_class tgt ON tgt.oid = con.confrelid
     WHERE con.contype = 'f' AND src.relname = 'artifact_references'
       AND tgt.relname = 'artifacts' AND con.confdeltype NOT IN ('a', 'r')

  UNION ALL
    -- 4. the bridge is read as its caller. As `SECURITY DEFINER` -- which for a
    --    view means security_invoker off -- `artifact_refs` would answer with
    --    the owner's view of every Program's references, and the policy on
    --    `artifacts` that consults it would stop being a boundary.
    SELECT 'artifact_bridge_definer', c.relname, 'security_invoker is not set'
      FROM pg_class c
     WHERE c.relkind = 'v' AND c.relnamespace = 'public'::regnamespace
       AND c.relname IN ('artifact_refs', 'v_artifacts')
       AND coalesce((SELECT option_value FROM pg_options_to_table(c.reloptions)
                      WHERE option_name = 'security_invoker'), 'false') <> 'true'
$$;

INSERT INTO standing_checks (name, query, owner_ticket, note) VALUES
    ('artifact_reachability', 'SELECT * FROM check_artifact_reachability()', 'ph2-06',
     'every Program-scoped reference names bytes that are present, non-secret and undeletable from under it, through a bridge that is read as its caller');


-- ---------------------------------------------------------------------------
-- 6. Bring the invariants to true for the corpus as it stands
-- ---------------------------------------------------------------------------
-- The runner calls both again at the end of every run. Calling them here is
-- what makes the new table's row level security and the new grants real inside
-- the transaction that declares them, and what makes this file self-contained
-- if someone applies it by hand.
--
-- `assert_standing_checks()` is deliberately not called, for the reason 05's
-- file gives: this is the last file in the corpus, so it runs before the
-- finalizers, and several registered checks describe invariants those
-- finalizers establish. What is asserted here is this file's own rule.

SELECT apply_state_rls();
SELECT apply_state_grants();

DO $$
DECLARE n integer; v record;
BEGIN
    SELECT count(*) INTO n FROM check_artifact_reachability();
    IF n > 0 THEN
        FOR v IN SELECT * FROM check_artifact_reachability() LOOP
            RAISE WARNING 'artifact reachability violation: % % %', v.problem, v.object, v.detail;
        END LOOP;
        RAISE EXCEPTION 'ph2-06 refuses to finish: % artifact-reachability violation(s)', n;
    END IF;
END $$;
