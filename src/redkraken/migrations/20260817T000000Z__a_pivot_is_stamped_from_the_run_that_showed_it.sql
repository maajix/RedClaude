-- ---------------------------------------------------------------------------
-- 20260817T000000Z__a_pivot_is_stamped_from_the_run_that_showed_it.sql  (39)
-- ---------------------------------------------------------------------------
--
--   A chain is the most rhetorical thing a hunter writes. "This SSRF reaches
--   the metadata service, so we have credentials, so we have the bucket" is
--   three claims of which one was tested, and the word that carries the other
--   two is "so". This ticket is about that word. A pivot is not a sentence
--   joining two Findings; it is a capability a run was seen to obtain, and the
--   stamp is the runtime's record that it saw it.
--
--   The shape, and why it is this shape:
--
--    * The claim is written before the run, not after it. It lives in the Test
--      specification, which 035 made immutable and digested and 038 made the
--      thing an operator's grant is about. A pivot claim authored beside a
--      finished run is a claim fitted to its answer; a pivot claim in the spec
--      is a prediction, and the run either bears it out or does not.
--
--    * The demonstrating run is an impact run. A transition that hands you a
--      capability you did not have is `read_other_data`, `write_target_state`
--      or `escalate_privilege` -- it is impact, and 038 already says impact
--      needs its own authorized Test. Reusing that verb rather than inventing
--      a second one is what makes criterion 3's grant recheck a real question:
--      there is a grant, it names this Test, and it can expire.
--
--    * "Demonstrates the transition rather than merely the member
--      vulnerability" is a structural question, so it gets a structural
--      answer. The named assertion has to have held, and the request it reads
--      has to be one the member Finding's own validating Test never made. A
--      pivot whose transition is a route the member was already validated on
--      demonstrates the member a second time and nothing else.
--
--    * The Identity is read off the Receipt, not off the claim. The claim
--      names a slot; the door recorded which Identity actually went out on the
--      transition request. When they differ the claim is wrong, and that is a
--      refusal rather than something to reconcile.
--
--    * Idempotence is a hash, not a flag. Everything the stamp rests on goes
--      into one canonical object -- member, its validation, subject, Identity,
--      Test, spec digest, run, capabilities, conditions, scope version and the
--      capability vocabulary itself -- and the digest of that object is the
--      stamp's identity. Issuing twice from unchanged evidence finds the row
--      already there; anything that moves underneath produces a different
--      digest, which is a different stamp.

-- ===========================================================================
-- 1. What a capability is
-- ===========================================================================
--
-- Criterion 1 asks a pivot to name "required capabilities" and a "provided
-- capability", and criterion 4 asks the stamp to record the vocabulary. Both
-- want the same thing: a closed list, owned by migrations, that two hunters
-- cannot spell two ways. `session` and `authenticated_session` are one
-- capability to their authors and two to anything counting.
--
-- Ten words, and none of them names a weakness. 007 owns the property class,
-- which is what a Finding is *about*, and 018 owns the vulnerability class,
-- which is what it *is*. This is the third question neither of them answers:
-- what holding it *gets you*, which is the only thing a chain composes over.

CREATE TABLE capabilities (
    capability  text PRIMARY KEY CHECK (capability ~ '^[a-z][a-z0-9_]{2,40}$'),
    description text NOT NULL CHECK (btrim(description) <> '')
);

COMMENT ON TABLE capabilities IS
  'Ticket 39: the closed vocabulary a pivot is stated in. What holding a position gets you, as distinct from what a Finding is about, which is a property class, and from what is wrong with the target, which is a vulnerability class.';

INSERT INTO capabilities (capability, description) VALUES
    ('anonymous_reach',       'reach the surface holding no credential at all'),
    ('authenticated_session', 'hold a session the target issued to some account'),
    ('other_account_data',    'read data the target holds for another account or tenant'),
    ('other_account_control', 'act as another account against the target'),
    ('privileged_role',       'hold a role the target treats as administrative'),
    ('credential_material',   'hold a secret the target issued or stored'),
    ('arbitrary_read',        'read objects or files the target did not mean to serve'),
    ('arbitrary_write',       'write objects or files the target did not mean to accept'),
    ('internal_network_reach','reach a host only the target can reach'),
    ('code_execution',        'run code on a host the target runs on');

-- Reference data, per 027: changed only by a migration, and every stamp says
-- which version of it was in force when it was issued.
INSERT INTO program_global_tables (table_name, reason) VALUES
    ('capabilities', 'the capability vocabulary; a pivot in one Program means what it means in every Program');

INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('capabilities', 'reference',
     'the capability vocabulary, changed only by migration', '39');

GRANT SELECT ON capabilities TO rk2_runtime, rk2_human;

-- The vocabulary as one value, so a stamp can say which vocabulary it meant.
-- A word added, removed or re-described later gives a different digest, and
-- every stamp issued before it keeps the old one -- which is the difference
-- between a stamp that still says what it said and one that quietly means
-- something new.
CREATE FUNCTION rk2_capability_vocabulary_sha256() RETURNS text
LANGUAGE sql STABLE AS $fn$
    SELECT equivalence_key(
        (SELECT coalesce(jsonb_agg(jsonb_build_object(
                    'capability', c.capability, 'description', c.description)
                 ORDER BY c.capability), '[]'::jsonb)
           FROM capabilities c))
$fn$;

COMMENT ON FUNCTION rk2_capability_vocabulary_sha256() IS
  'Ticket 39 criterion 4: the capability vocabulary as one digest, over the words and their descriptions in one order. What a stamp records so that a later migration cannot change what an old stamp was claiming.';


-- ===========================================================================
-- 2. What a Test says it would pivot
-- ===========================================================================
--
-- 038 gave the specification an optional `impact` block. This is the second
-- one, and it may only appear beside the first: a pivot is demonstrated by an
-- authorized impact run, so a Test claiming a pivot and no impact is a Test
-- claiming to obtain a capability without doing anything an operator was asked
-- about.
--
-- Five fields, and every one of them is checkable against the run afterwards.
-- `transition` is the load-bearing one: it names the assertion whose holding
-- *is* the pivot, so criterion 2's "demonstrates the transition" has one
-- identifier to be about rather than a whole run to be read charitably.

CREATE FUNCTION rk2_pivot_problem(p_spec jsonb) RETURNS text
LANGUAGE plpgsql STABLE AS $fn$
DECLARE
    v_pivot  jsonb := p_spec -> 'pivot';
    v_key    text;
    v_item   jsonb;
    v_index  integer;
    v_seen   text[] := '{}';
    v_need   text;
BEGIN
    IF v_pivot IS NULL THEN
        -- 035's Test and 038's impact Test both stay exactly as they were.
        RETURN NULL;
    END IF;
    IF jsonb_typeof(v_pivot) <> 'object' THEN
        RETURN 'the pivot of a Test is an object';
    END IF;
    FOR v_key IN SELECT jsonb_object_keys(v_pivot) LOOP
        IF v_key NOT IN ('provides', 'requires', 'identity', 'transition',
                         'conditions') THEN
            RETURN 'the pivot carries no key named ' || v_key;
        END IF;
    END LOOP;

    -- A pivot rides on an impact grant, so a Test that states one states the
    -- other. Said here rather than in `open_pivot_*` because it is a property
    -- of the specification, and a specification that cannot be run is one
    -- nobody should be able to store.
    IF p_spec -> 'impact' IS NULL THEN
        RETURN 'a Test that claims a pivot states the impact it would have';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM capabilities c
                    WHERE c.capability = v_pivot ->> 'provides') THEN
        RETURN 'the pivot provides no capability this harness has a word for';
    END IF;

    IF jsonb_typeof(v_pivot -> 'requires') IS DISTINCT FROM 'array'
       OR jsonb_array_length(v_pivot -> 'requires') NOT BETWEEN 1 AND 8 THEN
        RETURN 'the pivot requires between 1 and 8 capabilities';
    END IF;
    FOR v_need IN SELECT jsonb_array_elements_text(v_pivot -> 'requires') LOOP
        IF NOT EXISTS (SELECT 1 FROM capabilities c WHERE c.capability = v_need) THEN
            RETURN v_need || ' is not a capability';
        END IF;
        IF v_need = ANY (v_seen) THEN
            RETURN 'the pivot requires ' || v_need || ' twice';
        END IF;
        v_seen := array_append(v_seen, v_need);
        -- A pivot from a capability to itself composes with nothing: every
        -- chain it could join it could also be dropped from.
        IF v_need = v_pivot ->> 'provides' THEN
            RETURN 'the pivot requires the capability it provides';
        END IF;
    END LOOP;

    -- The slot name and not an entity id, because the specification is
    -- digested and an id would pin the claim to one row of a table the Test
    -- knows nothing about. 003 keys identities by slot name globally, so the
    -- name resolves.
    IF coalesce(v_pivot ->> 'identity', '') !~ '^[a-z][a-z0-9_-]{1,62}$' THEN
        RETURN 'the pivot names no Identity the transition is performed under';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM jsonb_array_elements(p_spec -> 'assertions') x
         WHERE x ->> 'id' = v_pivot ->> 'transition') THEN
        RETURN 'the pivot names no assertion of this Test as its transition';
    END IF;

    -- Criterion 1's safety conditions, in 035's five words rather than a
    -- sixth vocabulary. A condition is prose under a type: what has to hold
    -- for this transition to be one the harness was willing to make.
    IF jsonb_typeof(v_pivot -> 'conditions') IS DISTINCT FROM 'array'
       OR jsonb_array_length(v_pivot -> 'conditions') NOT BETWEEN 1 AND 8 THEN
        RETURN 'the pivot states between 1 and 8 conditions';
    END IF;
    v_index := 0;
    FOR v_item IN SELECT * FROM jsonb_array_elements(v_pivot -> 'conditions') LOOP
        v_index := v_index + 1;
        IF jsonb_typeof(v_item) <> 'object' THEN
            RETURN 'pivot condition ' || v_index || ' is not an object';
        END IF;
        FOR v_key IN SELECT jsonb_object_keys(v_item) LOOP
            IF v_key NOT IN ('kind', 'detail') THEN
                RETURN 'pivot condition ' || v_index || ' carries no key named ' || v_key;
            END IF;
        END LOOP;
        IF NOT (coalesce(v_item ->> 'kind', '')
                  = ANY (rk2_test_precondition_kinds())) THEN
            RETURN 'pivot condition ' || v_index
                   || ' states no kind a condition may have';
        END IF;
        IF coalesce(v_item ->> 'detail', '') = ''
           OR length(v_item ->> 'detail') > 500 THEN
            RETURN 'pivot condition ' || v_index || ' states no detail';
        END IF;
    END LOOP;

    -- Criterion 1 asks for "scope and safety conditions", and the two are not
    -- the same ask. Any of 035's five kinds is a safety condition; only one of
    -- them says which scope the transition was reached under, and a pivot that
    -- states none of it is a capability claimed against nowhere in particular.
    -- The scope version the run actually ran under is on the Receipt and goes
    -- into the stamp from there -- this is the hunter saying which scope the
    -- claim is supposed to hold in, which is the half no row can supply.
    IF NOT EXISTS (
        SELECT 1 FROM jsonb_array_elements(v_pivot -> 'conditions') c
         WHERE c.value ->> 'kind' = 'scope_holds') THEN
        RETURN 'the pivot states no scope_holds condition';
    END IF;

    RETURN NULL;
END $fn$;

COMMENT ON FUNCTION rk2_pivot_problem(jsonb) IS
  'Ticket 39: the shape of the optional pivot block of a Test specification, or NULL. STABLE and not IMMUTABLE because it reads the capability vocabulary, which is a table.';

-- 038's validator, re-stated with one more key admitted at the top. Every rule
-- and every reason between is carried over word for word: a CREATE OR REPLACE
-- replaces the whole body, so the rationale 035 and 038 wrote into it has to be
-- copied forward or it is deleted.
--
-- The CHECK on `tests` cannot call this one: a CHECK constraint may only call
-- IMMUTABLE functions, and reading `capabilities` is not immutable. So the
-- pivot block is validated where a Test is written instead, by the trigger
-- below -- which is the same rule at the same moment, enforced by the other
-- mechanism this schema has for it.
CREATE OR REPLACE FUNCTION rk2_test_spec_problem(p_spec jsonb) RETURNS text
LANGUAGE plpgsql IMMUTABLE AS $fn$
DECLARE
    v_parts    text[] := ARRAY['preconditions', 'setup', 'actions',
                               'assertions', 'cleanup'];
    v_part     text;
    v_key      text;
    v_item     jsonb;
    v_problem  text;
    v_actions  integer;
    v_index    integer;
    v_role     text;
    v_ids      text[] := '{}';
    v_id       text;
    v_kind     text;
    v_action   integer;
    v_against  integer;
BEGIN
    IF jsonb_typeof(p_spec) <> 'object' THEN
        RETURN 'the specification is not an object';
    END IF;

    FOR v_key IN SELECT jsonb_object_keys(p_spec) LOOP
        -- `impact` and `pivot` are stated, not performed, so neither is one of
        -- the parts the loop below requires to be an array.
        IF NOT (v_key = ANY (v_parts)) AND v_key NOT IN ('impact', 'pivot') THEN
            RETURN 'the specification carries no part named ' || v_key;
        END IF;
    END LOOP;

    FOREACH v_part IN ARRAY v_parts LOOP
        IF jsonb_typeof(p_spec -> v_part) IS DISTINCT FROM 'array' THEN
            RETURN 'the ' || v_part || ' of a Test are an array';
        END IF;
    END LOOP;

    -- Preconditions are stated, not performed: what has to be true before the
    -- run is worth starting. They are prose under a typed word rather than a
    -- predicate the runtime evaluates, because the four things the runtime can
    -- decide -- scope, risk, the Identity lease, the budget -- it decides in
    -- `open_test_replay` against canonical state, and a second copy stated in
    -- the specification would be a second answer.
    IF jsonb_array_length(p_spec -> 'preconditions') > 16 THEN
        RETURN 'a Test states at most 16 preconditions';
    END IF;
    v_index := 0;
    FOR v_item IN SELECT * FROM jsonb_array_elements(p_spec -> 'preconditions') LOOP
        v_index := v_index + 1;
        IF jsonb_typeof(v_item) <> 'object' THEN
            RETURN 'precondition ' || v_index || ' is not an object';
        END IF;
        FOR v_key IN SELECT jsonb_object_keys(v_item) LOOP
            IF v_key NOT IN ('kind', 'detail') THEN
                RETURN 'precondition ' || v_index || ' carries no key named ' || v_key;
            END IF;
        END LOOP;
        IF NOT (coalesce(v_item ->> 'kind', '')
                  = ANY (rk2_test_precondition_kinds())) THEN
            RETURN 'precondition ' || v_index
                   || ' states no kind a precondition may have';
        END IF;
        IF coalesce(v_item ->> 'detail', '') = ''
           OR length(v_item ->> 'detail') > 500 THEN
            RETURN 'precondition ' || v_index || ' states no detail';
        END IF;
    END LOOP;

    -- Setup and cleanup are requests the run makes and no assertion may name.
    -- They carry no role for that reason: a role is what makes an action
    -- evidence, and neither of these is evidence about the target.
    FOREACH v_part IN ARRAY ARRAY['setup', 'cleanup'] LOOP
        IF jsonb_array_length(p_spec -> v_part) > 16 THEN
            RETURN 'a Test performs at most 16 ' || v_part || ' requests';
        END IF;
        v_index := 0;
        FOR v_item IN SELECT * FROM jsonb_array_elements(p_spec -> v_part) LOOP
            v_index := v_index + 1;
            IF jsonb_typeof(v_item) <> 'object' THEN
                RETURN v_part || ' request ' || v_index || ' is not an object';
            END IF;
            FOR v_key IN SELECT jsonb_object_keys(v_item) LOOP
                IF v_key NOT IN ('method', 'url') THEN
                    RETURN v_part || ' request ' || v_index
                           || ' carries no key named ' || v_key;
                END IF;
            END LOOP;
            v_problem := rk2_test_request_problem(
                v_item, v_part || ' request ' || v_index);
            IF v_problem IS NOT NULL THEN
                RETURN v_problem;
            END IF;
        END LOOP;
    END LOOP;

    v_actions := jsonb_array_length(p_spec -> 'actions');
    IF v_actions < 3 OR v_actions > 32 THEN
        -- Three is the floor because it follows from the rule below it rather
        -- than standing on its own: 035 asks for "one immutable Test
        -- specification with baseline, variant and control actions", so a Test
        -- carries all three roles and cannot do that in fewer than three
        -- actions. What that rules out is the Test with no control -- a
        -- baseline and a variant that differ, with nothing to say the target
        -- would not have differed anyway.
        RETURN 'a Test performs between 3 and 32 actions';
    END IF;
    v_index := 0;
    FOR v_item IN SELECT * FROM jsonb_array_elements(p_spec -> 'actions') LOOP
        v_index := v_index + 1;
        IF jsonb_typeof(v_item) <> 'object' THEN
            RETURN 'action ' || v_index || ' is not an object';
        END IF;
        FOR v_key IN SELECT jsonb_object_keys(v_item) LOOP
            IF v_key NOT IN ('ordinal', 'role', 'kind', 'method', 'url') THEN
                RETURN 'action ' || v_index || ' carries no key named ' || v_key;
            END IF;
        END LOOP;
        IF jsonb_typeof(v_item -> 'ordinal') IS DISTINCT FROM 'number'
           OR (v_item ->> 'ordinal')::numeric IS DISTINCT FROM v_index::numeric THEN
            RETURN 'action ' || v_index || ' is not numbered ' || v_index;
        END IF;
        IF NOT (coalesce(v_item ->> 'role', '') = ANY (rk2_test_roles())) THEN
            RETURN 'action ' || v_index || ' carries no role a Test action may have';
        END IF;
        IF coalesce(v_item ->> 'kind', '') <> 'request' THEN
            RETURN 'action ' || v_index || ' is not a request, which is the '
                   'only kind of action this runtime performs';
        END IF;
        v_problem := rk2_test_request_problem(v_item, 'action ' || v_index);
        IF v_problem IS NOT NULL THEN
            RETURN v_problem;
        END IF;
    END LOOP;

    FOREACH v_role IN ARRAY rk2_test_roles() LOOP
        IF NOT EXISTS (
            SELECT 1 FROM jsonb_array_elements(p_spec -> 'actions') a
             WHERE a ->> 'role' = v_role) THEN
            RETURN 'a Test performs at least one ' || v_role || ' action';
        END IF;
    END LOOP;

    IF jsonb_array_length(p_spec -> 'assertions') NOT BETWEEN 1 AND 32 THEN
        RETURN 'a Test states between 1 and 32 assertions';
    END IF;
    v_index := 0;
    FOR v_item IN SELECT * FROM jsonb_array_elements(p_spec -> 'assertions') LOOP
        v_index := v_index + 1;
        IF jsonb_typeof(v_item) <> 'object' THEN
            RETURN 'assertion ' || v_index || ' is not an object';
        END IF;
        FOR v_key IN SELECT jsonb_object_keys(v_item) LOOP
            IF v_key NOT IN ('id', 'kind', 'action', 'against', 'status') THEN
                RETURN 'assertion ' || v_index || ' carries no key named ' || v_key;
            END IF;
        END LOOP;

        v_id := coalesce(v_item ->> 'id', '');
        IF v_id !~ '^[a-z][a-z0-9-]{2,62}$' THEN
            RETURN 'assertion ' || v_index || ' states no identifier';
        END IF;
        IF v_id = ANY (v_ids) THEN
            -- Criterion 5 reports failed assertions by identifier, so two
            -- assertions sharing one would report a failure nobody can locate.
            RETURN 'two assertions are identified as ' || v_id;
        END IF;
        v_ids := array_append(v_ids, v_id);

        v_kind := coalesce(v_item ->> 'kind', '');
        IF NOT (v_kind = ANY (rk2_test_assertion_kinds())) THEN
            RETURN 'assertion ' || v_id || ' states no kind this runtime evaluates';
        END IF;

        IF jsonb_typeof(v_item -> 'action') IS DISTINCT FROM 'number' THEN
            RETURN 'assertion ' || v_id || ' names no action';
        END IF;
        v_action := (v_item ->> 'action')::numeric::integer;
        IF v_action NOT BETWEEN 1 AND v_actions THEN
            RETURN 'assertion ' || v_id || ' names action ' || v_action
                   || ', which this Test does not perform';
        END IF;

        IF v_kind = 'status_equals' THEN
            IF v_item ? 'against' THEN
                RETURN 'assertion ' || v_id || ' compares against an action '
                       'and states a status as well';
            END IF;
            IF jsonb_typeof(v_item -> 'status') IS DISTINCT FROM 'number'
               OR (v_item ->> 'status')::numeric::integer NOT BETWEEN 100 AND 599 THEN
                RETURN 'assertion ' || v_id || ' states no status in 100-599';
            END IF;
        ELSE
            IF v_item ? 'status' THEN
                RETURN 'assertion ' || v_id || ' states a status and compares '
                       'two actions as well';
            END IF;
            IF jsonb_typeof(v_item -> 'against') IS DISTINCT FROM 'number' THEN
                RETURN 'assertion ' || v_id || ' names no action to compare against';
            END IF;
            v_against := (v_item ->> 'against')::numeric::integer;
            IF v_against NOT BETWEEN 1 AND v_actions THEN
                RETURN 'assertion ' || v_id || ' compares against action '
                       || v_against || ', which this Test does not perform';
            END IF;
            IF v_against = v_action THEN
                RETURN 'assertion ' || v_id || ' compares action ' || v_action
                       || ' against itself';
            END IF;
        END IF;
    END LOOP;

    RETURN rk2_impact_problem(p_spec);
END $fn$;

CREATE FUNCTION apply_pivot_claim() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE v_problem text := rk2_pivot_problem(NEW.spec);
BEGIN
    IF v_problem IS NOT NULL THEN
        RAISE EXCEPTION '%', v_problem USING ERRCODE = '23514';
    END IF;
    -- Derived here rather than asked of every writer. 038's `open_impact_task`
    -- and 035's plain INSERT both store a spec and neither knows about this
    -- column, so a column they had to fill would be a column they got wrong.
    NEW.pivot_provides := NEW.spec -> 'pivot' ->> 'provides';
    RETURN NEW;
END $fn$;

COMMENT ON FUNCTION apply_pivot_claim() IS
  'Ticket 39: refuse a pivot block that is not one, and read the provided capability out of the block it belongs to. The half of the specification rule that reads a table, so it cannot be a CHECK; `tests` is immutable, so BEFORE INSERT is every moment a spec can be written.';

CREATE TRIGGER tests_pivot_claim
    BEFORE INSERT ON tests
    FOR EACH ROW EXECUTE FUNCTION apply_pivot_claim();

-- The provided capability again, on a column, so "which Tests claim to provide
-- this" is a join. Written by the trigger above and held to the specification
-- by a CHECK, the same way 038 does the impact class.
ALTER TABLE tests
    ADD COLUMN pivot_provides text REFERENCES capabilities(capability),
    ADD CONSTRAINT tests_pivot_provides_agrees_check
        CHECK (pivot_provides IS NOT DISTINCT FROM (spec -> 'pivot' ->> 'provides'));

COMMENT ON COLUMN tests.pivot_provides IS
  'Ticket 39: the capability this Test claims its transition provides, or NULL for a Test that claims no pivot. Held equal to spec -> pivot ->> provides by a CHECK.';


-- ===========================================================================
-- 3. Reading the run the claim was made about
-- ===========================================================================
--
-- Three questions the refusal and the source object both ask, so they are
-- asked in one place each. Every one of them reads canonical rows the door or
-- the closer wrote; none reads the claim.

-- Which Receipt answered the transition. The claim names an assertion, the
-- assertion names an action, and 035 recorded which Receipt answered which
-- action as the run performed it -- so this walk cannot be redirected after
-- the fact by anything a caller says.
CREATE FUNCTION rk2_pivot_transition_receipt(p_tool_run uuid, p_spec jsonb)
RETURNS uuid
LANGUAGE sql STABLE AS $fn$
    SELECT a.receipt_id
      FROM jsonb_array_elements(p_spec -> 'assertions') x
      JOIN test_replay_actions a
        ON a.tool_run_id = p_tool_run
       AND a.ordinal = (x.value ->> 'action')::numeric::integer
     WHERE x.value ->> 'id' = p_spec -> 'pivot' ->> 'transition'
$fn$;

COMMENT ON FUNCTION rk2_pivot_transition_receipt(uuid, jsonb) IS
  'Ticket 39: the exchange the claimed transition is read from -- the Receipt that answered the action the transition assertion names. NULL when the run never performed it.';

-- Whether that assertion held. 035 stores one entry per assertion with its
-- identifier and a boolean, so this is a lookup and not an interpretation.
CREATE FUNCTION rk2_pivot_transition_held(p_test_run uuid, p_spec jsonb)
RETURNS boolean
LANGUAGE sql STABLE AS $fn$
    SELECT coalesce(bool_or((a.value -> 'held')::boolean), false)
      FROM test_runs run,
           LATERAL jsonb_array_elements(run.assertion_results -> 'assertions') a
     WHERE run.id = p_test_run
       AND a.value ->> 'id' = p_spec -> 'pivot' ->> 'transition'
$fn$;

COMMENT ON FUNCTION rk2_pivot_transition_held(uuid, jsonb) IS
  'Ticket 39: did the assertion the claim calls its transition hold in this run. False when the run recorded no such assertion, which is the same answer for the same reason.';

-- Whether the transition is a request the member Finding was already validated
-- on. This is criterion 2's "rather than merely the member vulnerability", and
-- it is a route comparison because a route is what a request is: the member's
-- validating run performed a set of them, and a transition drawn from that set
-- re-demonstrates the member.
CREATE FUNCTION rk2_pivot_is_the_members_own_request(p_finding uuid, p_spec jsonb)
RETURNS boolean
LANGUAGE sql STABLE AS $fn$
    SELECT EXISTS (
        SELECT 1
          FROM findings f
          JOIN test_runs vr  ON vr.id = f.validated_by_test_run_id
          JOIN tests vt      ON vt.id = vr.test_id
          CROSS JOIN LATERAL jsonb_array_elements(vt.spec -> 'actions') member
          CROSS JOIN LATERAL jsonb_array_elements(p_spec -> 'assertions') x
          CROSS JOIN LATERAL jsonb_array_elements(p_spec -> 'actions') pivot_action
          CROSS JOIN LATERAL rk2_test_route(member.value ->> 'url') mr
          CROSS JOIN LATERAL rk2_test_route(pivot_action.value ->> 'url') pr
         WHERE f.id = p_finding
           AND x.value ->> 'id' = p_spec -> 'pivot' ->> 'transition'
           AND (pivot_action.value ->> 'ordinal')::numeric::integer
                 = (x.value ->> 'action')::numeric::integer
           AND member.value ->> 'method' = pivot_action.value ->> 'method'
           AND (mr.scheme, mr.host, mr.port, mr.path)
                 IS NOT DISTINCT FROM (pr.scheme, pr.host, pr.port, pr.path))
$fn$;

COMMENT ON FUNCTION rk2_pivot_is_the_members_own_request(uuid, jsonb) IS
  'Ticket 39 criterion 2: is the transition a request the member Finding''s own validating Test already made. When it is, the run demonstrated the member a second time and no transition at all.';


-- ===========================================================================
-- 4. What a stamp rests on, as one object
-- ===========================================================================
--
-- Criterion 4 asks the stamp to record "exact member, Test, conditions,
-- vocabulary and source hashes", and criterion 6 asks that repeating a valid
-- issuance be idempotent while changed evidence needs a new stamp. Both are
-- the same object: everything the stamp rests on, canonically ordered, hashed
-- once. Equal evidence gives an equal digest and finds the row already there;
-- anything that moves gives a different digest, which is a different stamp
-- rather than an edit to this one.
--
-- `member_validated_by` is in it for exactly that reason. A member re-validated
-- by a later run is a member whose evidence changed, and a stamp still keyed to
-- the old validation would be a claim about a run nobody would now cite.

CREATE FUNCTION rk2_pivot_source(p_program uuid, p_tool_run uuid) RETURNS jsonb
LANGUAGE sql STABLE AS $fn$
    SELECT jsonb_build_object(
        'member',              ir.finding_id,
        'member_validated_by', f.validated_by_test_run_id,
        'subject',             f.subject_entity_id,
        'identity',            r.identity_entity_id,
        'test',                rp.test_id,
        'test_spec',           rp.spec_sha256,
        'test_run',            rp.test_run_id,
        'tool_run',            ir.tool_run_id,
        'transition_receipt',  r.id,
        'transition',          t.spec -> 'pivot' ->> 'transition',
        'provides',            t.spec -> 'pivot' ->> 'provides',
        'requires',            t.spec -> 'pivot' -> 'requires',
        'conditions',          t.spec -> 'pivot' -> 'conditions',
        'scope_version',       r.scope_version,
        'vocabulary',          rk2_capability_vocabulary_sha256())
      FROM impact_replays ir
      JOIN test_replays rp ON rp.tool_run_id = ir.tool_run_id
      JOIN tests t         ON t.id = rp.test_id
      JOIN findings f      ON f.id = ir.finding_id
      JOIN receipts r      ON r.id = rk2_pivot_transition_receipt(ir.tool_run_id, t.spec)
     WHERE ir.tool_run_id = p_tool_run AND ir.program_id = p_program
$fn$;

COMMENT ON FUNCTION rk2_pivot_source(uuid, uuid) IS
  'Ticket 39: everything a pivot stamp rests on, as one canonical object -- the member and the run that validated it, the subject, the Identity the door recorded, the Test and its digest, the run, the transition and the Receipt that answered it, the capabilities, the conditions, the scope version in force and the capability vocabulary. Its digest is the stamp''s identity, and every column of a stamp but its own label and issuing time is read back out of it.';


-- ===========================================================================
-- 5. The stamp
-- ===========================================================================
--
-- Immutable, runtime-authored and complete: every question a reader could ask
-- about what was stamped is answered by a column here, so a chain built on it
-- in 040 joins rather than re-derives.

INSERT INTO label_prefixes (kind, prefix) VALUES ('pivot_stamps', 'PV');

CREATE TABLE pivot_stamps (
    id            uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id    uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    label         text NOT NULL DEFAULT '',
    finding_id    uuid NOT NULL,
    subject_entity_id  uuid NOT NULL,
    identity_entity_id uuid NOT NULL,
    test_id       uuid NOT NULL,
    test_run_id   uuid NOT NULL,
    tool_run_id   uuid NOT NULL,
    transition_receipt_id uuid NOT NULL,
    transition    text NOT NULL CHECK (btrim(transition) <> ''),
    provides      text NOT NULL REFERENCES capabilities(capability),
    requires      text[] NOT NULL CHECK (cardinality(requires) BETWEEN 1 AND 8),
    conditions    jsonb NOT NULL,
    scope_version integer NOT NULL,
    vocabulary_sha256 char(64) NOT NULL CHECK (vocabulary_sha256 ~ '^[0-9a-f]{64}$'),
    source        jsonb NOT NULL,
    source_sha256 char(64) NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
    issued_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, program_id),
    UNIQUE (program_id, label),
    -- Criterion 6, as a constraint rather than as a convention: one stamp per
    -- body of evidence, so a second issuance from the same evidence has
    -- nowhere to put a second row.
    UNIQUE (program_id, source_sha256),
    FOREIGN KEY (finding_id, program_id) REFERENCES findings (id, program_id)
        ON DELETE CASCADE,
    FOREIGN KEY (subject_entity_id, program_id) REFERENCES entities (id, program_id)
        ON DELETE CASCADE,
    FOREIGN KEY (test_id, program_id) REFERENCES tests (id, program_id)
        ON DELETE CASCADE,
    FOREIGN KEY (test_run_id, program_id) REFERENCES test_runs (id, program_id)
        ON DELETE CASCADE,
    FOREIGN KEY (tool_run_id, program_id) REFERENCES impact_replays (tool_run_id, program_id)
        ON DELETE CASCADE,
    FOREIGN KEY (transition_receipt_id, program_id) REFERENCES receipts (id, program_id)
        ON DELETE CASCADE,
    CHECK (source_sha256 = equivalence_key(source)),
    -- Every column here is one field of the source object, and none of them
    -- may disagree with it. Without this a stamp could be inserted whose digest
    -- covers one thing and whose columns say another, and every join in 040
    -- would read the columns. All of them and not a readable subset: a column
    -- left out of this list is a column the digest does not defend, which is
    -- the only kind of column an attacker on this table would bother to move.
    -- The two source fields with no column of their own -- `member_validated_by`
    -- and `test_spec` -- are here to move the digest when the evidence moves,
    -- and 040 reads them off `source`.
    CHECK ((source ->> 'member')::uuid = finding_id
           AND (source ->> 'subject')::uuid = subject_entity_id
           AND (source ->> 'identity')::uuid = identity_entity_id
           AND (source ->> 'test')::uuid = test_id
           AND (source ->> 'test_run')::uuid = test_run_id
           AND (source ->> 'tool_run')::uuid = tool_run_id
           AND (source ->> 'transition_receipt')::uuid = transition_receipt_id
           AND source ->> 'transition' = transition
           AND source ->> 'provides' = provides
           AND source -> 'requires' = to_jsonb(requires)
           AND source -> 'conditions' = conditions
           AND (source ->> 'scope_version')::integer = scope_version
           AND source ->> 'vocabulary' = vocabulary_sha256)
);

COMMENT ON TABLE pivot_stamps IS
  'Ticket 39: the runtime''s record that it saw a capability obtained. One row per body of evidence, issued only from a holding, authorized impact run whose named transition assertion held on a request the member Finding was not itself validated on.';

COMMENT ON COLUMN pivot_stamps.identity_entity_id IS
  'The Identity the door recorded on the transition Receipt, not the slot the claim named. When those two disagree the stamp is refused, so by the time a row exists they are the same Identity.';

COMMENT ON COLUMN pivot_stamps.source IS
  'The object `source_sha256` is the digest of, kept beside it so a reader can see what was hashed without recomputing it from fourteen joins. Held equal to the columns by a CHECK.';

CREATE INDEX pivot_stamps_finding_idx ON pivot_stamps (program_id, finding_id);
CREATE INDEX pivot_stamps_provides_idx ON pivot_stamps (program_id, provides);

CREATE TRIGGER pivot_stamps_assign_label BEFORE INSERT ON pivot_stamps
    FOR EACH ROW EXECUTE FUNCTION assign_label();

-- Nothing edits a stamp. What was seen is settled when it is written, and a
-- stamp that could be repointed afterwards is a licence to unlock work on
-- evidence that has since been swapped out.
CREATE TRIGGER pivot_stamps_immutable
    BEFORE UPDATE OR DELETE ON pivot_stamps
    FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_purging();


-- Every attempt, kept, on 036's pattern: an operator reading a Program with no
-- stamps cannot otherwise tell "nothing was claimed" from "everything was
-- refused", and a hunter whose pivot was refused learns nothing from silence.
CREATE TABLE pivot_proposals (
    id           uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id   uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    tool_run_id  uuid,
    test_id      uuid,
    finding_id   uuid,
    subject_entity_id uuid,
    agent_run_id uuid,
    provides     text,
    requires     text[],
    identity_slot text,
    conditions   jsonb,
    outcome      text NOT NULL CHECK (outcome IN ('issued', 'repeated', 'refused')),
    refusal      text,
    stamp_id     uuid,
    at           timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (tool_run_id, program_id)  REFERENCES test_replays (tool_run_id, program_id)
        ON DELETE CASCADE,
    FOREIGN KEY (test_id, program_id)      REFERENCES tests (id, program_id)
        ON DELETE CASCADE,
    FOREIGN KEY (finding_id, program_id)   REFERENCES findings (id, program_id)
        ON DELETE CASCADE,
    FOREIGN KEY (subject_entity_id, program_id) REFERENCES entities (id, program_id)
        ON DELETE CASCADE,
    FOREIGN KEY (agent_run_id, program_id) REFERENCES agent_runs (id, program_id)
        ON DELETE CASCADE,
    FOREIGN KEY (stamp_id, program_id)     REFERENCES pivot_stamps (id, program_id)
        ON DELETE CASCADE,
    CHECK ((outcome = 'refused') = (refusal IS NOT NULL)),
    CHECK ((outcome = 'refused') = (stamp_id IS NULL))
);

COMMENT ON TABLE pivot_proposals IS
  'Ticket 39: one row per attempt to stamp a pivot, with the sentence that refused it or the stamp it reached. Beside the stamps and reachable from none of them: the edge runs the other way.';

COMMENT ON COLUMN pivot_proposals.provides IS
  'Not a foreign key, deliberately, and null when the Test claimed no pivot at all. A claim naming a capability that is not in the vocabulary is one of the things the refusal is for, and a key here would refuse the record of the refusal.';

COMMENT ON COLUMN pivot_proposals.identity_slot IS
  'The slot the claim named, not the Identity the door recorded. A transition that went out as somebody else is a refusal, and this is the half of that disagreement a refused row would otherwise not carry.';

COMMENT ON COLUMN pivot_proposals.conditions IS
  'Criterion 1: a proposal names its own scope and safety conditions rather than being read for them through a Test that may claim no pivot at all.';

CREATE INDEX pivot_proposals_program_idx ON pivot_proposals (program_id, at DESC);

CREATE TRIGGER pivot_proposals_immutable
    BEFORE UPDATE OR DELETE ON pivot_proposals
    FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_purging();


-- ===========================================================================
-- 6. The refusal
-- ===========================================================================
--
-- Criterion 5 names five things that must be refused and criterion 3 names
-- five things that must be rechecked, and they are one list read from two
-- ends. All of it is here, in the order a reader would ask it: is there a run,
-- did it conclude, was it authorized and is it still, does the member still
-- stand, and did the run show the transition rather than the member.
--
-- One function, returning the first reason or NULL, because the alternative is
-- a refusal worded in the issuer and a second copy worded in the check -- and
-- the two would answer differently on the day one of them was edited.

CREATE FUNCTION rk2_pivot_refusal(p_program uuid, p_tool_run uuid) RETURNS text
LANGUAGE plpgsql STABLE AS $fn$
DECLARE
    v_replay  impact_replays%ROWTYPE;
    v_rp      test_replays%ROWTYPE;
    v_test    tests%ROWTYPE;
    v_run     test_runs%ROWTYPE;
    v_find    findings%ROWTYPE;
    v_receipt receipts%ROWTYPE;
    v_pivot   jsonb;
    v_status  text;
    v_slot    text;
    v_missing text;
BEGIN
    -- Missing, in the first sense: no run at all, or one that was never
    -- authorized as impact. `rk2_program_required` fences the Program, so a
    -- run of another Program is simply not found -- which is the cross-Program
    -- refusal, enforced by the same rule that fences every other read.
    SELECT * INTO v_replay FROM impact_replays
     WHERE tool_run_id = p_tool_run AND program_id = p_program;
    IF NOT FOUND THEN
        RETURN 'no authorized impact run of this Program is recorded under that Tool run';
    END IF;

    SELECT * INTO v_rp FROM test_replays
     WHERE tool_run_id = p_tool_run AND program_id = p_program;
    IF v_rp.test_run_id IS NULL THEN
        RETURN 'the run has not been closed, so nothing has concluded yet';
    END IF;

    SELECT * INTO v_test FROM tests WHERE id = v_rp.test_id;
    v_pivot := v_test.spec -> 'pivot';
    IF v_pivot IS NULL THEN
        RETURN 'test ' || v_test.label || ' claims no pivot';
    END IF;

    -- Inferred, in the first sense: the run did not hold. A pivot read off a
    -- run that failed is a pivot read off the hunter's expectation of it.
    SELECT * INTO v_run FROM test_runs WHERE id = v_rp.test_run_id;
    IF v_run.outcome <> 'holds' THEN
        RETURN 'the run concluded ' || v_run.outcome
               || ', and a pivot is stamped from a run that held';
    END IF;

    -- Inferred, in the second sense: the run held on the strength of other
    -- assertions and the one the claim called its transition did not.
    IF NOT rk2_pivot_transition_held(v_rp.test_run_id, v_test.spec) THEN
        RETURN 'assertion ' || (v_pivot ->> 'transition')
               || ' is the claimed transition and it did not hold';
    END IF;

    -- Grant, rechecked. 038 recorded which approval the run opened under and
    -- the key it covered; this asks whether that approval is still live now.
    -- The status alone, not the row: 029 revoked the runtime's table-level
    -- SELECT and gave back every column but the answer, so a `SELECT *` here
    -- would be this function asking to read what the operator wrote.
    SELECT d.status INTO v_status FROM pending_decisions d
     WHERE d.id = v_replay.pending_decision_id AND d.program_id = p_program;
    IF v_status <> 'approved' THEN
        RETURN 'the grant the run opened under is ' || v_status;
    END IF;
    IF live_grant_for(p_program, v_replay.equivalence_key) IS NULL THEN
        RETURN 'the grant the run opened under is no longer live';
    END IF;

    -- Program, rechecked. A closed Program and a halted one are both Programs
    -- against which nothing further may be claimed.
    IF EXISTS (SELECT 1 FROM programs WHERE id = p_program AND closed_at IS NOT NULL) THEN
        RETURN 'the Program is closed';
    END IF;
    IF EXISTS (SELECT 1 FROM program_halts
                WHERE program_id = p_program AND status = 'halted') THEN
        RETURN 'the Program is halted';
    END IF;

    -- The member, rechecked. This is criterion 5's invalidated member, and it
    -- is asked at issuing time rather than trusted from when the run opened,
    -- because a Finding can be rejected between the two. `reported` passes:
    -- 009 makes it the one status a validated Finding may move to, and a
    -- Finding somebody wrote up is not a Finding somebody withdrew.
    SELECT * INTO v_find FROM findings
     WHERE id = v_replay.finding_id AND program_id = p_program;
    IF v_find.status NOT IN ('validated', 'reported') THEN
        RETURN 'member finding ' || v_find.label || ' is ' || v_find.status
               || ', and a pivot composes validated Findings';
    END IF;

    -- Receipt, rechecked: the exchange the transition is read from is still
    -- there, still this run's, and still one the door let through.
    SELECT * INTO v_receipt FROM receipts
     WHERE id = rk2_pivot_transition_receipt(p_tool_run, v_test.spec)
       AND program_id = p_program;
    IF NOT FOUND THEN
        RETURN 'no Receipt answered the action the transition reads';
    END IF;
    IF v_receipt.decision <> 'allowed' THEN
        RETURN 'the transition request was ' || v_receipt.decision
               || ' and never reached the target';
    END IF;

    -- Artifact, rechecked: the bodies the transition Receipt cites can still be
    -- produced. A stamp whose exchange cannot be shown is a stamp nobody can
    -- audit. Retirement and not deletion is the case to ask about: 011 keeps
    -- the row and stamps `purged_at`, so a body that is gone is a row that is
    -- still there, and asking only whether the row exists would answer yes
    -- about an artifact this database deliberately no longer holds.
    SELECT string_agg(sha, ', ' ORDER BY sha) INTO v_missing
      FROM unnest(ARRAY[v_receipt.request_wire_sha, v_receipt.response_wire_sha,
                        v_receipt.request_agent_sha, v_receipt.response_agent_sha]) sha
     WHERE sha IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM artifacts a
                        WHERE a.sha256 = sha AND a.purged_at IS NULL);
    IF v_missing IS NOT NULL THEN
        RETURN 'the transition exchange cites artifacts this database no longer holds: '
               || v_missing;
    END IF;

    -- The Identity, checked against the door rather than against the claim.
    SELECT i.slot_name INTO v_slot FROM identities i
     WHERE i.entity_id = v_receipt.identity_entity_id;
    IF v_slot IS DISTINCT FROM (v_pivot ->> 'identity') THEN
        RETURN 'the claim names identity ' || (v_pivot ->> 'identity')
               || ' and the transition went out as ' || coalesce(v_slot, 'nobody');
    END IF;

    -- And criterion 2's own question, last because it is the one that is
    -- about the claim rather than about the machinery around it.
    IF rk2_pivot_is_the_members_own_request(v_replay.finding_id, v_test.spec) THEN
        RETURN 'the transition is a request member finding ' || v_find.label
               || ' was itself validated on, so it demonstrates the member again';
    END IF;

    RETURN NULL;
END $fn$;

COMMENT ON FUNCTION rk2_pivot_refusal(uuid, uuid) IS
  'Ticket 39 criteria 3 and 5 as one list: the first reason this run cannot be stamped as a pivot, or NULL. Read in the order a reader would ask it -- is there a run, did it conclude, is it still authorized, does the member still stand, and did it show the transition rather than the member.';


-- ===========================================================================
-- 7. Issuing one
-- ===========================================================================
--
-- Criterion 4's "emitted only by runtime authority" is two things at once.
-- `set_actor('runtime')` is what 026's actor-kind guard reads, so the row says
-- runtime and could not have said anything else; and `pivot_stamps` carries
-- INSERT for `rk2_runtime` alone, so no other role can reach the table with or
-- without this verb.

CREATE FUNCTION issue_pivot_stamp(p_tool_run_id uuid,
                                  p_agent_run_id uuid DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p         uuid := rk2_program_required();
    v_refusal text;
    v_source  jsonb;
    v_sha     text;
    v_stamp   pivot_stamps%ROWTYPE;
    v_test    tests%ROWTYPE;
    v_pivot   jsonb;
    v_repeat  boolean := false;
BEGIN
    SELECT t.* INTO v_test
      FROM test_replays rp JOIN tests t ON t.id = rp.test_id
     WHERE rp.tool_run_id = p_tool_run_id AND rp.program_id = p;
    v_pivot := v_test.spec -> 'pivot';

    v_refusal := rk2_pivot_refusal(p, p_tool_run_id);
    IF v_refusal IS NOT NULL THEN
        PERFORM set_actor('runtime');
        -- One row whatever was found, so every column that could not be
        -- resolved is a subquery returning NULL rather than a join that would
        -- have dropped the row. An attempt about a Tool run nobody has is
        -- exactly the attempt an operator most wants to see recorded.
        INSERT INTO pivot_proposals (program_id, tool_run_id, test_id, finding_id,
                                     subject_entity_id, agent_run_id,
                                     provides, requires, identity_slot,
                                     conditions, outcome, refusal)
        VALUES (p,
                (SELECT rp.tool_run_id FROM test_replays rp
                  WHERE rp.tool_run_id = p_tool_run_id AND rp.program_id = p),
                v_test.id,
                (SELECT ir.finding_id FROM impact_replays ir
                  WHERE ir.tool_run_id = p_tool_run_id AND ir.program_id = p),
                (SELECT f.subject_entity_id
                   FROM impact_replays ir JOIN findings f ON f.id = ir.finding_id
                  WHERE ir.tool_run_id = p_tool_run_id AND ir.program_id = p),
                p_agent_run_id,
                v_pivot ->> 'provides',
                CASE WHEN jsonb_typeof(v_pivot -> 'requires') = 'array'
                     THEN ARRAY(SELECT jsonb_array_elements_text(
                                    v_pivot -> 'requires'))
                END,
                v_pivot ->> 'identity',
                v_pivot -> 'conditions',
                'refused', v_refusal);
        RETURN jsonb_build_object('stamp', NULL, 'refusal', v_refusal);
    END IF;

    v_source := rk2_pivot_source(p, p_tool_run_id);
    v_sha    := equivalence_key(v_source);

    -- Criterion 6. Unchanged evidence digests the same, so the row is already
    -- there and this issuance is the same issuance rather than a second one.
    SELECT * INTO v_stamp FROM pivot_stamps
     WHERE program_id = p AND source_sha256 = v_sha;
    v_repeat := FOUND;

    IF NOT v_repeat THEN
        -- Every column out of the source object and none of them out of a
        -- second read of the same rows: the CHECK on the table requires them to
        -- agree, and two readers of one fact are two chances to disagree.
        PERFORM set_actor('runtime');
        INSERT INTO pivot_stamps
            (program_id, finding_id, subject_entity_id, identity_entity_id,
             test_id, test_run_id, tool_run_id, transition_receipt_id,
             transition, provides, requires, conditions, scope_version,
             vocabulary_sha256, source, source_sha256)
        VALUES (p, (v_source ->> 'member')::uuid,
                (v_source ->> 'subject')::uuid,
                (v_source ->> 'identity')::uuid,
                (v_source ->> 'test')::uuid, (v_source ->> 'test_run')::uuid,
                (v_source ->> 'tool_run')::uuid,
                (v_source ->> 'transition_receipt')::uuid,
                v_source ->> 'transition',
                v_source ->> 'provides',
                ARRAY(SELECT jsonb_array_elements_text(v_source -> 'requires')),
                v_source -> 'conditions',
                (v_source ->> 'scope_version')::integer,
                v_source ->> 'vocabulary', v_source, v_sha)
        RETURNING * INTO v_stamp;
    END IF;

    PERFORM set_actor('runtime');
    INSERT INTO pivot_proposals (program_id, tool_run_id, test_id, finding_id,
                                 subject_entity_id, agent_run_id,
                                 provides, requires, identity_slot,
                                 conditions, outcome, stamp_id)
    VALUES (p, p_tool_run_id, v_stamp.test_id, v_stamp.finding_id,
            v_stamp.subject_entity_id, p_agent_run_id,
            v_stamp.provides, v_stamp.requires, v_pivot ->> 'identity',
            v_stamp.conditions,
            CASE WHEN v_repeat THEN 'repeated' ELSE 'issued' END, v_stamp.id);

    RETURN jsonb_build_object(
        'stamp', v_stamp.label, 'refusal', NULL,
        'issued', NOT v_repeat,
        'member', (SELECT label FROM findings WHERE id = v_stamp.finding_id),
        'provides', v_stamp.provides, 'requires', to_jsonb(v_stamp.requires),
        'source_sha256', v_stamp.source_sha256);
END $fn$;

COMMENT ON FUNCTION issue_pivot_stamp(uuid, uuid) IS
  'Ticket 39: stamp the pivot a closed, authorized impact run demonstrated, or record why it cannot be stamped. Idempotent by the digest of the evidence: unchanged evidence returns the stamp that is already there, and anything that moved underneath is a different stamp.';


-- ===========================================================================
-- 8. Wiring: events, purge, isolation, grants
-- ===========================================================================

INSERT INTO event_types (id, family, subject_table, description) VALUES
    ('pivot.stamped', 'row', 'pivot_stamps',
     'a run was seen to obtain a capability, and the runtime recorded that it saw it');

INSERT INTO event_table_config (table_name, created_type) VALUES
    ('pivot_stamps', 'pivot.stamped');

-- `audit` and not `covered`, per ADR 0001 and 036's reading of it: two of the
-- three outcomes here write no canonical row for an Event to be about.
INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('pivot_proposals', 'audit',
     'the append-only record of what was claimed and what was answered; only the issued outcome has an Event of its own, and a refused or repeated attempt writes no canonical row for one to be about', '39');

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('pivot_stamps', 'program_id',
     'program-scoped: the purge root'),
    ('pivot_stamps', 'finding_id',
     'ON DELETE CASCADE to findings: a pivot off a Finding that is gone'),
    ('pivot_stamps', 'subject_entity_id',
     'ON DELETE CASCADE to entities: the subject the capability was obtained against'),
    ('pivot_stamps', 'test_id',
     'ON DELETE CASCADE to tests: the specification the claim was written in'),
    ('pivot_stamps', 'test_run_id',
     'ON DELETE CASCADE to test_runs: the run that held'),
    ('pivot_stamps', 'tool_run_id',
     'ON DELETE CASCADE to impact_replays: the authorized run underneath it'),
    ('pivot_stamps', 'transition_receipt_id',
     'ON DELETE CASCADE to receipts: the exchange the transition is read from, without which there is nothing to audit'),
    ('pivot_proposals', 'program_id',
     'program-scoped: the purge root'),
    ('pivot_proposals', 'tool_run_id',
     'ON DELETE CASCADE to test_replays: the run the claim was made about'),
    ('pivot_proposals', 'test_id',
     'ON DELETE CASCADE to tests: the specification the claim was written in'),
    ('pivot_proposals', 'finding_id',
     'ON DELETE CASCADE to findings: the member the pivot was claimed off'),
    ('pivot_proposals', 'subject_entity_id',
     'ON DELETE CASCADE to entities: the subject the capability was claimed against'),
    ('pivot_proposals', 'agent_run_id',
     'ON DELETE CASCADE to agent_runs: the run that asked'),
    ('pivot_proposals', 'stamp_id',
     'ON DELETE CASCADE to pivot_stamps: the stamp the attempt reached');

SELECT attach_event_triggers();
SELECT attach_actor_kind_guards();

GRANT SELECT, INSERT ON pivot_stamps, pivot_proposals TO rk2_runtime;
GRANT SELECT ON pivot_stamps, pivot_proposals TO rk2_human;

-- 029's default privileges hand every new table SELECT, INSERT, UPDATE and
-- DELETE to `rk2_runtime`, so a table meant to be append-only has to say so.
-- The trigger already refuses the statement; this stops it being attempted,
-- which is the difference between "the row did not change" and "the role
-- cannot change rows". A cascade from `programs` still reaches these rows: a
-- referential action runs with the referencing table's owner's rights, which
-- is how every other immutable table in this corpus is purged.
REVOKE UPDATE, DELETE ON TABLE pivot_stamps, pivot_proposals FROM rk2_runtime;
REVOKE ALL ON TABLE pivot_stamps, pivot_proposals FROM rk2_proxy, rk2_state;

REVOKE ALL ON FUNCTION rk2_capability_vocabulary_sha256() FROM PUBLIC;
REVOKE ALL ON FUNCTION rk2_pivot_problem(jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION rk2_pivot_transition_receipt(uuid, jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION rk2_pivot_transition_held(uuid, jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION rk2_pivot_is_the_members_own_request(uuid, jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION rk2_pivot_source(uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION rk2_pivot_refusal(uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION issue_pivot_stamp(uuid, uuid) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION rk2_capability_vocabulary_sha256()
    TO rk2_runtime, rk2_human;
GRANT EXECUTE ON FUNCTION rk2_pivot_problem(jsonb)
    TO rk2_state, rk2_runtime, rk2_human;
GRANT EXECUTE ON FUNCTION rk2_pivot_transition_receipt(uuid, jsonb) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION rk2_pivot_transition_held(uuid, jsonb) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION rk2_pivot_is_the_members_own_request(uuid, jsonb)
    TO rk2_runtime;
GRANT EXECUTE ON FUNCTION rk2_pivot_source(uuid, uuid) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION rk2_pivot_refusal(uuid, uuid) TO rk2_runtime, rk2_human;
GRANT EXECUTE ON FUNCTION issue_pivot_stamp(uuid, uuid) TO rk2_runtime;

SELECT apply_state_rls();
SELECT apply_state_grants();
SELECT enforce_always_triggers();


-- ===========================================================================
-- 9. The standing check
-- ===========================================================================

CREATE FUNCTION check_pivot_stamps()
RETURNS TABLE (problem text, detail text) LANGUAGE sql STABLE AS $fn$
    -- (a) a stamp whose digest no longer covers what it says
    SELECT 'stamp_digest_disagrees_with_its_source'::text, s.label
      FROM pivot_stamps s
     WHERE s.source_sha256 <> equivalence_key(s.source)
UNION ALL
    -- (b) a stamp off a member that is no longer validated. Not a refusal
    --     after the fact -- nothing rewrites a stamp -- but the thing 040's
    --     chain integrity has to see, and the thing an operator wants named.
    SELECT 'stamp_member_is_no_longer_validated', s.label
      FROM pivot_stamps s JOIN findings f ON f.id = s.finding_id
     WHERE f.status NOT IN ('validated', 'reported')
UNION ALL
    -- (c) a stamp whose member has since been re-validated by another run, so
    --     the evidence underneath it moved
    SELECT 'stamp_rests_on_a_superseded_validation', s.label
      FROM pivot_stamps s JOIN findings f ON f.id = s.finding_id
     WHERE f.validated_by_test_run_id
             IS DISTINCT FROM (s.source ->> 'member_validated_by')::uuid
UNION ALL
    -- Nothing here reports a stamp whose vocabulary digest is not the current
    -- one. That is the design working: a stamp records the vocabulary it was
    -- issued under precisely so a later migration cannot change what it was
    -- claiming, and a check that fired on it would go red at the next
    -- vocabulary change and stay red for the life of the corpus. The question
    -- worth asking is whether a word a pivot leans on is gone, and (g) asks it
    -- where the answer lives -- a stamp's `requires` is copied out of a spec
    -- that is immutable, so a stamp cannot have lost a word its Test still has.
    --
    -- (d) criterion 4: a stamp the runtime did not emit. 026's guard makes an
    --     actor authentic at the moment of writing; this asks after the fact
    --     whether a `pivot.stamped` Event attributing to the runtime is there
    --     at all, so a stamp whose Event says something else and a stamp with
    --     no Event are one answer.
    SELECT 'stamp_was_not_emitted_by_the_runtime', s.label
      FROM pivot_stamps s
     WHERE NOT EXISTS (SELECT 1 FROM events e
                        WHERE e.subject_id = s.id
                          AND e.type = 'pivot.stamped'
                          AND e.actor_kind = 'runtime')
UNION ALL
    -- (e) criterion 2: a stamp whose transition Receipt is not one of its own
    --     run's recorded actions
    SELECT 'stamp_cites_a_foreign_receipt', s.label
      FROM pivot_stamps s
     WHERE NOT EXISTS (SELECT 1 FROM test_replay_actions a
                        WHERE a.tool_run_id = s.tool_run_id
                          AND a.receipt_id = s.transition_receipt_id)
UNION ALL
    -- (f) a stamp whose run did not hold. The foreign keys pin the run but not
    --     its outcome, and an outcome is what a stamp rests on.
    SELECT 'stamp_rests_on_a_run_that_did_not_hold', s.label
      FROM pivot_stamps s JOIN test_runs r ON r.id = s.test_run_id
     WHERE r.outcome <> 'holds'
UNION ALL
    -- (g) a stored Test requiring a capability this harness no longer has a
    --     word for. `provides` is a foreign key and cannot drift; `requires`
    --     lives in the specification, which is immutable, so the only thing
    --     that can move under it is the vocabulary -- and a Test asking for a
    --     word nobody defines is a claim nothing can compose with. Asked of
    --     every stored Test and not only of the stamped ones, because a claim
    --     nothing can compose with is worth knowing about before it is run.
    SELECT 'test_requires_a_capability_that_is_gone', t.label
      FROM tests t
      CROSS JOIN LATERAL jsonb_array_elements_text(t.spec -> 'pivot' -> 'requires') need
     WHERE t.pivot_provides IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM capabilities c WHERE c.capability = need)
$fn$;

COMMENT ON FUNCTION check_pivot_stamps() IS
  'Ticket 39. Everything about a pivot that is true of the corpus rather than of one row: every stamp still digests to what it says, still rests on a validated member validated by the run it names, was emitted by the runtime, cites its own run''s Receipt and a run that held, and no stored Test asks for a capability the vocabulary has since lost. Deliberately silent about a stamp holding an older vocabulary digest, which is the point of recording one.';

REVOKE ALL ON FUNCTION check_pivot_stamps() FROM PUBLIC, rk2_state, rk2_proxy;
GRANT EXECUTE ON FUNCTION check_pivot_stamps() TO rk2_runtime, rk2_human;

INSERT INTO standing_checks (name, query, owner_ticket, note) VALUES
    ('check_pivot_stamps',
     'SELECT * FROM check_pivot_stamps()',
     '39',
     'A pivot is stamped from the run that showed it: every stamp digests to its own source, rests on a still-validated member and the run that validated it, was emitted by the runtime, cites a Receipt of its own holding run, and no stored Test asks for a capability the vocabulary has lost.');


-- ===========================================================================
-- 10. What this migration asserts about itself
-- ===========================================================================

DO $$
DECLARE n integer; v text;
BEGIN
    -- The vocabulary is closed and non-empty, which is what makes a stamp's
    -- `requires` and `provides` mean anything.
    SELECT count(*) INTO n FROM capabilities;
    IF n < 2 THEN
        RAISE EXCEPTION 'a pivot composes capabilities and % are defined', n;
    END IF;

    -- The digest is over the words and their descriptions, so re-describing a
    -- capability moves it. Asserted by construction rather than by reading the
    -- source: two vocabularies that differ only in a description must differ.
    IF rk2_capability_vocabulary_sha256()
       = equivalence_key((SELECT coalesce(jsonb_agg(jsonb_build_object(
                              'capability', c.capability,
                              'description', c.description || '!')
                           ORDER BY c.capability), '[]'::jsonb)
                     FROM capabilities c)) THEN
        RAISE EXCEPTION 'the capability vocabulary digest ignores what a capability means';
    END IF;

    -- A stamp is immutable and nothing below the owner may edit one, which is
    -- the whole of "the immutable stamp".
    IF NOT EXISTS (SELECT 1 FROM pg_trigger
                    WHERE tgname = 'pivot_stamps_immutable'
                      AND tgrelid = 'pivot_stamps'::regclass) THEN
        RAISE EXCEPTION 'a pivot stamp can be edited after it was issued';
    END IF;
    SELECT string_agg(g.role || ' holds ' || g.privilege, ', ') INTO v
      FROM (VALUES ('rk2_runtime'), ('rk2_human'), ('rk2_state'), ('rk2_proxy'))
             AS r(role),
           (VALUES ('UPDATE'), ('DELETE')) AS p(privilege)
      CROSS JOIN LATERAL (SELECT r.role, p.privilege) g
     WHERE has_table_privilege(r.role, 'pivot_stamps', p.privilege);
    IF v IS NOT NULL THEN
        RAISE EXCEPTION 'a pivot stamp can be rewritten: %', v;
    END IF;

    -- Criterion 2 is structural, so the function that answers it must read the
    -- member's own validating run rather than the claim.
    SELECT prosrc INTO v FROM pg_proc
     WHERE proname = 'rk2_pivot_is_the_members_own_request';
    IF v NOT LIKE '%validated_by_test_run_id%' THEN
        RAISE EXCEPTION 'the transition is not compared against what validated the member';
    END IF;

    -- And the refusal is worded once. Two copies of "no longer live" would be
    -- two rules on the day one of them was edited.
    SELECT count(*) INTO n FROM pg_proc
     WHERE pronamespace = 'public'::regnamespace
       AND prosrc LIKE '%and a pivot composes validated Findings%';
    IF n <> 1 THEN
        RAISE EXCEPTION '% functions word the refusal of an invalidated member', n;
    END IF;
END $$;
