-- ---------------------------------------------------------------------------
-- 20260922T060000Z__a_fixture_may_own_its_own_handshake.sql
--                                                                   (ticket 88)
--
-- `playbooks/http-desync` declares `transport.tls_configuration` as its only
-- output and no fixture in the corpus declared that class, so
-- `playbook_fixture_binding` yielded an empty in-pair side and
-- `playbook_test_verdict` stopped at `untested` for it on every run ticket 84's
-- campaign could spend. Ticket 64's final review recorded that as
-- `one-playbook-has-no-fixture-to-be-graded-against`; this is the fixture that
-- closes it, and the one schema rule that had to move for the fixture to be
-- reachable.
--
-- The rule that moved is the protocol. Every fixture before this one is an
-- `app.py` defining `handler(variant)` and is served over cleartext, because
-- every class before this one is settled by what came back. This class is not
-- settled by what came back at all: 025 records it as `probe_only` over
-- `tls_version`, `cipher` and `alpn`, and not one of those three is a thing a
-- request handler can write. So `tls-configuration-pair/app.py` defines a
-- second entry point, `tls(variant, context)`, which configures the socket the
-- handler is served over -- the bytes are the application's and the handshake
-- is the front end's, which is the class's own division. `evaluation.served`
-- wraps the socket when that entry point is there and leaves it alone when it
-- is not, so the scheme is a property of the fixture rather than a mode the
-- evaluator is put into.
--
-- `fixture_addresses.protocol` therefore admits `https`. It said `http` and
-- nothing else, with a comment giving the reason -- "a fixture is served by
-- `evaluation.served` over plain HTTP; a second spelling here would be a claim
-- about a listener nothing starts". That reason was true and is now not: this
-- migration ships the listener. Both spellings are still closed, because the
-- fixture address is what the door dials and a third scheme would be a claim
-- about a listener that still does not exist.
--
-- What this migration does not do is make the measurement admissible.
-- `receipts.transport_citable` is generated over
-- `purpose = 'transport_measurement'` and the two wire verification columns,
-- and no Python writer sets `purpose` at all -- 021 gives it a default of
-- `target_traffic` and nothing moves it.
-- The evaluator mints the fixture's authority per run and hands nobody its
-- root, so an exchange with this fixture is recorded unverified, which is what
-- it is. Ticket 93 owns that lane. The binding this migration opens is real and
-- the verdict it reaches is real; the citable transport measurement is a
-- separate piece of work and is named as one.
--
-- A new file rather than an edit to an earlier one: a recorded migration whose
-- file has changed is schema drift and `rk db migrate` refuses the whole corpus
-- for it.
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- 1. The fixture, as a row
-- ===========================================================================

-- Both digests, for 050's reason: `source_sha256` is what was served and
-- `ground_truth_sha256` is how it was graded, and they move separately. An edit
-- to either without an edit to a migration is drift, and the catalogue test in
-- `tests/test_database.py` is what catches it.
INSERT INTO fixtures (id, kind, path, source_sha256, ground_truth_sha256) VALUES
 ('tls-configuration-pair', 'own_pair',
  'fixtures/tls-configuration-pair/fixture.md',
  'c6d9f51b9264d16ac7585b9a99760088feb388a4ce0f547af827551d7c79b91c',
  '91eb385da15616236ef01a8b4a4a1b47884de43a776df473a75ec015aa7c8737')
ON CONFLICT (id) DO UPDATE SET
    kind                = excluded.kind,
    path                = excluded.path,
    source_sha256       = excluded.source_sha256,
    ground_truth_sha256 = excluded.ground_truth_sha256;


-- ===========================================================================
-- 2. One class
-- ===========================================================================

-- One, for 050's reason: a fixture claiming two classes cannot say which of
-- them a Playbook that fired on it read. The document argues in its own words
-- why the three neighbouring transport classes are not merely absent from this
-- ground truth but could not be true of what it serves -- the advertisement is
-- identical on both halves, both halves present the same certificate from the
-- same authority, and neither frames a request differently from the other.
INSERT INTO fixture_classes (fixture_id, property_class) VALUES
 ('tls-configuration-pair', 'transport.tls_configuration')
ON CONFLICT (fixture_id, property_class) DO NOTHING;


-- ===========================================================================
-- 3. A fixture address may name the scheme its fixture actually serves
-- ===========================================================================

-- 078 wrote this as `CHECK (protocol = 'http')` because that was the only thing
-- `evaluation.served` served. The constraint is replaced rather than dropped:
-- the closed set is the point of it, and a fixture address whose scheme is
-- neither of the two the evaluator can bind is a row the door would dial into
-- nothing.
ALTER TABLE fixture_addresses DROP CONSTRAINT fixture_addresses_protocol_check;

ALTER TABLE fixture_addresses
    ADD CONSTRAINT fixture_addresses_protocol_check
    CHECK (protocol IN ('http', 'https'));

-- The reason, where a reader of the live schema will find it. The original is a
-- `--` comment inside a recorded migration file, which cannot be edited, so the
-- rule now says why it is two rather than why it was one.
COMMENT ON COLUMN fixture_addresses.protocol IS
 'The scheme `evaluation.served` actually bound this fixture on, and the scheme the door will be asked about. Two spellings and no more: a fixture whose `app.py` defines `tls(variant, context)` is served over `https` and every other fixture is served over `http`, and a third spelling would be a claim about a listener nothing starts.';


-- ===========================================================================
-- 4. And the opener has to admit the same two
-- ===========================================================================

-- Replaced for one clause. The constraint above would refuse an `https` row on
-- its own, but the refusal would arrive as a check violation naming a column
-- rather than as this function's own sentence naming the rule -- and this
-- function refusing anonymously is the thing 078 wrote it to avoid.
CREATE OR REPLACE FUNCTION open_fixture_address(
    p_program  uuid,
    p_protocol text,
    p_host     text,
    p_port     integer,
    p_address  text
) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    v_version integer;
    v_host    text;
    v_address inet;
    v_class   text;
BEGIN
    PERFORM 1 FROM evaluation_programs e WHERE e.program_id = p_program;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'program % is not marked as an evaluation', p_program
          USING HINT = 'mark it in evaluation_programs first; a fixture address '
                       'belongs to a Program that exists to grade a Playbook',
                ERRCODE = '23514';
    END IF;

    IF p_protocol IS NULL OR p_protocol NOT IN ('http', 'https') THEN
        RAISE EXCEPTION 'a fixture is served over http or https, not %',
            coalesce(p_protocol, '<null>') USING ERRCODE = '23514';
    END IF;
    IF p_port IS NULL OR p_port < 1 OR p_port > 65535 THEN
        RAISE EXCEPTION 'a fixture address states no port in 1-65535'
            USING ERRCODE = '23514';
    END IF;

    -- The policy's own spelling of the name, so that what is stored is what
    -- `authorize_fixture_address` will be asked about: the door canonicalises
    -- the request and this function canonicalises the fixture address, and two
    -- normalisers over one name is the differential this schema keeps avoiding.
    v_host := scope_normalize_host(p_host);
    IF v_host IS NULL THEN
        RAISE EXCEPTION 'a fixture address states no host' USING ERRCODE = '23514';
    END IF;

    BEGIN
        v_address := p_address::inet;
    EXCEPTION WHEN invalid_text_representation THEN
        RAISE EXCEPTION 'a fixture address states no address: %',
            coalesce(p_address, '<null>') USING ERRCODE = '23514';
    END;

    SELECT p.scope_version INTO v_version FROM programs p WHERE p.id = p_program;
    IF v_version IS NULL THEN
        RAISE EXCEPTION 'program % has no compiled scope to check a fixture address against',
            p_program USING ERRCODE = '23514';
    END IF;

    -- The coverage question, the same one `authorize_egress_address` asks: this
    -- is about the machine the fixture is on, not about a path. `target` and
    -- nothing weaker -- an `egress_support` host is somewhere the harness may
    -- talk to on its own business, and a Playbook is not graded against one.
    SELECT s.scope_class INTO v_class
      FROM scope_class_of(p_program, v_version, v_host, p_port,
                          '/', '/', p_protocol, 'coverage') s;
    IF coalesce(v_class, 'denied') <> 'target' THEN
        RAISE EXCEPTION 'the scope of program % does not class %:% as a target',
            p_program, v_host, p_port
          USING DETAIL = 'a fixture address changes the address a target is dialled at; '
                         'it does not make something a target',
                ERRCODE = '23514';
    END IF;

    INSERT INTO fixture_addresses (program_id, protocol, host, port, address)
    VALUES (p_program, p_protocol, v_host, p_port, v_address);
END $fn$;

COMMENT ON FUNCTION open_fixture_address(uuid, text, text, integer, text) IS
 'Records where an evaluation Program''s fixture is listening, on the scheme it '
 'was actually bound on. Refuses a Program that is not an evaluation, a scheme '
 'that is neither http nor https, a host its own policy does not class as a '
 'target, and any address that is not one private host on this machine.';


-- ===========================================================================
-- 5. The four things this migration claims, asserted
-- ===========================================================================

DO $$
DECLARE n integer;
BEGIN
    SELECT count(*) INTO n FROM fixtures
     WHERE id = 'tls-configuration-pair'
       AND source_sha256 = 'c6d9f51b9264d16ac7585b9a99760088feb388a4ce0f547af827551d7c79b91c'
       AND ground_truth_sha256 = '91eb385da15616236ef01a8b4a4a1b47884de43a776df473a75ec015aa7c8737';
    IF n <> 1 THEN
        RAISE EXCEPTION 'ticket 88: the tls-configuration-pair row is not its digests';
    END IF;

    SELECT count(*) INTO n FROM fixture_classes
     WHERE fixture_id = 'tls-configuration-pair'
       AND property_class = 'transport.tls_configuration';
    IF n <> 1 THEN
        RAISE EXCEPTION 'ticket 88: tls-configuration-pair declares no class';
    END IF;

    -- The binding is not asked here, and the reason is worth writing down: it is
    -- derived from `playbook_outputs` against `fixture_classes`, and the
    -- Playbook catalogue is loaded by the runtime rather than by a migration, so
    -- at this point `playbooks` is empty and the question has no answer yet
    -- rather than a false one. `PlaybookEvaluationTest` asks it where the
    -- catalogue exists.

    -- The kind, because `playbook_test_verdict` counts own pairs and nothing
    -- else on the `in` side: a third-party fixture can fail a Playbook and can
    -- never satisfy it, so a fixture registered under the wrong kind would leave
    -- the verdict exactly where this migration found it.
    SELECT count(*) INTO n FROM fixtures
     WHERE id = 'tls-configuration-pair' AND kind = 'own_pair';
    IF n <> 1 THEN
        RAISE EXCEPTION 'ticket 88: tls-configuration-pair is not an own pair';
    END IF;

    -- And the scheme the fixture address may name.
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'fixture_addresses'::regclass
           AND conname = 'fixture_addresses_protocol_check'
           AND pg_get_constraintdef(oid) LIKE '%https%'
    ) THEN
        RAISE EXCEPTION 'ticket 88: fixture_addresses still refuses https';
    END IF;
END $$;
