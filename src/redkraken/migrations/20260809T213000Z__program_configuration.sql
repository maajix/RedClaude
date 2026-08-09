-- ===========================================================================
-- Production harness 04 -- a Program is opened by a configuration revision
-- ===========================================================================
-- `rk run` takes one validated configuration file and either opens a Program
-- from it or resumes the Program that file already opened. Both halves need a
-- durable answer to the same question, and the corpus did not have one: which
-- configuration is this Program running under?
--
-- Without it, "resume the same Program" degrades into "find a row with the
-- same slug and hope the policy behind it has not moved". A budget halved, a
-- scope entry removed or a rule of engagement flipped between two runs would
-- be adopted silently, and every Receipt, Observation and Finding written
-- afterwards would cite a policy nobody recorded. `program_scope_versions`
-- already refuses that shape for scope, for exactly this reason, and says so
-- in its own comment: a policy change mid-hunt is a new version, never an
-- edit. This migration extends the same rule to the whole configuration.
--
-- So: append-only revisions, each carrying both hashes the loader computes.
-- `canonical_sha256` is the policy -- sorted-key compact JSON, so reordering
-- keys or reflowing the file does not make a new revision -- and
-- `source_sha256` names the bytes on disk that produced it. The runtime
-- compares the canonical hash to decide whether the operator changed the
-- policy or only the file.
--
-- The root `programs` row is left classified as it was. What a Program IS now
-- emits an event; whether the identity row should emit one of its own is
-- ticket 07's question, not this one's.
-- ===========================================================================


-- ---------------------------------------------------------------------------
-- 1. The revisions
-- ---------------------------------------------------------------------------

CREATE TABLE program_configurations (
    id               uuid    NOT NULL DEFAULT uuidv7(),
    program_id       uuid    NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    revision         integer NOT NULL CHECK (revision >= 1),
    schema_version   integer NOT NULL CHECK (schema_version >= 1),

    -- Where the bytes were read from, for an operator reading a revision back
    -- months later. Not an identity: two machines can hold the same policy at
    -- different paths, and the hashes are what say whether they agree.
    source_path      text     NOT NULL,
    source_sha256    char(64) NOT NULL CHECK (source_sha256    ~ '^[0-9a-f]{64}$'),
    canonical_sha256 char(64) NOT NULL CHECK (canonical_sha256 ~ '^[0-9a-f]{64}$'),

    -- The validated document, as the loader accepted it. The closed schema
    -- admits no inline secret -- a credential is a `slot://` reference and
    -- nothing else -- so this column holds policy, never key material. Stored
    -- as jsonb, which normalises: key order and whitespace do not survive it,
    -- so `canonical_sha256` and not this column is what identifies the policy.
    document         jsonb    NOT NULL,

    -- The two values this revision projects onto the root `programs` row, which
    -- is where the scheduler and the quota views read them from. They are
    -- restated here because `programs` emits no event of its own yet, so the
    -- projection would otherwise be a policy change with no before and after
    -- anywhere in the log -- exactly what the revision history exists to stop.
    -- `check_program_configuration()` fails the gate if the two disagree.
    platform         text,
    token_budget     bigint   NOT NULL CHECK (token_budget > 0),

    -- Why this revision exists. The first one says the Program was opened; a
    -- later one says an operator accepted a change, and to what.
    reason           text     NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),

    PRIMARY KEY (program_id, revision),
    UNIQUE (program_id, id)
);

COMMENT ON TABLE program_configurations IS
  'Append-only. The configuration a Program runs under is a revision, never an edit: a Finding cites the policy that authorised the work behind it, and rewriting a revision would rewrite what that citation means. `rk run` records revision 1 when it opens a Program and refuses a changed policy afterwards unless the operator accepts the change, which records the next revision.';

COMMENT ON COLUMN program_configurations.canonical_sha256 IS
  'The policy identity: sha256 over sorted-key compact JSON, so reflowing the file or reordering its keys is not a policy change.';

COMMENT ON COLUMN program_configurations.source_sha256 IS
  'The bytes on disk that produced this revision. Two revisions can share a canonical hash and differ here; that is a file edit that changed no policy.';

-- The same immutability the event log and the scope versions have, through the
-- same function, so a program purge can still delete the rows and nothing else
-- can. `check_purge_reachability()` reads this function's body for
-- `app.purging` and fails the gate for a BEFORE DELETE trigger that ignores it.
CREATE TRIGGER program_configurations_immutable
    BEFORE UPDATE OR DELETE ON program_configurations
    FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_purging();

-- Program-scoped, so it reaches the purge root directly. 016 swept the tables
-- that existed when it ran; a table added afterwards registers its own edge.
INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('program_configurations', 'program_id', 'program-scoped: the purge root');


-- ---------------------------------------------------------------------------
-- 2. The event
-- ---------------------------------------------------------------------------
-- Decision 15 asks for a semantic name on an immutable table, and this one has
-- no update to describe: a revision happens once and then stands. The event is
-- trigger-authored like every other row event, so a configuration recorded by
-- any path -- `rk run`, a repair, a future import -- carries its event with it
-- rather than depending on the writer remembering.
--
-- `document` is redacted rather than ignored: the log has to show that the
-- policy changed without reprinting the policy into a table that different
-- connections read. Both hashes stay in the clear, which is what makes the
-- event answer "which policy" without carrying any of its values.
--
-- `platform` and `token_budget` stay in the clear too, and they are the reason
-- the redaction is affordable: what the revision changed about the Program's
-- own row is readable in the log without the document being in it.

INSERT INTO event_types (id, family, subject_table, description) VALUES
    ('program.configured', 'row', 'program_configurations',
     'a Program configuration revision was recorded: revision 1 opens the Program, a later one is a policy change an operator accepted');

INSERT INTO event_table_config
    (table_name, created_type, updated_type, ignored_columns, redacted_columns) VALUES
    ('program_configurations', 'program.configured', NULL, '{}', '{document}');

SELECT attach_event_triggers();


-- ---------------------------------------------------------------------------
-- 3. The invariants this table introduces
-- ---------------------------------------------------------------------------
-- Four, and each of them is a way the create-or-resume path can be wrong
-- without any single statement being illegal.

CREATE FUNCTION check_program_configuration()
RETURNS TABLE (problem text, object text, detail text)
LANGUAGE sql STABLE AS $$
    -- 1. A Program nobody can say the policy of. This is what a create path
    --    that wrote the root row and then failed leaves behind, and what a
    --    Program opened by hand around `rk run` would leave behind for good.
    SELECT 'program_without_configuration', p.slug,
           'programs row with no program_configurations revision; nothing records the policy it runs under'
      FROM programs p
     WHERE NOT EXISTS (SELECT 1 FROM program_configurations c
                        WHERE c.program_id = p.id)
  UNION ALL
    -- 2. Revisions are 1..n with no gap. A gap means a revision was lost, and
    --    a lost revision is a policy that authorised work and cannot be read
    --    back -- the failure the append-only rule exists to prevent.
    SELECT 'configuration_revisions_not_contiguous', p.slug,
           'revisions ' || c.lowest || '..' || c.highest || ' but ' || c.total || ' row(s)'
      FROM programs p
      JOIN (SELECT program_id, min(revision) AS lowest, max(revision) AS highest,
                   count(*) AS total
              FROM program_configurations GROUP BY program_id) c
        ON c.program_id = p.id
     WHERE c.lowest <> 1 OR c.highest <> c.total
  UNION ALL
    -- 3. A revision that changes nothing. Recording one is how a resume path
    --    that compares the wrong hash announces itself: the policy is
    --    identical, so the revision says a change happened that did not, and
    --    every row citing it afterwards cites a version number with no meaning.
    SELECT 'configuration_revision_changes_nothing',
           p.slug || ' revision ' || c.revision,
           'canonical_sha256 is identical to revision ' || (c.revision - 1)
      FROM program_configurations c
      JOIN program_configurations prior
        ON prior.program_id = c.program_id AND prior.revision = c.revision - 1
       AND prior.canonical_sha256 = c.canonical_sha256
      JOIN programs p ON p.id = c.program_id
  UNION ALL
    -- 4. The Program is not running the policy its newest revision states.
    --    `programs` carries the platform and the token budget as columns
    --    because the scheduler and the quota views read them there, and it
    --    emits no event of its own, so a write that moved them without
    --    recording a revision is a policy change with no before and after. The
    --    revision history is only worth citing if this cannot happen quietly.
    SELECT 'configuration_not_applied', p.slug || ' revision ' || c.revision,
           'the Program runs platform ' || coalesce(p.platform, '(none)') ||
           ' with budget ' || coalesce(p.token_budget::text, '(none)') ||
           '; its newest revision states ' || coalesce(c.platform, '(none)') ||
           ' with ' || c.token_budget
      FROM programs p
      JOIN LATERAL (SELECT revision, platform, token_budget
                      FROM program_configurations
                     WHERE program_id = p.id
                     ORDER BY revision DESC
                     LIMIT 1) c ON true
     WHERE p.platform     IS DISTINCT FROM c.platform
        OR p.token_budget IS DISTINCT FROM c.token_budget
$$;

COMMENT ON FUNCTION check_program_configuration() IS
  'Every Program states the policy it runs under, the statement is complete, no revision claims a change that did not happen, and the Program runs what its newest revision states.';

INSERT INTO standing_checks (name, query, owner_ticket, note) VALUES
    ('program_configuration', 'SELECT * FROM check_program_configuration()', 'PH2-04',
     'every Program has a contiguous configuration history, every revision in it changed something, and the root row matches the newest one');


-- ---------------------------------------------------------------------------
-- 4. The runtime may read which migrations are applied
-- ---------------------------------------------------------------------------
-- `rk run` asserts readiness before it writes anything, and readiness is the
-- integrity gate run on the runtime's own connection rather than on a
-- privileged one borrowed for the occasion. It runs the two families the
-- runtime is entitled to run: the baseline and the standing checks. The role
-- catalogue is deliberately not among them -- 0029 gates
-- `check_role_catalogue()` away from PUBLIC because it is the runner's, and
-- ticket 66 closes the default-privilege grant that currently leaves it
-- reachable as `rk2_runtime` anyway, so a runtime command that depended on it
-- would start failing the day that ticket lands.
--
-- Two of `check_server_baseline()`'s checks read `rk2_meta.schema_migrations`
-- -- "no migration in the database with no file" and "no file not applied" --
-- and that schema was reachable only by its owner, so the whole baseline family
-- raised a permission error and the gate reported an invariant it could not
-- answer as one that failed.
--
-- The grant is SELECT on one table. The runtime cannot write it -- INSERT there
-- is the runner's, and `rk2_runtime` is not a member of `rk2_owner` -- so what
-- this buys is the ability to answer "is this database the schema this build
-- was written against?" before opening a Program against it. Refusing to let
-- the runtime see the schema version does not make the mismatch impossible; it
-- makes it undetectable until the first missing relation.
GRANT USAGE ON SCHEMA rk2_meta TO rk2_runtime;
GRANT SELECT ON rk2_meta.schema_migrations TO rk2_runtime;


-- ---------------------------------------------------------------------------
-- 5. Bring the end-of-run invariants to true for the new table
-- ---------------------------------------------------------------------------
-- The runner calls both finalizers again after the last migration, so this is
-- not what makes them hold. It is what makes this file self-contained: applied
-- on its own, it leaves a table with row level security on it and the two
-- policies every other program-scoped table has, rather than one that only
-- becomes correct at the end of somebody else's run.
SELECT apply_state_rls();
SELECT apply_state_grants();
