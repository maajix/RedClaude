-- ===========================================================================
-- Production harness 07 -- the wire artifact, encrypted, and the two views of
-- one exchange kept apart
-- ===========================================================================
-- Ticket 06 stored plaintext. Everything it wrote is `agent_visible`, and
-- `check_artifact_reachability()` refuses a label that points anywhere else, so
-- the credential-bearing half of §6 has been unbuilt and unreachable rather than
-- built and trusted.
--
-- This file builds it. A wire artifact is the exact bytes that crossed the
-- network, which is what makes it worth keeping -- it is the only evidence that
-- can be replayed or shown to a program -- and what makes keeping it dangerous:
-- it carries the credential the harness injected. The arrangement is:
--
--   * The bytes on disk are the ciphertext, in a self-describing envelope, filed
--     under the hash of the *envelope*. `rk db verify --artifacts` can then hold
--     every sealed envelope against its recorded identifier with no key at all,
--     which is what makes the store checkable by an operator who is not allowed
--     to read it. 005's comment says the filename is the plaintext hash; that
--     was written for a single installation-wide key, where plaintext-hash
--     filing still deduplicates. Per-Program keys end that -- two Programs
--     sealing identical bytes produce different ciphertext -- so the reason for
--     the old rule is gone and the reason against it is not: a file named by its
--     plaintext hash cannot be verified without decrypting it.
--   * The database records the algorithm, the nonce and the plaintext hash, and
--     no key. §6 asks for exactly those three, and `artifacts.sha256` is already
--     the plaintext hash, so the seal row is the other two plus the pairing.
--     Note what the plaintext hash is a hash *of*: the whole wire message, not
--     the credential in it. A digest of a short secret is a secret; a digest of
--     an HTTP exchange is not.
--   * The key is a file this process reads and no statement can open. What lives
--     in `secret_kek` is a random salt and a check value -- an HMAC output, not
--     a key -- so a database dump is a dump of ciphertext and the check is what
--     makes "wrong key material" answerable before any ciphertext is touched.
--     `secret_dek` stays empty on purpose and rule 8 below says so: 024's design
--     wrapped a key per scope, and a derived key needs no row, which is a
--     stronger form of "outside the database" than a wrapped one.
--   * The agent-visible view and the wire view are two artifacts, two hashes and
--     two rows, and the seal is what pairs them. Redaction is never an overwrite:
--     both hashes describe exactly the bytes their party saw, and neither is
--     derived from the other.
--
-- What is deliberately not closed here is named at rule 2: `register_proxy_-
-- artifacts()` writes four hashes with `byte_size = 0` and no bytes anywhere,
-- so a wire hash the proxy registered has nothing to seal yet. The rule fires on
-- an encrypted artifact that has bytes and no seal, which is every artifact this
-- ticket's path can produce and none of the proxy's placeholders. The proxy
-- storing real bytes is ticket 09's, and it will store them through this seal.
-- ===========================================================================


-- ---------------------------------------------------------------------------
-- 1. Which constructions a ciphertext may declare
-- ---------------------------------------------------------------------------
-- A registry rather than a CHECK, for the reason the algorithm is recorded at
-- all: the construction that opens a ciphertext is a fact about the ciphertext,
-- not about the code that happens to be installed when someone reads it. Adding
-- a real AEAD later is a row here and a branch in the runtime, and every
-- existing seal keeps naming what it was actually sealed under.

CREATE TABLE seal_algorithms (
    name     text PRIMARY KEY,
    added_by text NOT NULL,
    note     text NOT NULL
);

COMMENT ON TABLE seal_algorithms IS
    'The authenticated-encryption constructions a seal may name. A ciphertext whose construction is implied by the installed code cannot be opened once that code has moved on.';

INSERT INTO seal_algorithms (name, added_by, note) VALUES
    ('rk-hkdf-sha256-ctr-hmac-v1', 'ph2-07',
     'HKDF-SHA256 subkeys per nonce, an HMAC-SHA256 counter-mode keystream, and encrypt-then-MAC with HMAC-SHA256 over a length-prefixed header binding the algorithm, the nonce, the Program, the key generation and the plaintext hash. Built from the standard library because the runtime has no dependencies; a library AEAD arrives as a second row here rather than as a rewrite of everything that reads a seal.');

INSERT INTO program_global_tables (table_name, reason) VALUES
    ('seal_algorithms', 'the constructions a ciphertext may declare; corpus-wide vocabulary');

INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('seal_algorithms', 'reference', 'algorithm vocabulary, changed only by migration', 'ph2-07');


-- ---------------------------------------------------------------------------
-- 2. The seal: what the ciphertext is, and which agent-visible bytes it pairs with
-- ---------------------------------------------------------------------------
-- 024 created `artifact_seal` and nothing has ever written a row into it, so
-- these columns arrive NOT NULL with no default: a seal that does not say how to
-- open it is not a seal, and there is no historical row to be lenient about.
--
-- `nonce` and `alg` are recorded here *and* inside the envelope on disk. That is
-- not redundancy: the database is the metadata record §6 asks for, the envelope
-- is what makes the store readable on its own, and the gate holds one against
-- the other. Two places that must agree is a check; one place is a hope.

ALTER TABLE artifact_seal
    ADD COLUMN alg               text    NOT NULL REFERENCES seal_algorithms(name),
    ADD COLUMN nonce             bytea   NOT NULL CHECK (octet_length(nonce) = 32),
    ADD COLUMN kek_gen           integer NOT NULL REFERENCES secret_kek(gen),
    ADD COLUMN ciphertext_sha256 text    NOT NULL UNIQUE
                                         CHECK (ciphertext_sha256 ~ '^[0-9a-f]{64}$'),
    ADD COLUMN agent_sha256      text    NOT NULL REFERENCES artifacts(sha256) ON DELETE CASCADE,
    ADD CONSTRAINT artifact_seal_two_views CHECK (agent_sha256 <> sha256);

COMMENT ON COLUMN artifact_seal.sha256 IS
    'SHA-256 of the wire PLAINTEXT: the identifier of the artifact this seal describes, and never the name of a file.';
COMMENT ON COLUMN artifact_seal.ciphertext_sha256 IS
    'SHA-256 of the envelope on disk. The store is filed under this, so a sealed envelope is verifiable without key material.';
COMMENT ON COLUMN artifact_seal.agent_sha256 IS
    'The redacted view of the same exchange. Two artifacts, two hashes, each describing exactly the bytes its party saw; redaction is never an overwrite of the wire artifact.';
COMMENT ON COLUMN artifact_seal.nonce IS
    'Fresh per seal. Sealing one plaintext twice must not produce equal ciphertext, or the store answers "these two bodies are the same" to anyone holding it and no key.';

-- Immutable, like every other evidentiary row. A seal whose nonce or algorithm
-- could be edited afterwards would describe bytes it no longer opens, and the
-- pairing of the two views would be a claim someone could rewrite. DELETE stays
-- possible under `app.purging`, which is how the cascade from `artifacts`
-- reaches it during a purge and how it fails everywhere else.
CREATE TRIGGER artifact_seal_immutable BEFORE UPDATE OR DELETE ON artifact_seal
    FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_purging();

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('artifact_seal', 'agent_sha256',
     'ON DELETE CASCADE to artifacts: the seal is the pairing of two views of one exchange and describes nothing once either view is gone');

UPDATE event_table_exempt
   SET exempt_kind = 'audit',
       reason = 'program-global, so an event has no Program to belong to; every seal and every open is a secret_access_log row, which is the audit surface for key operations and is not agent-readable',
       owner_ticket = 'ph2-07'
 WHERE table_name = 'artifact_seal';


-- ---------------------------------------------------------------------------
-- 3. A sealed artifact is not due for purge while its Program lives
-- ---------------------------------------------------------------------------
-- Ticket 06 widened this view for references. A sealed pair is reachable through
-- neither a receipt nor a reference -- the wire artifact deliberately has no
-- reference, because a reference is an agent-reachable name -- so without a
-- third arm every seal written would be proposed for deletion by the next purge
-- and the immutability trigger above would turn that into a refused purge.

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
           AND (p.purge_after IS NULL OR p.purge_after > now()))
   AND NOT EXISTS (
        SELECT 1 FROM artifact_seal s JOIN programs p ON p.id = s.scope_id
         WHERE s.scope_kind = 'program'
           AND a.sha256 IN (s.sha256, s.agent_sha256)
           AND (p.purge_after IS NULL OR p.purge_after > now()));


-- ---------------------------------------------------------------------------
-- 4. Asking the database whether a value is anywhere in it
-- ---------------------------------------------------------------------------
-- Criterion 3 is an absence -- a synthetic credential marker must not be in the
-- database, the logs, the Events, the diagnostics or an agent read -- and an
-- absence is only worth claiming if something looked. A dump is a serialisation
-- of the rows, so a marker in no column of any table is a marker in no dump of
-- it, and this asks that question directly instead of shelling out to `pg_dump`
-- and grepping a file whose format is not this repository's to depend on.
--
-- `bytea` is compared as bytes rather than as its hex rendering, because a
-- credential that reached a bytea column would be invisible to a text LIKE.
--
-- The needle is a parameter, so it reaches the server statement log if the
-- installation logs statements. That is acceptable for the thing this is for --
-- a synthetic marker in a test, or an operator checking after an incident -- and
-- would not be for a real credential. The comment says so where someone reaching
-- for it will read it.

CREATE FUNCTION find_in_database(needle text)
RETURNS TABLE (relation text, attribute text, hits bigint)
LANGUAGE plpgsql STABLE AS $fn$
DECLARE r record; n bigint; q text;
BEGIN
    IF needle IS NULL OR needle = '' THEN
        RAISE EXCEPTION 'find_in_database needs something to look for';
    END IF;
    FOR r IN
        SELECT c.relname, a.attname, t.typname
          FROM pg_attribute a
          JOIN pg_class c ON c.oid = a.attrelid
          JOIN pg_namespace ns ON ns.oid = c.relnamespace AND ns.nspname = 'public'
          JOIN pg_type t ON t.oid = a.atttypid
         -- Ordinary tables, partitioned parents and materialised views: every
         -- relkind in `public` that holds rows of its own. Foreign tables are
         -- deliberately not here -- reading one contacts another server, which
         -- is not a thing a question about this database should do -- and views
         -- are not, because a view holds nothing a base table does not.
         WHERE c.relkind IN ('r', 'p', 'm') AND a.attnum > 0 AND NOT a.attisdropped
         ORDER BY c.relname, a.attnum
    LOOP
        -- `strpos`, not LIKE: a marker containing `%` or `_` would otherwise be
        -- a pattern, and this has to answer about the literal value.
        IF r.typname = 'bytea' THEN
            q := format('SELECT count(*) FROM public.%I WHERE position($1::bytea in %I) > 0',
                        r.relname, r.attname);
        ELSE
            q := format('SELECT count(*) FROM public.%I WHERE strpos(%I::text, $1) > 0',
                        r.relname, r.attname);
        END IF;
        EXECUTE q INTO n USING needle;
        IF n > 0 THEN
            relation := r.relname; attribute := r.attname; hits := n;
            RETURN NEXT;
        END IF;
    END LOOP;
END $fn$;

COMMENT ON FUNCTION find_in_database(text) IS
    'Every table column holding this value. For synthetic markers and incident response: the needle travels as a query parameter, so do not pass a real credential.';

REVOKE ALL ON FUNCTION find_in_database(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION find_in_database(text) TO rk2_runtime;


-- ---------------------------------------------------------------------------
-- 5. The eight rules, as a query that returns the violations
-- ---------------------------------------------------------------------------

CREATE FUNCTION check_wire_artifact_secrecy()
RETURNS TABLE (problem text, object text, detail text)
LANGUAGE sql STABLE AS $$
    -- 1. a seal describes credential-bearing, encrypted material. The reverse
    --    reading matters more than it looks: it is what stops a seal being
    --    written over an artifact the agent can already read, which would pair
    --    a Program's own plaintext with a ciphertext of itself.
    SELECT 'seal_over_agent_visible_artifact', s.sha256,
           'sealed artifact is ' || a.visibility ||
           CASE WHEN a.encrypted THEN ', encrypted' ELSE ', not encrypted' END
      FROM artifact_seal s JOIN artifacts a ON a.sha256 = s.sha256
     WHERE a.visibility <> 'credential_bearing' OR NOT a.encrypted

  UNION ALL
    -- 2. wire bytes that exist are sealed bytes. `byte_size = 0` is excluded
    --    because `register_proxy_artifacts()` registers four hashes per
    --    intercepted call with no bytes behind any of them; there is nothing to
    --    seal until ticket 09 stores them, and it will store them sealed.
    SELECT 'unsealed_wire_artifact', a.sha256,
           a.byte_size || ' byte(s) of credential-bearing material with no seal describing it'
      FROM artifacts a
     WHERE a.encrypted AND a.byte_size > 0 AND a.purged_at IS NULL
       AND NOT EXISTS (SELECT 1 FROM artifact_seal s WHERE s.sha256 = a.sha256)

  UNION ALL
    -- 3. nothing credential-bearing is reachable from a session. The three arms
    --    are read directly rather than through `artifact_refs`, because that
    --    view is security_invoker and this check has to see every Program's rows
    --    rather than the caller's. Ticket 06's rule 2 covers the reference arm;
    --    this one also covers the receipt arms, where the failure would be the
    --    proxy recording a wire hash in an agent column.
    SELECT 'credential_bearing_artifact_reachable', a.sha256,
           'reachable as ' || u.ref_kind || ' by ' || u.program_id::text
      FROM artifacts a
      JOIN (
            SELECT program_id, request_agent_sha AS sha256, 'receipt_request' AS ref_kind
              FROM receipts WHERE request_agent_sha IS NOT NULL
             UNION ALL
            SELECT program_id, response_agent_sha, 'receipt_response'
              FROM receipts WHERE response_agent_sha IS NOT NULL
             UNION ALL
            SELECT program_id, sha256, kind FROM artifact_references
           ) u ON u.sha256 = a.sha256
     WHERE a.encrypted OR a.visibility <> 'agent_visible'

  UNION ALL
    -- 4. the agent-visible half of the pair is present, unpurged and readable.
    --    A seal pointing at missing or encrypted bytes is a pair with one view.
    SELECT 'sealed_pair_incomplete', s.sha256,
           'agent view ' || s.agent_sha256 || ' is ' ||
           CASE WHEN a.sha256 IS NULL THEN 'not in the store'
                WHEN a.purged_at IS NOT NULL THEN 'purged at ' || a.purged_at::text
                ELSE a.visibility || CASE WHEN a.encrypted THEN ', encrypted' ELSE '' END END
      FROM artifact_seal s
      LEFT JOIN artifacts a ON a.sha256 = s.agent_sha256
     WHERE a.sha256 IS NULL OR a.purged_at IS NOT NULL
        OR a.visibility <> 'agent_visible' OR a.encrypted

  UNION ALL
    -- 5. the Program that sealed it holds the agent view by name. Without this
    --    the redacted half exists and nothing can cite it, which is the same as
    --    not having produced one.
    SELECT 'sealed_pair_unheld', s.sha256,
           'no reference in program ' || s.scope_id::text || ' names ' || s.agent_sha256
      FROM artifact_seal s
     WHERE s.scope_kind = 'program'
       AND NOT EXISTS (SELECT 1 FROM artifact_references x
                        WHERE x.program_id = s.scope_id AND x.sha256 = s.agent_sha256)

  UNION ALL
    -- 6. the envelope is not itself an artifact. An `artifacts` row for the
    --    ciphertext hash would be a second, unsealed identifier for the same
    --    material, and rule 2 would not see it because it is not encrypted.
    SELECT 'ciphertext_registered_as_artifact', s.ciphertext_sha256,
           'the envelope of ' || s.sha256 || ' has an artifacts row of its own'
      FROM artifact_seal s
     WHERE EXISTS (SELECT 1 FROM artifacts a WHERE a.sha256 = s.ciphertext_sha256)

  UNION ALL
    -- 7. the agent connection reaches no part of the key arrangement. This
    --    duplicates what `check_state_grants()` derives from `state_read_surface`
    --    on purpose: that check answers "does the surface match the grants", and
    --    this one answers "is this table on the surface at all", which is the
    --    question a future registry row could quietly change.
    SELECT 'state_reaches_key_material', c.relname,
           'rk2_state holds relation-level ' || p.priv || ' on key material or its audit trail'
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
      CROSS JOIN (VALUES ('SELECT'),('INSERT'),('UPDATE'),('DELETE'),('REFERENCES')) AS p(priv)
     WHERE c.relname IN ('artifact_seal', 'secret_kek', 'secret_dek',
                         'secret_access_log', 'redaction_failure', 'seal_algorithms')
       AND has_table_privilege('rk2_state', c.oid, p.priv)

  UNION ALL
    -- and the same at column level, which is the shape the read surface grants
    -- in and therefore the shape an accidental registry row would arrive as.
    SELECT 'state_reaches_key_material', c.relname || '.' || a.attname,
           'rk2_state holds ' || p.priv || ' on key material or its audit trail'
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
      JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
      CROSS JOIN (VALUES ('SELECT'),('INSERT'),('UPDATE'),('REFERENCES')) AS p(priv)
     WHERE c.relname IN ('artifact_seal', 'secret_kek', 'secret_dek',
                         'secret_access_log', 'redaction_failure', 'seal_algorithms')
       AND has_column_privilege('rk2_state', c.oid, a.attnum, p.priv)

  UNION ALL
    -- 8. no key material in the database, wrapped or otherwise. 024 stored a
    --    wrapped data key per scope; this runtime derives the Program's key from
    --    the root secret and the generation's salt, so the row is unnecessary and
    --    its presence would mean something is keeping keys where dumps go.
    SELECT 'wrapped_key_material_present',
           d.scope_kind || ':' || d.scope_id::text,
           'a wrapped data key is stored; per-Program keys are derived, not kept'
      FROM secret_dek d
$$;

COMMENT ON FUNCTION check_wire_artifact_secrecy() IS
    'Ticket 07: credential-bearing artifacts are sealed, unreachable from any session, paired with a held agent-visible view, and backed by no key material inside the database.';

INSERT INTO standing_checks (name, query, owner_ticket, note) VALUES
    ('wire_artifact_secrecy', 'SELECT * FROM check_wire_artifact_secrecy()', 'ph2-07',
     'every credential-bearing artifact is sealed under a named construction, paired with the redacted view its Program holds, reachable from no session, and opened only with key material the database does not have');


-- ---------------------------------------------------------------------------
-- 6. Bring the invariants to true for the corpus as it stands
-- ---------------------------------------------------------------------------
-- Same shape as 06's file and for the same reasons: the two finalizers make this
-- file's new table real inside the transaction that declares it, and only this
-- file's own rule is asserted, because the corpus-wide assertion runs after the
-- finalizers and this is not the place for it.

SELECT apply_state_rls();
SELECT apply_state_grants();

DO $$
DECLARE n integer; v record;
BEGIN
    SELECT count(*) INTO n FROM check_wire_artifact_secrecy();
    IF n > 0 THEN
        FOR v IN SELECT * FROM check_wire_artifact_secrecy() LOOP
            RAISE WARNING 'wire artifact secrecy violation: % % %', v.problem, v.object, v.detail;
        END LOOP;
        RAISE EXCEPTION 'ph2-07 refuses to finish: % wire-artifact-secrecy violation(s)', n;
    END IF;
END $$;
