-- ---------------------------------------------------------------------------
-- 20260914T000000Z__a_fixture_is_reached_by_address_not_by_name.sql    (PH2-78)
--
-- `rk playbook evaluate` grades a Playbook on every production seam but one.
-- `program.run` opens each Program, `config.load` and `scope.compile_policy`
-- read the document, `record_playbook_test_run` does the counting -- and the
-- door is missing, because the fixture listens on an ephemeral loopback port
-- and the door refuses loopback twice over: `scope.address_refusal` when the
-- policy is compiled, and `authorize_egress_address` when an address is about
-- to be dialled. Both refusals are correct. A Program whose scope could name a
-- loopback address at a port of its choosing is a Program that can be pointed
-- at this host's own PostgreSQL, and those two rules are what stand between a
-- configuration file and that.
--
-- So the fixture is not made dialable. The evaluator moves it: with an Agent
-- boundary configured the fixture binds on the gateway address of the door's
-- own routable network -- a private address this machine answers on, which the
-- children on the internal Agent network cannot reach and the door can -- and
-- the Program records where it put it. That record is this file.
--
-- `fixture_addresses` is one row per evaluation Program: the host its scope
-- already classes as a target, and the address that host is actually listening
-- at. It is written by `open_fixture_address` and read by
-- `authorize_fixture_address`, and neither of them widens what the door will
-- dial by name:
--
--   * only a Program in `evaluation_programs` may have a row at all, which is a
--     foreign key rather than a check, so nothing that is not grading a
--     Playbook can acquire one;
--   * the address must be RFC 1918 or unique-local -- never loopback, never
--     link-local, never a global address -- so the fixture address cannot point at
--     this host's own control ports and cannot become a second, unchecked way
--     to reach the internet;
--   * the host and port must already be `target` in the Program's own compiled
--     policy, so a fixture address changes the address a target is dialled at and
--     never makes something a target;
--   * and nothing a configuration file writes reaches this function. The
--     compiler is untouched, and an inclusion naming 10.0.0.1 is refused today
--     exactly as it was yesterday.
--
-- The Receipt says what happened rather than something adjacent to it. The
-- address it pins is the address the socket was opened to, and its class is
-- `fixture` -- a fourth scope class, so that a synthetic target the harness
-- started for itself is legible as one and `target` keeps meaning what it did.
-- An evaluation has always been visible to the Agent reading its own Receipts,
-- because ticket 46 scopes a fixture under `<fixture>.localhost` and that name
-- is in every row; this class tells it nothing the host column does not.
--
-- Two routes to one fixture, then, and a run says which it took:
-- `playbook_test_runs.route` is derived at filing from whether the vulnerable
-- Program opened a fixture address. A run that had the door and reached nothing is
-- then a reported problem rather than a silent zero, which is the arm
-- `check_playbook_tests` gains at the end of this file.
-- ---------------------------------------------------------------------------


-- ---------------------------------------------------------------------------
-- 1. Where one evaluation Program's fixture is listening
-- ---------------------------------------------------------------------------
-- One row per Program and no history: a fixture address is where a fixture was put
-- when the Program opened, and a second row would make "which address is this
-- Program's target at" a question about row order -- asked, at dial time, by
-- the door.
--
-- The address is `inet` rather than text so that the range rule is arithmetic
-- rather than a regular expression, and constrained to a single host so that a
-- network cannot be smuggled in as one: `10.0.0.0/8` is not an address anything
-- listens at, and `<<` would admit every subnet of it.

CREATE TABLE fixture_addresses (
    -- To the marker and not to `programs`, which is the fence: a Program that
    -- is not grading a Playbook cannot have a fixture address, and the reason is a
    -- foreign key rather than a sentence in a function somebody may restate.
    program_id uuid PRIMARY KEY
        REFERENCES evaluation_programs(program_id) ON DELETE CASCADE,
    -- One protocol. A fixture is served by `evaluation.served` over plain HTTP;
    -- a second spelling here would be a claim about a listener nothing starts.
    protocol   text NOT NULL CHECK (protocol = 'http'),
    -- The name the Program's scope carries, normalised the way the policy
    -- normalises it. The door asks by name and this is the name it asks with.
    host       text NOT NULL CHECK (host = lower(host) AND host <> ''),
    port       integer NOT NULL CHECK (port BETWEEN 1 AND 65535),
    address    inet NOT NULL,
    opened_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fixture_addresses_address_is_one_private_host CHECK (
        masklen(address) = CASE WHEN family(address) = 4 THEN 32 ELSE 128 END
        AND (address << inet '10.0.0.0/8'
          OR address << inet '172.16.0.0/12'
          OR address << inet '192.168.0.0/16'
          OR address << inet 'fc00::/7')
    )
);

COMMENT ON TABLE fixture_addresses IS
 'Where the fixture one evaluation Program is grading is actually listening. '
 'Written by `open_fixture_address` when the Program opens, read by '
 '`authorize_fixture_address` when the door is about to dial. Changes the '
 'address a target is reached at and never what the policy calls a target.';

COMMENT ON COLUMN fixture_addresses.address IS
 'The private address the harness bound the fixture on: the gateway of the door''s own routable network. Never loopback, never link-local, never global -- a fixture address is not a way to reach this host''s control ports or a second way to reach the internet.';

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
 ('fixture_addresses', 'program_id',
  'program-scoped: the fixture address dies with the evaluation it was opened for');

INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
 ('fixture_addresses', 'reference',
  'where one evaluation put its fixture; written once when the Program opens, and covered by the marker''s own row', '78');

-- No `state_read_surface` row, for 046's reason restated: the fixture catalogue
-- is the answer key, and a Program that could read its own fixture address would be
-- reading the harness's arrangements for grading it.


-- ---------------------------------------------------------------------------
-- 2. Opening one, which the runtime does and a configuration cannot
-- ---------------------------------------------------------------------------
-- Called by `evaluation._graded_work`, in the same wrapper that writes the marker
-- and before the work runs -- so a Program that is about to be worked has its
-- fixture address or has never had one, and there is no interval in which the door
-- would resolve the fixture's name for real.
--
-- Every rule here is about the fixture address being narrower than the policy, never
-- wider. The Program must already class the host and port as `target`; the
-- address must be one of this machine's own private addresses; the protocol is
-- the one thing `evaluation.served` serves. A caller that satisfies all three
-- has moved a target it was already allowed to reach. A caller that satisfies
-- none of them is refused with the rule it broke named, because the one thing
-- worse than this function refusing is this function refusing anonymously.

CREATE FUNCTION open_fixture_address(
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

    IF p_protocol IS DISTINCT FROM 'http' THEN
        RAISE EXCEPTION 'a fixture is served over http, not %',
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
 'Records where an evaluation Program''s fixture is listening. Refuses a Program '
 'that is not an evaluation, a host its own policy does not class as a target, '
 'and any address that is not one private host on this machine.';


-- ---------------------------------------------------------------------------
-- 3. Reading one, which is the door's question and nobody else's
-- ---------------------------------------------------------------------------
-- Asked by `proxy.Handler._pin` before the name is resolved, because the whole
-- point is that it is not resolved: a fixture address answers "this target is at this
-- address", and a DNS lookup for `webapp.localhost` would answer 127.0.0.1 and
-- be refused, correctly, one line later.
--
-- The capability is resolved again for the same reason `authorize_egress_address`
-- resolves it: this is the last decision before a socket, and a capability whose
-- Tool run closed in between must not open one. It is resolved through
-- `resolve_egress_identity` rather than `resolve_egress_capability` so that the
-- Identity lease is re-checked here too -- the other route reaches that check
-- through `authorize_identity_egress_address`, and a route that skipped it
-- would be a way to dial with a lease that had lapsed. The Program comes from
-- the capability rather than from the door, so a door made to lie about which
-- Program it serves reads somebody else's fixture address no more than it reads
-- somebody else's policy.
--
-- The coverage question is asked again as well, at the Program's scope version
-- as it stands now rather than as it stood when the fixture address was opened. That is
-- what the other route gets from `authorize_egress_address` refusing a withdrawn
-- destination: an operator who takes the fixture's host out of scope mid-run has
-- taken it out, and a recorded address is not a standing permission.
--
-- No row is the ordinary answer and is not a refusal -- almost every request
-- this fence ever sees is against a real target, and the caller falls through to
-- resolving the name. The class comes back with the address because the door
-- does not get to name what it was allowed as.

CREATE FUNCTION authorize_fixture_address(
    p_capability text,
    p_protocol   text,
    p_host       text,
    p_port       integer
) RETURNS TABLE (
    address     text,
    scope_class text
)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    v_auth    record;
    v_host    text;
    v_address text;
    v_version integer;
    v_class   text;
BEGIN
    SELECT * INTO v_auth FROM resolve_egress_identity(p_capability);
    IF NOT FOUND THEN
        RAISE EXCEPTION 'egress capability refused' USING ERRCODE = '23514';
    END IF;

    v_host := scope_normalize_host(p_host);
    SELECT host(e.address) INTO v_address
      FROM fixture_addresses e
     WHERE e.program_id = v_auth.program_id
       AND e.protocol = p_protocol
       AND e.host = v_host
       AND e.port = p_port;
    IF v_address IS NULL THEN
        RETURN;
    END IF;

    SELECT p.scope_version INTO v_version FROM programs p WHERE p.id = v_auth.program_id;
    SELECT s.scope_class INTO v_class
      FROM scope_class_of(v_auth.program_id, v_version, v_host, p_port,
                          '/', '/', p_protocol, 'coverage') s;
    IF coalesce(v_class, 'denied') <> 'target' THEN
        RAISE EXCEPTION 'the scope of program % no longer classes %:% as a target',
            v_auth.program_id, v_host, p_port
          USING DETAIL = 'a recorded fixture address is where a target is dialled, '
                         'not a standing permission to dial it',
                ERRCODE = '23514';
    END IF;

    RETURN QUERY SELECT v_address, 'fixture'::text;
END $fn$;

COMMENT ON FUNCTION authorize_fixture_address(text, text, text, integer) IS
 'The address an evaluation''s fixture is listening at, for the one host and port '
 'the request named, or no row at all. Refuses a lapsed capability, a lapsed '
 'Identity lease and a host this Program''s scope no longer classes as a target. '
 'The door dials what this answers with and pins it on the Receipt; everything '
 'else resolves the name as it always did.';


-- ---------------------------------------------------------------------------
-- 4. A fourth class on a Receipt
-- ---------------------------------------------------------------------------
-- `target` keeps meaning "something an operator put in scope and a Program is
-- hunting". A fixture is neither: the harness started it, on this machine, to
-- measure a Playbook against a defect it planted. Filing that as `target` would
-- put synthetic traffic and real traffic in one column, and an auditor counting
-- what a Program did to a target would be counting evaluations too.

ALTER TABLE receipts DROP CONSTRAINT receipts_scope_class_check;
ALTER TABLE receipts ADD CONSTRAINT receipts_scope_class_check
    CHECK (scope_class IN ('target','egress_support','control_plane','denied','fixture'));

COMMENT ON COLUMN receipts.scope_class IS
 'What the request was allowed AS. `fixture` is a synthetic target this harness started for an evaluation, reached at the address in fixture_addresses rather than at whatever its name resolves to.';


-- ---------------------------------------------------------------------------
-- 5. Which route a run took, on the run
-- ---------------------------------------------------------------------------
-- The evaluator's report says it too, but a report is read by whoever ran the
-- command and a run row is read by every rule that grades a Playbook. The
-- default is what every row already written means: before this file there was
-- one route, and it was loopback.

ALTER TABLE playbook_test_runs
    ADD COLUMN route text NOT NULL DEFAULT 'loopback'
        CHECK (route IN ('loopback','door'));

COMMENT ON COLUMN playbook_test_runs.route IS
 'How the Agent reached the fixture: `loopback`, the in-process route a machine with no Agent boundary takes, or `door`, through the proxy at the address fixture_addresses recorded. Derived at filing from the vulnerable Program''s fixture address, never supplied.';

-- 046's function with one derived column added. Restated whole rather than
-- wrapped: it is one INSERT and a wrapper would be a second function deciding
-- half of one row.

CREATE OR REPLACE FUNCTION record_playbook_test_run(
    p_playbook   uuid,
    p_fixture    text,
    p_vulnerable uuid,
    p_secure     uuid DEFAULT NULL
) RETURNS uuid
LANGUAGE plpgsql AS $$
DECLARE
    v_sha          text;
    v_source       text;
    v_ground_truth text;
    v_kind         text;
    v_side         text;
    v_skills       text;
    v_ambiguous    text;
    v_repeat       integer;
    v_run          uuid;
    c              record;
BEGIN
    SELECT p.source_sha256 INTO v_sha FROM playbooks p WHERE p.id = p_playbook;
    IF v_sha IS NULL THEN
        RAISE EXCEPTION 'no playbook %', p_playbook USING ERRCODE = 'foreign_key_violation';
    END IF;

    SELECT f.source_sha256, f.ground_truth_sha256, f.kind
      INTO v_source, v_ground_truth, v_kind
      FROM fixtures f WHERE f.id = p_fixture;
    IF v_source IS NULL THEN
        RAISE EXCEPTION 'no fixture %', p_fixture USING ERRCODE = 'foreign_key_violation';
    END IF;

    SELECT b.side INTO v_side
      FROM playbook_fixture_binding(p_playbook) b WHERE b.fixture_id = p_fixture;

    -- The two Programs are the evaluator's, and they have to say so. A run
    -- counted out of an unmarked Program would be a run whose evidence C is
    -- still admitting into promotions: the marker is what makes the exclusion
    -- and the measurement read the same rows.
    PERFORM 1 FROM evaluation_programs e
      WHERE e.program_id = p_vulnerable AND e.playbook_id = p_playbook
        AND e.fixture_id = p_fixture AND e.variant = 'vulnerable';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'program % is not marked as the vulnerable evaluation of % against %',
            p_vulnerable, (SELECT path FROM playbooks WHERE id = p_playbook), p_fixture
          USING HINT = 'mark it in evaluation_programs before the run, not after',
                ERRCODE = 'check_violation';
    END IF;

    IF v_kind = 'own_pair' THEN
        PERFORM 1 FROM evaluation_programs e
          WHERE e.program_id = p_secure AND e.playbook_id = p_playbook
            AND e.fixture_id = p_fixture AND e.variant = 'secure';
        IF NOT FOUND THEN
            RAISE EXCEPTION 'fixture % is a pair and its secure half was not run', p_fixture
              USING DETAIL = 'without the control, a claim on the vulnerable half cannot be '
                             'told apart from a claim the playbook makes about anything',
                    ERRCODE = 'check_violation';
        END IF;
    ELSIF p_secure IS NOT NULL THEN
        RAISE EXCEPTION 'fixture % has no secure twin; there is no second program to run',
            p_fixture USING ERRCODE = 'check_violation';
    END IF;

    -- Every count, from the rows the run left behind.
    WITH claim AS (
        SELECT h.property_class,
               h.status = 'supported' AS asserted,
               EXISTS (SELECT 1 FROM hypothesis_evidence he
                        WHERE he.hypothesis_id = h.id AND he.polarity = 'supports') AS grounded,
               EXISTS (SELECT 1 FROM playbook_outputs po
                        WHERE po.playbook_id = p_playbook
                          AND po.property_class = h.property_class) AS declared,
               EXISTS (SELECT 1 FROM fixture_classes fc
                        WHERE fc.fixture_id = p_fixture
                          AND fc.property_class = h.property_class) AS contained,
               -- Deliberately wider than the vulnerable side below, which is
               -- restricted to the subjects this Playbook was selected on: a
               -- claim of this class on the control disqualifies whatever
               -- selected it there. The asymmetry only ever REMOVES credit,
               -- and a control that let a claim through on a technicality
               -- about which selection produced it would be no control.
               EXISTS (SELECT 1 FROM hypotheses s
                         JOIN hypothesis_evidence se
                           ON se.hypothesis_id = s.id AND se.polarity = 'supports'
                        WHERE s.program_id = p_secure
                          AND s.superseded_by IS NULL
                          AND s.status = 'supported'
                          AND s.property_class = h.property_class) AS admitted
          FROM hypotheses h
         WHERE h.program_id = p_vulnerable
           AND h.superseded_by IS NULL
           AND EXISTS (SELECT 1 FROM playbook_selections s
                        WHERE s.program_id = p_vulnerable
                          AND s.playbook_id = p_playbook
                          AND s.subject_entity_id = h.subject_entity_id
                          AND s.dropped_because IS NULL)
    )
    SELECT count(*)::int AS claims,
           count(*) FILTER (WHERE asserted AND NOT grounded)::int AS ungrounded,
           count(*) FILTER (WHERE asserted AND grounded AND declared)::int AS fired_in_scope,
           count(*) FILTER (WHERE asserted AND grounded AND NOT declared)::int AS out_of_scope,
           count(*) FILTER (WHERE asserted AND grounded AND NOT contained)::int AS false_positives,
           count(*) FILTER (WHERE p_secure IS NOT NULL
                                  AND asserted AND grounded AND declared
                                  AND contained AND NOT admitted)::int AS discriminating_tp
      INTO c FROM claim;

    -- Repeats are numbered by the harness. A caller-supplied index is a caller
    -- that can overwrite the repeat it did not like.
    SELECT coalesce(max(r.repeat_index) + 1, 0) INTO v_repeat
      FROM playbook_test_runs r
     WHERE r.playbook_id = p_playbook AND r.playbook_sha256 = v_sha
       AND r.fixture_id = p_fixture;

    -- The instrument, from 045's freeze rather than from the registry as it
    -- stands now. `playbook_selection_skills` is what this Program was handed
    -- when the Playbook was selected in it; `skills` is what the catalogue holds
    -- at the moment of filing, and the two differ exactly when a Skill was
    -- edited between the run and the filing -- which is the case 045 froze them
    -- for. The counts above already read this run through `playbook_selections`,
    -- so taking its instrument from anywhere else would be one function keeping
    -- two accounts of one Program.
    --
    -- A Program that froze two texts of one Skill name is refused rather than
    -- deduplicated: the run's own key would then depend on which of them the
    -- insert happened to keep.
    SELECT string_agg(name, ', ' ORDER BY name) INTO v_ambiguous FROM (
        SELECT k.skill_name AS name
          FROM playbook_selection_skills k
          JOIN playbook_selections s ON s.id = k.selection_id
         WHERE s.program_id = p_vulnerable AND s.playbook_id = p_playbook
           AND s.dropped_because IS NULL
         GROUP BY k.skill_name
        HAVING count(DISTINCT (k.skill_sha256, k.skill_version)) > 1
    ) q;
    IF v_ambiguous IS NOT NULL THEN
        RAISE EXCEPTION 'program % froze more than one text of Skill %', p_vulnerable, v_ambiguous
          USING DETAIL = 'the repeat has no single instrument to record; re-run it against '
                         'a corpus that stopped moving',
                ERRCODE = 'check_violation';
    END IF;

    -- The run key: everything that must be equal for two rows to be repeats of
    -- one measurement. The Skill digests are in it because two runs that read
    -- different Skill texts measured different instruments, however identical
    -- the Playbook was.
    SELECT string_agg(DISTINCT k.skill_name || '@' || coalesce(k.skill_sha256, '-')
                      || '/' || coalesce(k.skill_version, '-'), ','
                      ORDER BY k.skill_name || '@' || coalesce(k.skill_sha256, '-')
                      || '/' || coalesce(k.skill_version, '-'))
      INTO v_skills
      FROM playbook_selection_skills k
      JOIN playbook_selections s ON s.id = k.selection_id
     WHERE s.program_id = p_vulnerable AND s.playbook_id = p_playbook
       AND s.dropped_because IS NULL;

    INSERT INTO playbook_test_runs
        (playbook_id, playbook_sha256, fixture_id, fixture_sha256, fixture_ground_truth,
         side, repeat_index, run_key,
         claims, ungrounded, fired_in_scope, out_of_scope, false_positives,
         discriminating_tp, admitted_secure, tool_runs, route)
    VALUES
        (p_playbook, v_sha, p_fixture, v_source, v_ground_truth,
         v_side, v_repeat,
         left(encode(sha256(convert_to(
              p_playbook::text || ':' || v_sha || ':' || p_fixture || ':' || v_source
              || ':' || v_ground_truth || ':' || coalesce(v_skills, ''), 'utf8')), 'hex'), 32),
         c.claims, c.ungrounded, c.fired_in_scope, c.out_of_scope, c.false_positives,
         c.discriminating_tp,
         -- 036's R4: NULL, never 0, for a target with no secure twin. Counted
         -- inside the Playbook's own declaration, because a correct claim about
         -- something else on the secure half is not a false alarm -- the
         -- out-side clause is what answers that.
         CASE WHEN v_kind = 'own_pair' THEN (
             SELECT count(*)::int FROM hypotheses h
               JOIN hypothesis_evidence he
                 ON he.hypothesis_id = h.id AND he.polarity = 'supports'
              WHERE h.program_id = p_secure AND h.superseded_by IS NULL
                AND h.status = 'supported'
                AND EXISTS (SELECT 1 FROM playbook_outputs po
                             WHERE po.playbook_id = p_playbook
                               AND po.property_class = h.property_class))
         END,
         (SELECT count(*)::int FROM tool_runs t
           WHERE t.program_id = p_vulnerable
              OR (p_secure IS NOT NULL AND t.program_id = p_secure)),
         -- Ticket 78. Derived, never passed: the caller already says which
         -- Programs ran, and which route they had is a fact about those
         -- Programs rather than a second opinion the evaluator supplies.
         -- The vulnerable half alone decides it, because that is the half
         -- the counts above are about; a pair is opened on one route.
         CASE WHEN EXISTS (SELECT 1 FROM fixture_addresses ep
                            WHERE ep.program_id = p_vulnerable)
              THEN 'door' ELSE 'loopback' END)
    RETURNING id INTO v_run;

    INSERT INTO playbook_test_run_skills (run_id, skill_name, skill_sha256, skill_version)
    SELECT DISTINCT v_run, k.skill_name, k.skill_sha256, k.skill_version
      FROM playbook_selection_skills k
      JOIN playbook_selections s ON s.id = k.selection_id
     WHERE s.program_id = p_vulnerable AND s.playbook_id = p_playbook
       AND s.dropped_because IS NULL;

    RETURN v_run;
END $$;


-- ---------------------------------------------------------------------------
-- 6. The standing check learns the route
-- ---------------------------------------------------------------------------
-- 046's arms with one hard arm added, restated in full for the reason 046 gave
-- when it restated 036's: the arms are a single UNION ALL and there is no seam
-- to add one at. The registration is unchanged -- it selects `severity =
-- 'error'` -- so the new arm is picked up without touching the row.

CREATE OR REPLACE FUNCTION check_playbook_tests()
RETURNS TABLE (severity text, problem text, detail text) LANGUAGE sql STABLE AS $$
    -- HARD: a stable playbook whose test fails. `demote_playbooks()` is owed.
    SELECT 'error'::text, 'stable_playbook_failing'::text, p.path || ' -> ' || v.reason
      FROM playbooks p
      CROSS JOIN LATERAL playbook_test_verdict(p.id, p.source_sha256) v
     WHERE p.status = 'stable' AND v.verdict = 'fail'
UNION ALL
    -- HARD: ticket 46. Stable and past its review date. Same shape as the
    -- above and the same remedy; 036 reported this as a warning because expiry
    -- did not demote, and it does now.
    SELECT 'error', 'stable_playbook_expired',
           p.path || ' -> stale_after passed on ' || p.stale_after::date::text
      FROM playbooks p
     WHERE p.status = 'stable' AND p.stale_after IS NOT NULL AND p.stale_after <= now()
UNION ALL
    -- HARD: a fixture declaring a class no vocabulary entry has is unwritable
    -- (FK), so a row here means the catalogue was bypassed.
    SELECT 'error', 'fixture_class_unknown', fc.fixture_id || ' -> ' || fc.property_class
      FROM fixture_classes fc
     WHERE NOT EXISTS (SELECT 1 FROM property_classes pc WHERE pc.id = fc.property_class)
UNION ALL
    -- HARD: ticket 78. A repeat that had the door and reached nothing. On
    -- the loopback route zero tool runs is the honest answer for a machine
    -- that describes no Agent boundary, and 046 files it deliberately. On
    -- the door route it is not an answer at all: the Program had a fixture
    -- at a reachable address and an Agent that could have dialled it, and a
    -- verdict computed from what that run claimed would be a verdict about
    -- a Playbook that was never given the chance to claim anything.
    SELECT 'error', 'test_run_reached_nothing',
           p.path || ' on ' || r.fixture_id || ' repeat ' || r.repeat_index
           || ' ran behind the door and filed no tool run'
      FROM playbook_test_runs r JOIN playbooks p ON p.id = r.playbook_id
     WHERE r.route = 'door' AND r.tool_runs = 0
UNION ALL
    -- WARNING: stable but no longer testable. Almost always a fixture was
    -- added and the suite has not caught up.
    SELECT 'warning', 'stable_playbook_untested', p.path || ' -> ' || v.reason
      FROM playbooks p
      CROSS JOIN LATERAL playbook_test_verdict(p.id, p.source_sha256) v
     WHERE p.status = 'stable' AND v.verdict = 'untested'
UNION ALL
    -- WARNING: the catalogue's untestable tail -- what "every playbook needs a
    -- test" costs against a catalogue that mostly does not exist yet.
    SELECT 'warning', 'draft_playbook_untestable', p.path || ' -> ' || v.reason
      FROM playbooks p
      CROSS JOIN LATERAL playbook_test_verdict(p.id, p.source_sha256) v
     WHERE p.status = 'draft' AND v.verdict = 'untested'
UNION ALL
    -- WARNING: a real finding outside the playbook's declaration. Never scored
    -- against the playbook; it is a ground-truth gap in the FIXTURE, and the
    -- fixture's owner is the one who has to answer it.
    SELECT 'warning', 'fixture_groundtruth_gap',
           r.fixture_id || ' <- ' || p.path || ' (' || r.out_of_scope
           || ' finding(s) outside its bb:outputs)'
      FROM playbook_test_runs r JOIN playbooks p ON p.id = r.playbook_id
     WHERE r.out_of_scope > 0
UNION ALL
    -- WARNING: test results for a text the card no longer has. R2 makes new
    -- rows impossible, so this is the residue of a re-text -- which is exactly
    -- why the standing does not transfer.
    SELECT 'warning', 'test_run_for_superseded_text',
           p.path || ' -> ' || left(r.playbook_sha256, 12)
      FROM playbook_test_runs r JOIN playbooks p ON p.id = r.playbook_id
     WHERE r.playbook_sha256 <> p.source_sha256
     GROUP BY p.path, r.playbook_sha256
UNION ALL
    -- WARNING: ticket 46. Results graded against a fixture the corpus has moved
    -- past. R5 makes new ones impossible; an old one is a result whose verdict
    -- was decided by text that is no longer the ground truth.
    SELECT 'warning', 'test_run_for_superseded_fixture',
           r.fixture_id || ' -> ' || left(r.fixture_ground_truth, 12)
      FROM playbook_test_runs r JOIN fixtures f ON f.id = r.fixture_id
     WHERE r.fixture_sha256 <> f.source_sha256
        OR r.fixture_ground_truth <> f.ground_truth_sha256
     GROUP BY r.fixture_id, r.fixture_ground_truth
UNION ALL
    -- WARNING: ticket 46. A repeat that recorded no Skill text for a Playbook
    -- that declares Skills. 045's warning one table over, for the same reason:
    -- the result is about an instrument nobody wrote down.
    SELECT 'warning', 'test_run_froze_no_skills', p.path || ' on ' || r.fixture_id
      FROM playbook_test_runs r JOIN playbooks p ON p.id = r.playbook_id
     WHERE EXISTS (SELECT 1 FROM playbook_skills ps WHERE ps.playbook_id = p.id)
       AND NOT EXISTS (SELECT 1 FROM playbook_test_run_skills s WHERE s.run_id = r.id)
     GROUP BY p.path, r.fixture_id;
$$;


-- ---------------------------------------------------------------------------
-- 7. The capability fence learns the third authorizer
-- ---------------------------------------------------------------------------
-- A missing grant fails closed on its own: the door's call raises and the
-- request is refused. What this arm adds is visibility -- a door that has
-- silently stopped being able to ask the fixture address question would answer every
-- evaluation by resolving `<fixture>.localhost`, being told 127.0.0.1 and
-- refusing it, which reads as a broken fixture rather than as a broken fence.
--
-- And the arm below it is the other direction: a Receipt that says `fixture`
-- while nothing says where the fixture was.

CREATE OR REPLACE FUNCTION check_capability_receipt_fence()
RETURNS TABLE(problem text, detail text) LANGUAGE sql STABLE AS $fn$
    SELECT 'proxy_can_insert_receipts', 'rk2_proxy has direct INSERT'
     WHERE has_table_privilege('rk2_proxy', 'receipts', 'INSERT')
    UNION ALL
    SELECT 'allowed_receipt_trigger_missing', 'trigger absent or not ENABLE ALWAYS'
     WHERE NOT EXISTS (SELECT 1 FROM pg_trigger
                        WHERE tgrelid = 'receipts'::regclass
                          AND tgname = 'receipts_allowed_capability' AND tgenabled = 'A')
    UNION ALL
    SELECT 'proxy_identity_writer_missing', 'rk2_proxy cannot execute the Identity fence'
     WHERE NOT has_function_privilege(
               'rk2_proxy',
               'authorize_identity_egress_request(text,text,text,text,integer,text,text)',
               'EXECUTE')
        OR NOT has_function_privilege(
               'rk2_proxy', 'authorize_identity_egress_address(text,text,text,integer,text)',
               'EXECUTE')
        OR NOT has_function_privilege('rk2_proxy', 'open_identity_slot(text,text)', 'EXECUTE')
        OR NOT has_function_privilege(
               'rk2_proxy', 'confirm_identity_slot_open(text,text,uuid,text)', 'EXECUTE')
        OR NOT has_function_privilege(
               'rk2_proxy',
               'record_identity_proxy_exchange(text,jsonb,jsonb,jsonb,text,bigint,jsonb)',
               'EXECUTE')
        OR NOT has_function_privilege(
               'rk2_proxy', 'ensure_proxy_wire_keying(text,bytea,bytea)', 'EXECUTE')
        OR NOT has_function_privilege(
               'rk2_proxy', 'write_blocked_receipt(uuid,jsonb,text)', 'EXECUTE')
        OR NOT has_function_privilege(
               'rk2_proxy', 'authorize_fixture_address(text,text,text,integer)',
               'EXECUTE')
    UNION ALL
    SELECT 'proxy_bypasses_identity_writer', 'rk2_proxy retains an unchecked writer'
     WHERE has_function_privilege('rk2_proxy', 'write_allowed_receipt(text,jsonb)', 'EXECUTE')
        OR has_function_privilege(
               'rk2_proxy', 'record_proxy_exchange(text,jsonb,jsonb)', 'EXECUTE')
        OR has_function_privilege(
               'rk2_proxy', 'record_proxy_exchange(text,jsonb,jsonb,jsonb)', 'EXECUTE')
        OR has_function_privilege(
               'rk2_proxy',
               'authorize_egress_request(text,text,text,text,integer,text,text,text)',
               'EXECUTE')
        OR has_function_privilege(
               'rk2_proxy', 'authorize_egress_address(text,text,text,integer,text)', 'EXECUTE')
        OR has_function_privilege('rk2_proxy', 'provision_identity_slot(uuid,text,bigint,jsonb)',
                                  'EXECUTE')
        OR has_table_privilege('rk2_proxy', 'identity_slots', 'SELECT')
    UNION ALL
    SELECT 'state_can_reach_identity_slots', 'the agent-facing role can reach slot state'
     WHERE has_table_privilege('rk2_state', 'identity_slots', 'SELECT')
        OR has_function_privilege('rk2_state', 'open_identity_slot(text,text)', 'EXECUTE')
        OR has_function_privilege(
               'rk2_state', 'provision_identity_slot(uuid,text,bigint,jsonb)', 'EXECUTE')
    UNION ALL
    SELECT 'unsealed_zero_byte_wire_artifact', a.sha256
      FROM artifacts a
     WHERE a.encrypted AND a.byte_size = 0 AND a.purged_at IS NULL
       AND NOT EXISTS (SELECT 1 FROM artifact_seal s WHERE s.sha256 = a.sha256)
    UNION ALL
    SELECT 'blocked_receipt_answers_with_a_row_id',
           'a refusal would name its record with something no label resolves'
     WHERE pg_get_function_result(
               'write_blocked_receipt(uuid,jsonb,text)'::regprocedure) <> 'text'
    UNION ALL
    SELECT 'stored_transcript_is_unheld',
           'no label in program ' || r.program_id::text || ' names ' || t.sha256
      FROM receipts r
      CROSS JOIN LATERAL (VALUES (r.request_agent_sha), (r.response_agent_sha))
        AS t(sha256)
      JOIN artifacts a ON a.sha256 = t.sha256
     WHERE t.sha256 IS NOT NULL
       AND a.visibility = 'agent_visible'
       AND NOT a.encrypted
       AND a.purged_at IS NULL
       AND NOT EXISTS (SELECT 1 FROM artifact_references x
                        WHERE x.program_id = r.program_id AND x.sha256 = t.sha256)
    UNION ALL
    -- Ticket 78. A Receipt classed `fixture` names a synthetic target this
    -- harness started, and the only thing that can say where one was is the
    -- fixture address the evaluation opened. Without that row the class is the
    -- door's own word for what it dialled, which is the one thing no
    -- Receipt column is allowed to be.
    SELECT 'fixture_receipt_without_an_address',
           'receipt ' || r.id::text || ' is classed fixture at ' || r.host
           || ':' || r.port::text || ', which no fixture address names'
      FROM receipts r
     WHERE r.scope_class = 'fixture'
       AND NOT EXISTS (SELECT 1 FROM fixture_addresses e
                        WHERE e.program_id = r.program_id
                          AND e.host = r.host AND e.port = r.port)
$fn$;


UPDATE standing_checks
   SET note = 'the proxy reaches Identity slots and allowed Receipts only through lease-gated writers; it decides a name, a pinned address and a fixture address only through the definer authorizers; hunter reads and provisioning remain separate; every wire transformation is sealed; a refusal names a Receipt the agent can cite; a stored transcript is held by name; and a Receipt classed fixture names a fixture address that exists'
 WHERE name = 'capability_receipt_fence';


-- ---------------------------------------------------------------------------
-- 8. What each role holds
-- ---------------------------------------------------------------------------
-- Since 66 a function born here is open to PUBLIC and a table is granted to
-- nobody, so both verbs are closed and then declared, and the table is named on
-- the runtime surface to be readable at all.
--
-- The split is the design in one place. The runtime opens a fixture address and can
-- read the row back; the proxy can do neither -- it can only ask the definer
-- what one Program's fixture address is, for a capability it holds, and gets a
-- single address or nothing. Neither role can widen the policy: the writer
-- checks the Program's own scope, and the reader never touches it.

REVOKE ALL ON FUNCTION open_fixture_address(uuid, text, text, integer, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION authorize_fixture_address(text, text, text, integer) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION
    open_fixture_address(uuid, text, text, integer, text) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION
    authorize_fixture_address(text, text, text, integer) TO rk2_proxy;

INSERT INTO runtime_verb_surface (verb, added_by, note) VALUES
    ('open_fixture_address(uuid, text, text, integer, text)', '78',
     'records where an evaluation Program''s fixture is listening, so the door dials the address instead of resolving the name');

INSERT INTO runtime_table_surface (table_name, privilege, added_by) VALUES
    ('fixture_addresses', 'SELECT', '78');

-- The proxy asks the definer and never the table: a role that could select the
-- fixture addresses could enumerate every evaluation running on this machine, and the
-- door has no question that needs more than its own Program's one row.
REVOKE ALL ON TABLE fixture_addresses FROM rk2_proxy, rk2_state, rk2_human;

SELECT apply_state_rls();
SELECT apply_runtime_grants();


-- ---------------------------------------------------------------------------
-- 9. This file's own rules, or it does not finish
-- ---------------------------------------------------------------------------

DO $$
DECLARE n integer; d text;
BEGIN
    IF NOT has_function_privilege(
               'rk2_proxy', 'authorize_fixture_address(text,text,text,integer)', 'EXECUTE') THEN
        RAISE EXCEPTION
            'rk2_proxy cannot call authorize_fixture_address; the door would have no '
            'way to learn where an evaluation put its fixture';
    END IF;
    IF has_table_privilege('rk2_proxy', 'fixture_addresses', 'SELECT') THEN
        RAISE EXCEPTION
            'rk2_proxy can select fixture_addresses; the fixture address question is a '
            'definer function so that one door reads one Program''s one row';
    END IF;
    IF has_function_privilege(
               'rk2_proxy', 'open_fixture_address(uuid,text,text,integer,text)',
               'EXECUTE') THEN
        RAISE EXCEPTION
            'rk2_proxy can open a fixture address; the door would then be able '
            'to write the answer it is about to be given';
    END IF;
    IF has_table_privilege('rk2_state', 'fixture_addresses', 'SELECT') THEN
        RAISE EXCEPTION
            'rk2_state can select fixture_addresses; an agent that can read where '
            'the fixture is has read the harness''s arrangements for grading it';
    END IF;

    -- Both halves of the fourth class, as definitions rather than as intent: a
    -- Receipt may say `fixture`, and a fixture address may not be anywhere but one
    -- private host. A later migration that widens either without meaning to
    -- stops here rather than in a live run.
    IF pg_get_constraintdef((SELECT oid FROM pg_constraint
                              WHERE conrelid = 'receipts'::regclass
                                AND conname = 'receipts_scope_class_check'))
       NOT LIKE '%fixture%' THEN
        RAISE EXCEPTION 'receipts still refuses the fixture class';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conrelid = 'fixture_addresses'::regclass
                      AND conname = 'fixture_addresses_address_is_one_private_host') THEN
        RAISE EXCEPTION
            'the fixture address is unconstrained; a fixture could then be '
            'declared at this machine''s own loopback';
    END IF;

    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_capability_receipt_fence();
    IF n > 0 THEN
        RAISE EXCEPTION 'capability receipt fence broken (% problems): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_program_isolation();
    IF n > 0 THEN
        RAISE EXCEPTION 'program isolation broken (% problems): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_rls_coverage();
    IF n > 0 THEN
        RAISE EXCEPTION 'row level security coverage broken (% problems): %', n, d;
    END IF;
END $$;
