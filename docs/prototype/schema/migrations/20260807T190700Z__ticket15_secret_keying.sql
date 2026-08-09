-- 024_secret_keying.sql  --  ticket 15, the secret encryption scheme.
--
-- Self-contained: applies to an empty database (its own fixtures) and to the
-- consolidated ticket-33 baseline.  Foreign keys to `programs`, `identities`
-- and `artifacts` are added only if those tables already exist, so this file is
-- order-independent with respect to migrations 001-023.
--
-- Nothing in here is secret.  Salts and generation numbers are public by
-- construction; the only key material stored is a DEK *wrapped* under a KEK
-- that is never persisted anywhere on this host.

-- [ticket 33 consolidation] BEGIN;/COMMIT; removed: ./migrate.sh wraps every
-- migration in one transaction with its rk2_meta.schema_migrations row, and an
-- inner COMMIT would end that transaction early. Refused by ./migrate.sh lint.

-- ---------------------------------------------------------------------------
-- KEK generations.
--
-- KEK_g = HKDF-SHA256(ikm = root_secret, salt = salt, info = 'rk2/kek/v1|gen=g')
--
-- The root secret lives only in 1Password
-- (op://BugBounty Static/Harness Credential Encryption Key/password) and, for
-- the lifetime of an engagement, in the keyholder process.  Rotating the KEK is
-- inserting a row: every earlier generation stays derivable from the same root
-- secret, so no ciphertext has to be rewritten.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS secret_kek (
    gen         integer PRIMARY KEY CHECK (gen >= 1),
    salt        bytea   NOT NULL CHECK (octet_length(salt) = 32),
    -- HMAC-SHA256(KEK_g, 'rk2/rootcheck/v1') truncated to 16 bytes.  Lets
    -- startup prove it read the right root secret without decrypting anything
    -- and without ever comparing key material.
    root_check  bytea   NOT NULL CHECK (octet_length(root_check) = 16),
    created_at  timestamptz NOT NULL DEFAULT now(),
    retired_at  timestamptz,
    CHECK (retired_at IS NULL OR retired_at >= created_at)
);

-- Exactly one generation is current.
CREATE UNIQUE INDEX IF NOT EXISTS secret_kek_current_idx
    ON secret_kek ((true)) WHERE retired_at IS NULL;

-- ---------------------------------------------------------------------------
-- Wrapped DEKs.  One per (scope_kind, scope_id, dek_gen).
--
-- scope_kind is the deletion granularity, and that is the only thing that
-- decides it:
--   'engagement' - the run itself; ephemeral working material.
--   'program'    - every credential-bearing artifact of one bug-bounty program.
--                  Deleting this row crypto-shreds the whole program at once.
--   'identity'   - one identity's cookie jar, headers, password material.
--                  Deleting this row shreds one identity, leaving the rest of
--                  the program readable.
--   'rootcheck'  - the startup self-test item.
--
-- There is deliberately no per-artifact DEK: artifacts number in the millions,
-- clean deletion is required per program and per identity, and a per-artifact
-- key would add a row and a wrap per artifact while buying no deletion
-- granularity anyone asked for.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS secret_dek (
    scope_kind  text    NOT NULL CHECK (scope_kind IN
                          ('rootcheck','engagement','program','identity')),
    scope_id    uuid    NOT NULL,
    dek_gen     integer NOT NULL CHECK (dek_gen >= 1),
    kek_gen     integer NOT NULL REFERENCES secret_kek(gen),
    -- AES-256-GCM(KEK_g) over the 32-byte DEK: nonce(12) || ct(32) || tag(16).
    wrapped     bytea   NOT NULL CHECK (octet_length(wrapped) = 60),
    -- AES-GCM with random 96-bit nonces needs a message cap.  Reaching it rolls
    -- the DEK (dek_gen + 1) rather than risking a nonce collision.
    seal_count  bigint  NOT NULL DEFAULT 0 CHECK (seal_count >= 0),
    seal_cap    bigint  NOT NULL DEFAULT 4294967296 CHECK (seal_cap > 0),
    created_at  timestamptz NOT NULL DEFAULT now(),
    retired_at  timestamptz,
    PRIMARY KEY (scope_kind, scope_id, dek_gen),
    CHECK (seal_count <= seal_cap)
);

-- One live DEK per scope.
CREATE UNIQUE INDEX IF NOT EXISTS secret_dek_current_idx
    ON secret_dek (scope_kind, scope_id) WHERE retired_at IS NULL;

-- ---------------------------------------------------------------------------
-- Which DEK scope owns a sealed artifact blob.
--
-- The artifact store is content-addressed and the filename is the PLAINTEXT
-- hash (ticket 06, decision 14), so one blob can be produced by two programs.
-- With a single global key that is harmless dedup.  With per-program keys it is
-- a hazard: purging program A would shred evidence program B still references.
-- This table makes the case impossible to hit silently - a second scope sealing
-- an already-sealed hash is REFUSED and receipted, not deduped.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS artifact_seal (
    sha256      text    PRIMARY KEY CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    scope_kind  text    NOT NULL CHECK (scope_kind IN ('program','identity','engagement')),
    scope_id    uuid    NOT NULL,
    visibility  text    NOT NULL CHECK (visibility IN ('agent_visible','credential_bearing')),
    byte_size   bigint  NOT NULL CHECK (byte_size >= 0),
    sealed_at   timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- Audit.  Written on every keyholder verb, including refusals.
--
-- Never the value.  `value_fpr` is HMAC-SHA256(audit_key, value) truncated to
-- 4 bytes, where audit_key = HKDF(root_secret, info='rk2/audit-fp/v1').  A
-- plain SHA-256 prefix would be offline-brute-forceable for a short password;
-- a keyed fingerprint is not, and still answers "is the value used here the
-- same one used there".
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS secret_access_log (
    id           bigserial PRIMARY KEY,
    at           timestamptz NOT NULL DEFAULT now(),
    verb         text NOT NULL CHECK (verb IN
                    ('derive_kek','new_dek','unwrap_dek','rewrap_dek','retire_dek',
                     'seal','open','open_identity','shred','rootcheck')),
    scope_kind   text,
    scope_id     uuid,
    dek_gen      integer,
    kek_gen      integer,
    -- Who asked.  The keyholder reads these off SO_PEERCRED; a caller cannot
    -- forge them.
    peer_pid     integer,
    peer_uid     integer,
    peer_exe     text,
    program_id   uuid,
    tool_run_id  uuid,
    receipt_id   uuid,
    field        text,          -- 'cookie_jar', 'authorization', ...
    value_len    integer CHECK (value_len IS NULL OR value_len >= 0),
    value_fpr    bytea   CHECK (value_fpr IS NULL OR octet_length(value_fpr) = 4),
    outcome      text NOT NULL CHECK (outcome IN ('ok','denied','shredded','error')),
    detail       text
);

CREATE INDEX IF NOT EXISTS secret_access_log_scope_idx
    ON secret_access_log (scope_kind, scope_id, at DESC);

-- ---------------------------------------------------------------------------
-- Redaction failures.  A redaction that fails open is worse than none, so the
-- projection is withheld and the failure is a row here, not a log line.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS redaction_failure (
    id            bigserial PRIMARY KEY,
    at            timestamptz NOT NULL DEFAULT now(),
    artifact_sha  text CHECK (artifact_sha IS NULL OR artifact_sha ~ '^[0-9a-f]{64}$'),
    rule_id       text NOT NULL,      -- which verifier tripped
    encoding_path text NOT NULL,      -- 'raw', 'urldecode', 'base64>urldecode', ...
    -- Never the matched text.  Offset + length + keyed fingerprint is enough to
    -- find the bug and not enough to reconstruct the value.
    match_offset  integer NOT NULL,
    match_len     integer NOT NULL,
    value_fpr     bytea CHECK (value_fpr IS NULL OR octet_length(value_fpr) = 4)
);

-- ---------------------------------------------------------------------------
-- Consolidation hooks (ticket 33).  No-ops on a standalone fixture database.
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF to_regclass('public.programs') IS NOT NULL THEN
        ALTER TABLE secret_access_log
            ADD CONSTRAINT secret_access_log_program_fk
            FOREIGN KEY (program_id) REFERENCES programs(id) ON DELETE SET NULL;
    END IF;
    IF to_regclass('public.artifacts') IS NOT NULL THEN
        ALTER TABLE artifact_seal
            ADD CONSTRAINT artifact_seal_sha_fk
            FOREIGN KEY (sha256) REFERENCES artifacts(sha256) ON DELETE CASCADE;
        ALTER TABLE redaction_failure
            ADD CONSTRAINT redaction_failure_sha_fk
            FOREIGN KEY (artifact_sha) REFERENCES artifacts(sha256) ON DELETE SET NULL;
    END IF;
EXCEPTION WHEN duplicate_object THEN
    NULL;
END $$;

