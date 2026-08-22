-- ---------------------------------------------------------------------------
-- 20261007T000000Z__a_run_registers_the_authority_it_is_intercepted_under.sql
--                                                                 (ticket 124)
--
-- 025 built `interception_cas` and nothing has ever put a row in it. Nine
-- columns, six named CHECKs, a partial unique index (`0025:506-507`) and a
-- purge edge (`:509-511`), every one of them an assertion about an empty table.
--
-- The consequence is one layer further on and is invisible for that reason.
-- `proxy.transport` leaves `agent_cert_sha256`, `agent_cert_issuer`,
-- `agent_cert_subject` and `agent_cert_not_after` null on every intercepted
-- exchange, and says why at the point of refusal: recording the leaf means
-- naming the forging key under `receipts_intercepted_leaf_names_ca`
-- (`0025:154-157`), and nothing writes the row that name would point at. That
-- constraint is what makes the door's silence mandatory rather than cautious --
-- an intercepted Receipt that names a leaf must name the CA that signed it --
-- so the four columns can never be filled while the table is empty. Which in
-- turn empties two arms of `check_transport_claims`: `unattributed_forged_leaf`
-- (`20260815T000000Z:2435-2440`) reports nothing, not because no leaf is
-- unattributed but because no leaf is recorded, and `expired_ca_still_current`
-- (`:2443-2447`) is empty because no CA is registered.
--
-- WHY A WRITER COULD NOT SIMPLY BE ADDED.
--
-- The CA 025 describes and the CA this harness makes are different objects, and
-- one constraint is where they collide. What ships is a per-run, on-disk root:
-- `tls.authority` makes it with `openssl req -x509`, writes the key into a
-- directory the door owns, gives it seven days, and hands the certificate to
-- children while the key is handed to nobody. Held against the table, three of
-- the four things that look like obstacles are not. `interception_cas_max_lifetime`
-- caps life at ninety days and seven passes. `program_id NOT NULL` and
-- `interception_cas_one_current` look wrong for an authority one door shares
-- across Programs and are not: the row states that *this Program's* flows were
-- intercepted under *that* key, so one authority is registered once per Program,
-- one row each, exactly one current. And `spki_sha256` is derivable without the
-- key, because the subject public key info comes out of the certificate.
--
-- The one that does block it is `interception_cas_secret_ref_shape CHECK
-- (secret_ref ~ '^(op://|kek:)')` on a NOT NULL column. The shipped key has no
-- secret reference of any kind -- it is a file in the door's own directory --
-- so there is no honest string to write, and writing an `op://` or a `kek:`
-- would be a lie about where key material lives, which is the exact thing that
-- CHECK and `interception_cas_no_key_material` exist to prevent. So this file
-- admits a third form: a CA whose key is held by the door and referenced
-- nowhere.
--
-- WHY NOT BUILD 025'S DESIGN INSTEAD.
--
-- 025's preamble (`:458-465`) sets up a choice between two ways of getting
-- ticket 15's KEK-held key to the proxy, and flags that "either the CA key
-- travels the runtime->proxy channel or 15's holder must be reachable from the
-- proxy. It must be the former". What shipped is a third option that preamble
-- did not consider, and it is better than either: the key is never in the
-- runtime, never in a message, never in a secret store, and never lives longer
-- than a week. `tls.py:55-57` states the property that would be given up --
-- "a trust root that outlives the run it was minted for is a trust root someone
-- still trusts after the door that owns its key has stopped answering" -- and
-- moving a CA private key through an IPC channel to lengthen its life to ninety
-- days is the wrong trade. The two constraints 025 wrote to keep key material
-- out of the database are satisfied more completely by what ships than by what
-- it anticipated, so 025's channel-delivery design is retired rather than built.
--
-- WHO WRITES THE ROW.
--
-- The runtime, not the door. The door holds the key and must not gain a grant
-- that lets it describe itself; the runtime already holds the CA *certificate*,
-- because every child it starts verifies every target against
-- `$RK_PROXY_CA_FILE`. Subject, `not_before`, `not_after` and the SPKI all come
-- out of that public half, so the write needs no key access at all -- which is
-- the property that makes it safe on the run-start path, and the reason
-- `register_interception_ca` is granted to `rk2_runtime` alone. `tls.registration`
-- is the reader that turns the certificate into the four facts, and
-- `tls.REGISTER` is the statement.
--
-- WHAT IS DELIBERATELY NOT HERE.
--
-- The agent's read surface does not move. Ten `interception_cas` columns are on
-- it already with `secret_ref` excluded, and `check_transport_claims` asserts
-- that exclusion (`20260815T000000Z:2472-2475`). Under the third form
-- `secret_ref` stops carrying a reference at all for door-held CAs, and the
-- exclusion still stands exactly as written: a column that may name a secret
-- store for some rows has to stay off the surface for all of them. Filling the
-- table makes nine of those ten columns real and leaves the tenth excluded.
--
-- `20260923T000000Z:406` is left as it is: a measurement Receipt sets
-- `interception_ca_id := NULL` on purpose, because a measurement the runtime
-- takes for itself is not intercepted and has no forging key to name.
--
-- No Event is emitted. `0030_corpus_corrections.sql:122` already exempts
-- `interception_cas` as a `reference` table -- "the CA set the proxy may
-- present, changed only by migration or operator" -- and a registration is
-- exactly that change.
--
-- Depends on 0002 (`next_label`), 0015 (`label_prefixes`, `free_label`), 0025
-- (the table, the constraint being replaced, the partial index) and
-- 20260909T000000Z (`runtime_verb_surface`, and the rule that a grant to
-- `rk2_runtime` is declared or it is a leak).
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- 1. The shape rule admits a third form
-- ===========================================================================

-- Dropped and re-added rather than widened in place, because a CHECK has no
-- ALTER. The two forms 025 wrote are kept letter for letter: an installation
-- that does hold its CA key behind ticket 15 still writes `op://` or `kek:`,
-- and this file takes nothing away from that. What is added is the case 025
-- ruled out by assuming there were only two -- a key that is in no store at all
-- because it is a file in a directory that dies with the run.
ALTER TABLE interception_cas
    DROP CONSTRAINT interception_cas_secret_ref_shape,
    ADD  CONSTRAINT interception_cas_secret_ref_shape CHECK (
        secret_ref ~ '^(op://|kek:|door:)');

-- The reason, where a reader of the live schema will find it. The original is a
-- `--` comment inside a recorded migration file, which cannot be edited, so the
-- rule now says why it is three rather than why it was two. G8: the file that
-- moves a constraint on a column re-issues that column's comment.
COMMENT ON COLUMN interception_cas.secret_ref IS
 'Where the private half of this CA is held, in three forms and no others. `op://` and `kek:` are ticket 15''s: the key is in the secret store, and anything else in that shape would mean somebody built a second one. `door:` is the third and it is not a reference -- it says the key is a file in the directory the door minted it into, handed to nobody, never in this database and never in any store, and gone when the run is. A door-held CA has no recoverable key by construction, which is the strongest form of the promise the other two make by policy. This column is off the agent''s read surface for every row whatever it holds, because a column that may name a secret store for some rows has to stay off it for all of them; check_transport_claims asserts that.';


-- ===========================================================================
-- 2. A CA gets a label the same way everything else does
-- ===========================================================================

-- `interception_cas.label` is NOT NULL and unique per Program, and 015 already
-- owns how a per-Program name is minted. Registering a prefix rather than
-- deriving a name from the digest means a rotation cannot collide with the CA
-- it replaced: `free_label` walks past a label already taken, and a digest-shaped
-- name would not.
INSERT INTO label_prefixes (kind, prefix) VALUES ('interception_cas', 'CA');


-- ===========================================================================
-- 3. Registering one
-- ===========================================================================

-- Called by the runtime at the point a Program first has a door to intercept
-- with, and idempotent from the second call onwards, because that point is
-- reached once per pass and a run makes many. Same key, same row: the authority
-- is reused across restarts for as long as it is current -- which is what
-- `tls.authority` does and why it does it -- so a second registration of the
-- same SPKI is the same fact arriving again and not a rotation.
--
-- A different SPKI is a rotation, and rotation here is 025's order rather than
-- this function's invention: retire, then issue, then record the supersession.
-- The two steps never overlap, so no Program ever has two live forging keys,
-- which is what `interception_cas_one_current` enforces and what makes the
-- chain in `superseded_by` readable backwards from a Receipt older than the
-- rotation.
--
-- Every refusal names the rule it broke. The CHECKs on the table would each
-- refuse the same row, but as a constraint violation naming a column rather
-- than as a sentence naming the reason, and a function that refuses anonymously
-- is the thing 078 wrote `open_fixture_address` to avoid.
CREATE FUNCTION register_interception_ca(
    p_program    uuid,
    p_subject    text,
    p_spki       text,
    p_not_before timestamptz,
    p_not_after  timestamptz
) RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    v_spki    text;
    v_current interception_cas%ROWTYPE;
    v_id      uuid;
BEGIN
    PERFORM 1 FROM programs p WHERE p.id = p_program;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'program % does not exist, so nothing of it was intercepted',
            p_program USING ERRCODE = '23514';
    END IF;

    IF p_subject IS NULL OR btrim(p_subject) = '' THEN
        RAISE EXCEPTION 'a CA registration states no subject'
          USING HINT = 'the subject is the certificate''s own, and it is what a '
                       'reader compares against receipts.agent_cert_issuer',
                ERRCODE = '23514';
    END IF;

    -- Lower-cased rather than refused for case: the digest is the same fact
    -- either way and the column pattern is the lower-case one. What is refused
    -- is a value that is not a SHA-256 at all.
    v_spki := lower(coalesce(p_spki, ''));
    IF v_spki !~ '^[0-9a-f]{64}$' THEN
        RAISE EXCEPTION 'a CA registration states no subject public key digest: %',
            coalesce(p_spki, '<null>')
          USING HINT = 'spki_sha256 is the SHA-256 of the DER subject public key '
                       'info, in hex, and it comes out of the certificate',
                ERRCODE = '23514';
    END IF;

    IF p_not_before IS NULL OR p_not_after IS NULL OR p_not_after <= p_not_before THEN
        RAISE EXCEPTION 'a CA registration states no window it is valid in'
          USING ERRCODE = '23514';
    END IF;
    IF p_not_after > p_not_before + interval '90 days' THEN
        RAISE EXCEPTION 'a CA valid from % to % outlives the ninety days one program may intercept under one key',
            p_not_before, p_not_after
          USING DETAIL = 'a CA that outlives the program it was minted for is the '
                         'per-installation failure mode by another name',
                ERRCODE = '23514';
    END IF;

    -- Read into a row variable rather than tested with FOUND, because FOUND is
    -- reassigned by every statement below it and the question "was there a
    -- current CA" is asked again after two writes have moved it.
    SELECT * INTO v_current FROM interception_cas c
     WHERE c.program_id = p_program AND c.retired_at IS NULL;

    -- The same authority arriving again. Answered with the row that is already
    -- there rather than with a second one: a run that registered its CA on
    -- every pass would retire and supersede a key nothing rotated, and the
    -- chain would record a rotation that never happened.
    IF v_current.spki_sha256 = v_spki THEN
        RETURN v_current.id;
    END IF;

    IF v_current.id IS NOT NULL THEN
        UPDATE interception_cas SET retired_at = now() WHERE id = v_current.id;
    END IF;

    INSERT INTO interception_cas
        (program_id, label, subject, spki_sha256, not_before, not_after, secret_ref)
    VALUES (p_program,
            free_label(p_program, 'interception_cas', 'interception_cas'),
            p_subject, v_spki, p_not_before, p_not_after, 'door:no-reference')
    RETURNING id INTO v_id;

    -- Last, because the foreign key on (program_id, superseded_by) needs the
    -- row it points at to exist and `interception_cas_supersede_needs_retire`
    -- needs the retirement above to have happened.
    IF v_current.id IS NOT NULL THEN
        UPDATE interception_cas SET superseded_by = v_id WHERE id = v_current.id;
    END IF;

    RETURN v_id;
END $fn$;

COMMENT ON FUNCTION register_interception_ca(uuid, text, text, timestamptz, timestamptz) IS
 'Records the authority one Program''s flows are intercepted under, from the '
 'public half of the door''s certificate and nothing else. Idempotent for the CA '
 'that is already current; a different subject public key is a rotation, and is '
 'retired-then-issued in that order so no Program ever has two live forging '
 'keys. Writes the door-held form of secret_ref, because the key is a file the '
 'door owns and no reference to it exists anywhere.';


-- ===========================================================================
-- 4. Who may call it
-- ===========================================================================

-- The runtime and nobody else. The door is the party that holds the signing
-- key, and a door that could also write the row describing that key would be a
-- door that attributes its own forgeries -- so `rk2_proxy` is not given this.
-- That the registration needs no key access at all is what makes putting it on
-- the runtime side possible rather than merely preferable.
REVOKE ALL ON FUNCTION
    register_interception_ca(uuid, text, text, timestamptz, timestamptz) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION
    register_interception_ca(uuid, text, text, timestamptz, timestamptz) TO rk2_runtime;

INSERT INTO runtime_verb_surface (verb, added_by, note) VALUES
    ('register_interception_ca(uuid, text, text, timestamp with time zone, timestamp with time zone)',
     '124',
     'records the authority a Program''s flows are intercepted under, from the CA certificate the runtime was told to trust; the row an intercepted Receipt''s leaf is attributed to');


-- ===========================================================================
-- 5. What this file claims, asserted
-- ===========================================================================

-- The static half: the constraint, the comment the G8 rule owes, and the two
-- halves of the grant that have to be written in one file or drift apart in
-- two.
DO $$
DECLARE
    v_definition text;
    v_comment    text;
BEGIN
    SELECT pg_get_constraintdef(oid) INTO v_definition
      FROM pg_constraint
     WHERE conrelid = 'interception_cas'::regclass
       AND conname = 'interception_cas_secret_ref_shape';
    IF v_definition IS NULL OR v_definition NOT LIKE '%door:%' THEN
        RAISE EXCEPTION 'the shape rule still refuses a CA whose key the door holds: %',
            coalesce(v_definition, 'the constraint is gone');
    END IF;
    IF v_definition NOT LIKE '%op://%' OR v_definition NOT LIKE '%kek:%' THEN
        RAISE EXCEPTION 'the shape rule stopped admitting ticket 15''s own forms: %',
            v_definition;
    END IF;

    SELECT col_description('interception_cas'::regclass, a.attnum) INTO v_comment
      FROM pg_attribute a
     WHERE a.attrelid = 'interception_cas'::regclass AND a.attname = 'secret_ref';
    IF v_comment IS NULL OR v_comment NOT LIKE '%door:%' THEN
        RAISE EXCEPTION 'secret_ref carries no live comment naming the third form';
    END IF;

    IF NOT has_function_privilege('rk2_runtime',
            'register_interception_ca(uuid,text,text,timestamptz,timestamptz)', 'EXECUTE') THEN
        RAISE EXCEPTION 'rk2_runtime cannot register an interception CA; nothing would write the row';
    END IF;
    IF has_function_privilege('rk2_proxy',
            'register_interception_ca(uuid,text,text,timestamptz,timestamptz)', 'EXECUTE') THEN
        RAISE EXCEPTION 'rk2_proxy can register an interception CA; the door would be '
                        'describing the key it forges with';
    END IF;
    IF EXISTS (SELECT 1 FROM check_runtime_privileges()
                WHERE problem = 'runtime_holds_undeclared_verb') THEN
        RAISE EXCEPTION 'the runtime holds a verb no runtime_verb_surface row declares';
    END IF;
END $$;


-- The lifecycle, against a Program this block rolls back. Asserted rather than
-- described, because every sentence in section 3 is about an order of writes
-- and an order is the one thing prose cannot hold to.
DO $$
DECLARE
    v_program uuid;
    v_first   uuid;
    v_again   uuid;
    v_second  uuid;
    v_row     interception_cas%ROWTYPE;
BEGIN
    BEGIN
        INSERT INTO programs (slug, name) VALUES ('ticket-124-proof', 'ticket 124 proof')
        RETURNING id INTO v_program;

        v_first := register_interception_ca(
            v_program, 'commonName=redKraken run authority', repeat('a', 64),
            now() - interval '1 hour', now() + interval '7 days');

        -- The same key, spelled the other way. Two facts in one call: a second
        -- registration is the same row, and the digest is a digest whatever
        -- case it arrives in.
        v_again := register_interception_ca(
            v_program, 'commonName=redKraken run authority', repeat('A', 64),
            now() - interval '1 hour', now() + interval '7 days');
        IF v_again IS DISTINCT FROM v_first THEN
            RAISE EXCEPTION 'the same authority registered twice made two rows; a run '
                            'would rotate its own key on every pass';
        END IF;

        v_second := register_interception_ca(
            v_program, 'commonName=redKraken run authority', repeat('b', 64),
            now(), now() + interval '7 days');
        IF v_second = v_first THEN
            RAISE EXCEPTION 'a different forging key was recorded as the same CA';
        END IF;

        SELECT * INTO v_row FROM interception_cas WHERE id = v_first;
        IF v_row.retired_at IS NULL OR v_row.superseded_by IS DISTINCT FROM v_second THEN
            RAISE EXCEPTION 'the superseded CA is not retired and pointed at its successor';
        END IF;

        SELECT * INTO v_row FROM interception_cas WHERE id = v_second;
        IF v_row.secret_ref !~ '^door:' OR v_row.label !~ '^CA[0-9]+$' THEN
            RAISE EXCEPTION 'a registered CA carries neither the door-held form nor a CA label: % / %',
                v_row.secret_ref, v_row.label;
        END IF;

        IF (SELECT count(*) FROM interception_cas
             WHERE program_id = v_program AND retired_at IS NULL) <> 1 THEN
            RAISE EXCEPTION 'a rotation left the program with something other than one current CA';
        END IF;

        -- The two arms that were empty because the table was. Neither may fire
        -- for what this block just wrote: the current CA is inside its window,
        -- and no Receipt was touched at all.
        IF EXISTS (SELECT 1 FROM check_transport_claims(v_program)
                    WHERE problem IN ('expired_ca_still_current', 'unattributed_forged_leaf')) THEN
            RAISE EXCEPTION 'registering a live CA made check_transport_claims report one';
        END IF;

        -- And the defence the third form is most likely to have weakened. The
        -- refusal here is a check violation, so the raise that would mean it
        -- did not happen must not be one, or it would be caught as the pass.
        BEGIN
            INSERT INTO interception_cas
                (program_id, label, subject, spki_sha256, not_before, not_after, secret_ref)
            VALUES (v_program, 'CA-leak', 'commonName=leak', repeat('c', 64),
                    now(), now() + interval '1 day',
                    'door:-----BEGIN PRIVATE KEY-----');
            RAISE EXCEPTION 'the door-held form admits key material';
        EXCEPTION WHEN check_violation THEN
            NULL;
        END;

        RAISE EXCEPTION 'ticket 124 proof' USING ERRCODE = 'RK124';
    EXCEPTION WHEN SQLSTATE 'RK124' THEN
        NULL;
    END;
END $$;
