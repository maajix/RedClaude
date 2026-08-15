-- ---------------------------------------------------------------------------
-- 20260815T000000Z__a_test_runs_through_the_replay_lane.sql        (ticket 35)
-- ---------------------------------------------------------------------------
--   008 gave a Test a `spec jsonb`, a Test run a `lane` and an `outcome`, and
--   a Test run's Receipts a table to hang off. Nothing has ever written any of
--   them. `replay` has been in the Lane vocabulary since 007 and no path in the
--   corpus produces a Receipt carrying it, because `write_allowed_receipt` sets
--   `agent` on every Receipt it writes -- so the second of the two lanes that
--   may back an Observation has been unreachable for the whole corpus.
--
--   This file makes it reachable. Four decisions run through everything below.
--
--   The Lane is a property of the capability, not of the caller. A replay is a
--   Tool run like any other -- 031's browser mission established the shape --
--   and what makes it a replay is a row saying which Test it is performing. The
--   door reads that row and writes `replay` on every Receipt the capability
--   produces. Nothing the runtime passes in can name the Lane, which is what
--   makes criterion 3 a property of the schema rather than a discipline.
--
--   The outcome is derived, never supplied. `evaluate_test_assertions` reads
--   the Receipts the run produced and answers holds, refutes or inconclusive
--   from them. A caller cannot name the outcome for the same reason 031's
--   caller cannot name a result digest: an outcome a caller can state is an
--   outcome a caller can make agree.
--
--   A role is planned, not observed. The Test says which of its actions is the
--   baseline, which the variant and which the control; the recorded action
--   copies the word off the plan; the Evidence copies it off the recorded
--   action. Nothing anywhere derives a role from the order rows were written
--   in, which is criterion 4.
--
--   And a Test run row is written once, at the end. 015 made `test_runs`
--   immutable on the reasoning that a run is only recorded after it finished,
--   and that stays true here: `test_replays` is the row that exists while the
--   run is in flight, and the `test_runs` row is what the closing produces.
--
--   What is deliberately not here: a Test action that runs an offline tool.
--   Criterion 1 words it as "request or tool actions", and the two criteria in
--   the same ticket cannot both be met today. 030 gives an offline run a
--   `tool_runs` row of its own -- that is what carries its ceilings, its
--   isolation and its exit -- and a tool whose registry row says
--   `network = 'proxy'` reaches the door under that row, so the Receipts it
--   produces are its own Tool run's. Criterion 6 refuses exactly that: a Test
--   run may not cite a Receipt another Tool run produced. A tool action becomes
--   possible when 030 has a way to perform a tool under a Tool run that already
--   exists, and not before. `kind` is on every action and takes one word today,
--   so the vocabulary widens in one place on the day it does.
-- ---------------------------------------------------------------------------


-- ---------------------------------------------------------------------------
-- 1. What a run may conclude
-- ---------------------------------------------------------------------------
-- Criterion 5 states the three words: holds, refutes, inconclusive. 008 wrote
-- holds, fails, error, and the difference is not spelling. `fails` and
-- `refutes` are one word for one fact. `error` is not `inconclusive`: 007's
-- machine has no `testing -> error` arm, so a run that errored had nowhere to
-- leave the claim, and a Test whose assertions could not be evaluated had no
-- outcome to record at all. The three words below map one-to-one onto the three
-- statuses `testing` may reach, which is what lets section 9 settle a claim
-- without a second judgement about what the run meant.
--
-- The rename is a data migration on an immutable table, so the trigger comes
-- off and goes back on ALWAYS -- 016's required state, and 027's
-- `trigger_not_always` is the check that would report anything less. The
-- `emit_event` trigger is INSERT-only here because `event_table_config`
-- declares `test_runs` immutable, so no Event is skipped by the update.

ALTER TABLE test_runs DISABLE TRIGGER test_runs_immutable;
ALTER TABLE negative_knowledge DISABLE TRIGGER negative_knowledge_immutable;

UPDATE test_runs
   SET outcome = CASE outcome WHEN 'fails' THEN 'refutes'
                              WHEN 'error' THEN 'inconclusive' END
 WHERE outcome IN ('fails', 'error');

-- 034 copies the settling run's word onto the record. Left alone it would be a
-- second vocabulary for one fact, and the copy is what `v_negative_knowledge`
-- shows an operator.
UPDATE negative_knowledge
   SET outcome = CASE outcome WHEN 'fails' THEN 'refutes'
                              WHEN 'error' THEN 'inconclusive' END
 WHERE outcome IN ('fails', 'error');

ALTER TABLE negative_knowledge ENABLE ALWAYS TRIGGER negative_knowledge_immutable;
ALTER TABLE test_runs ENABLE ALWAYS TRIGGER test_runs_immutable;

ALTER TABLE test_runs DROP CONSTRAINT test_runs_outcome_check;
ALTER TABLE test_runs ADD CONSTRAINT test_runs_outcome_check
    CHECK (outcome IN ('holds', 'refutes', 'inconclusive'));

COMMENT ON COLUMN test_runs.outcome IS
    'What the run concluded, derived from its own Receipts by '
    '`evaluate_test_assertions` and never supplied by a caller. `holds` means '
    'every assertion held, `refutes` means one did not, `inconclusive` means '
    'one could not be evaluated -- and the three map onto the three statuses a '
    'Hypothesis in `testing` may reach.';

-- 015's outcome pin on `findings` reads `holds` and is untouched by the rename:
-- a validated Finding cites a run that held, and that word did not change.

-- What each of the three words means everywhere else, in one place. Section 9
-- has to say three things about an outcome -- which polarity its Evidence
-- carries, which status it settles the claim at, and how the Tool run ended --
-- and three switches on one value spread over one function is three chances for
-- a later ticket to widen the vocabulary in two of them.

CREATE FUNCTION rk2_test_outcome(p_outcome text)
RETURNS TABLE (polarity text, settles text, tool_run_status text)
LANGUAGE sql IMMUTABLE AS $fn$
    SELECT m.polarity, m.settles, m.tool_run_status
      FROM (VALUES
              ('holds',        'supports', 'supported',    'success'),
              ('refutes',      'refutes',  'refuted',      'success'),
              -- No polarity: a run that could not evaluate its own assertions
              -- has no statement to make about the target, so section 9 files
              -- no Evidence for it and nothing reads this column.
              ('inconclusive', NULL,       'inconclusive', 'error')
           ) AS m(outcome, polarity, settles, tool_run_status)
     WHERE m.outcome = p_outcome
$fn$;

COMMENT ON FUNCTION rk2_test_outcome(text) IS
    'One outcome read three ways: the polarity its Evidence carries, the status '
    'it settles a claim in `testing` at, and the status its Tool run ends on. '
    'Answers no row for a word that is not an outcome, which is the same '
    'refusal `test_runs_outcome_check` makes.';


-- ---------------------------------------------------------------------------
-- 2. The shape a Test specification has
-- ---------------------------------------------------------------------------
-- Criterion 1. 008 typed the column as `jsonb` and left the shape to whoever
-- wrote one, which is how a Test with no control action, an assertion naming an
-- action that does not exist, or two assertions sharing an identifier all
-- become things the runtime discovers at execution time. The validator below
-- is a CHECK constraint, so they are things nobody can store.
--
-- The digest is the identity. `tests` is immutable already, so "changing any
-- part creates a new Test identity" needs no enforcement against edits -- what
-- it needs is that the digest cannot disagree with the specification it names,
-- which is the second constraint, and that one Hypothesis cannot hold the same
-- specification twice, which is the third. A re-run of a Test is a Test run.

CREATE FUNCTION rk2_test_roles() RETURNS text[]
LANGUAGE sql IMMUTABLE AS $fn$
    SELECT ARRAY['baseline', 'variant', 'control']
$fn$;

COMMENT ON FUNCTION rk2_test_roles() IS
    'The three roles an action may carry, in one place. `hypothesis_evidence` '
    'also admits `context`, which no action may be: a Test action exists to '
    'settle the question, and evidence that is merely context is not something '
    'a Test was written to produce.';

CREATE FUNCTION rk2_test_precondition_kinds() RETURNS text[]
LANGUAGE sql IMMUTABLE AS $fn$
    SELECT ARRAY['scope_holds', 'risk_accepted', 'identity_leased',
                 'budget_allows', 'target_state']
$fn$;

COMMENT ON FUNCTION rk2_test_precondition_kinds() IS
    'The words a precondition may be stated under. Criterion 1 asks for typed '
    'preconditions and a free-form word is not a type: two Tests stating the '
    'same condition as `needs_login` and `logged_in` would be two conditions to '
    'a reader and one to their author. The first four name what '
    '`open_test_replay` decides against canonical state, so a reader can see '
    'which of the stated conditions the machine already checked; '
    '`target_state` is everything only the target can answer, which is why the '
    'detail beside it is prose.';

CREATE FUNCTION rk2_test_cleanup_states() RETURNS text[]
LANGUAGE sql IMMUTABLE AS $fn$
    SELECT ARRAY['done', 'failed', 'skipped']
$fn$;

COMMENT ON FUNCTION rk2_test_cleanup_states() IS
    'What a run may honestly say about its own cleanup: it ran, it tried and '
    'could not, or it never got there. Criterion 5 records the state and this '
    'is where the three words live, so the check on the stored results and the '
    'check in the closing are one rule.';

CREATE FUNCTION rk2_test_assertion_kinds() RETURNS text[]
LANGUAGE sql IMMUTABLE AS $fn$
    SELECT ARRAY['status_equals', 'status_differs', 'body_equals', 'body_differs']
$fn$;

COMMENT ON FUNCTION rk2_test_assertion_kinds() IS
    'Every assertion this runtime can evaluate deterministically, which is '
    'every assertion a Test may state. Each is a comparison over columns the '
    'door writes on a Receipt -- the status line and the digest of what the '
    'agent saw -- so the evaluation reads canonical state and nothing else.';

CREATE FUNCTION rk2_test_request_problem(p_request jsonb, p_position text)
RETURNS text
LANGUAGE plpgsql IMMUTABLE AS $fn$
DECLARE
    v_url text := p_request ->> 'url';
BEGIN
    IF upper(coalesce(p_request ->> 'method', '')) NOT IN
       ('GET', 'HEAD', 'OPTIONS', 'POST', 'PUT', 'PATCH', 'DELETE') THEN
        RETURN p_position || ' states no method this runtime sends';
    END IF;
    IF p_request ->> 'method' <> upper(p_request ->> 'method') THEN
        -- The method is part of the digest, so one spelling of it. A plan
        -- carrying `get` would digest differently from the same plan carrying
        -- `GET` and would describe the same request.
        RETURN p_position || ' states its method in lower case';
    END IF;
    IF v_url IS NULL
       OR v_url !~ '^https?://[a-z0-9.-]+(:[0-9]{1,5})?(/[^\s]*)?$' THEN
        RETURN p_position || ' states no absolute http or https url in canonical form';
    END IF;
    IF length(v_url) > 2000 THEN
        RETURN p_position || ' states a url longer than a url may be';
    END IF;
    -- A path this file resolves one way and the door resolves another is a
    -- request nobody planned: `/public/../admin` is scope-classed as `/public/`
    -- when the plan is checked and reaches `/admin` when it is sent. The scope
    -- is stated over paths, so one spelling of a path, and it is the resolved
    -- one. `%2e` goes with it because a dot the door decodes is a dot.
    IF split_part(regexp_replace(v_url, '^https?://[^/]*', ''), '?', 1)
           ~ '(^|/)\.\.?(/|$)'
       OR v_url ~* '%2e' THEN
        RETURN p_position || ' states a path that resolves somewhere else';
    END IF;
    RETURN NULL;
END $fn$;

COMMENT ON FUNCTION rk2_test_request_problem(jsonb, text) IS
    'The two values every request in a specification carries, checked the same '
    'way wherever one appears. Key sets are the caller''s business because an '
    'action carries three more keys than a setup step does.';

-- And where a well-formed url points, in the four values the scope is stated
-- over and the door writes on a Receipt. Two sections need it -- section 7
-- classes every planned request before one is sent, and section 8 checks that
-- the Receipt it is handed answers the action it is recorded as -- and a second
-- copy of this parse is a second answer to "which port did the plan mean".
--
-- `scope_normalize_host` and not `lower`: the door normalises the host before it
-- classes anything, and a pre-flight that classed `APP.example.com.` under a
-- different rule than the door would answer for a request nobody will make.
--
-- A url that does not parse answers one row of nulls rather than no row, which
-- is what both callers already handle: an unclassifiable request is refused by
-- the scope, and a Receipt is `IS DISTINCT FROM` anything null.

CREATE FUNCTION rk2_test_route(p_url text)
RETURNS TABLE (scheme text, host text, port integer, path text)
LANGUAGE sql IMMUTABLE AS $fn$
    SELECT lower(u[1]),
           scope_normalize_host(u[2]),
           coalesce(u[3]::integer,
                    CASE lower(u[1]) WHEN 'https' THEN 443 ELSE 80 END),
           coalesce(nullif(u[4], ''), '/')
      FROM (SELECT regexp_match(p_url,
                       '^(https?)://([^/:?#]+)(?::([0-9]+))?([^?#]*)') AS u) parsed
$fn$;

COMMENT ON FUNCTION rk2_test_route(text) IS
    'Where a planned request goes: the scheme, the normalised host, the port '
    'the scheme implies when none is stated, and the path, spelled the way the '
    'door spells them. The one parse both the pre-flight and the recording '
    'read.';

CREATE FUNCTION rk2_test_spec_problem(p_spec jsonb) RETURNS text
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
        IF NOT (v_key = ANY (v_parts)) THEN
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

    RETURN NULL;
END $fn$;

COMMENT ON FUNCTION rk2_test_spec_problem(jsonb) IS
    'Criterion 1, as one function so the constraint on `tests` and the refusal '
    'a caller reads are the same rule. Returns the first problem in the '
    'specification, or null when there is none.';

CREATE FUNCTION rk2_test_spec_digest(p_spec jsonb) RETURNS text
LANGUAGE sql IMMUTABLE AS $fn$
    SELECT encode(digest(p_spec::text, 'sha256'), 'hex')
$fn$;

COMMENT ON FUNCTION rk2_test_spec_digest(jsonb) IS
    'The identity of a Test. Over the jsonb rendering, which is canonical: keys '
    'are stored sorted and de-duplicated, so two specifications that are equal '
    'as jsonb digest the same and two that differ anywhere digest differently. '
    'Changing any part of a Test therefore produces a different Test.';

ALTER TABLE tests ADD CONSTRAINT tests_spec_shape_check
    CHECK (rk2_test_spec_problem(spec) IS NULL);

ALTER TABLE tests ADD CONSTRAINT tests_spec_sha256_agrees_check
    CHECK (spec_sha256 = rk2_test_spec_digest(spec));

ALTER TABLE tests ADD CONSTRAINT tests_hypothesis_id_spec_sha256_key
    UNIQUE (hypothesis_id, spec_sha256);

COMMENT ON CONSTRAINT tests_hypothesis_id_spec_sha256_key ON tests IS
    'One Hypothesis holds one copy of a specification. Storing it twice would '
    'make "which Test settled the claim" a question about which row somebody '
    'picked; performing it twice is what a second Test run is for.';


-- ---------------------------------------------------------------------------
-- 3. The run while it is in flight
-- ---------------------------------------------------------------------------
-- 015: a `test_runs` row is written after the run finished, which leaves
-- nothing for the door to bind a capability to while it is running. 031 solved
-- the same problem for a browser mission and the answer is the same here: the
-- in-flight row is an extension of the Tool run that is performing the work,
-- because the status, the times, the task and the credential all live on
-- `tool_runs` already and a copy would be a second answer.
--
-- What this row holds is the two facts the Tool run cannot: which Test is being
-- performed, and -- once it closes -- which Test run came of it.

CREATE TABLE test_replays (
    tool_run_id uuid PRIMARY KEY,
    program_id  uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    test_id     uuid NOT NULL,
    spec_sha256 text NOT NULL CHECK (spec_sha256 ~ '^[0-9a-f]{64}$'),
    started_at  timestamptz NOT NULL DEFAULT now(),
    test_run_id uuid,
    UNIQUE (tool_run_id, program_id),
    FOREIGN KEY (tool_run_id, program_id) REFERENCES tool_runs (id, program_id),
    FOREIGN KEY (test_id, program_id)     REFERENCES tests (id, program_id),
    FOREIGN KEY (test_run_id, program_id) REFERENCES test_runs (id, program_id)
);

COMMENT ON TABLE test_replays IS
    'One execution of a Test, as the extension of the Tool run performing it. '
    'Its existence is what makes the Tool run''s capability replay-bound: the '
    'door reads this table to decide the Lane of every Receipt it writes.';

COMMENT ON COLUMN test_replays.spec_sha256 IS
    'The specification as it stood when the run opened. `tests` is immutable so '
    'it cannot have moved, and pinning it anyway is what lets a reader of a '
    'closed run see which Test identity ran without joining through a row that '
    'a later ticket might learn to supersede.';

COMMENT ON COLUMN test_replays.test_run_id IS
    'Null while the run is in flight. Written once, by `close_test_replay`, in '
    'the transaction that writes the Test run itself.';

CREATE TABLE test_replay_actions (
    tool_run_id uuid NOT NULL,
    ordinal     integer NOT NULL CHECK (ordinal BETWEEN 1 AND 32),
    program_id  uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    role        text NOT NULL CHECK (role = ANY (rk2_test_roles())),
    receipt_id  uuid NOT NULL,
    recorded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tool_run_id, ordinal),
    UNIQUE (receipt_id),
    FOREIGN KEY (tool_run_id, program_id) REFERENCES test_replays (tool_run_id, program_id),
    FOREIGN KEY (receipt_id, program_id)  REFERENCES receipts (id, program_id)
        ON DELETE CASCADE
);

COMMENT ON TABLE test_replay_actions IS
    'Which Receipt answered which planned action, recorded as the run performs '
    'it. `role` is copied off the plan by `record_test_action` and is never '
    'supplied by the caller, so no ordering of these rows can change what a '
    'role means.';

COMMENT ON COLUMN test_replay_actions.receipt_id IS
    'Unique across the table: one Receipt answers one action. Without it a run '
    'could cite the same exchange as its baseline and its variant and produce a '
    'differential against itself.';

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('test_replays',        'program_id', 'program-scoped: the purge root'),
    ('test_replay_actions', 'program_id', 'program-scoped: the purge root'),
    ('test_replay_actions', 'receipt_id',
     'ON DELETE CASCADE to receipts: an action row says which exchange answered it and says nothing without the exchange');

-- Both `covered`, and the covering rows are 022's. A replay IS a Tool run, so
-- `tool_run.proposed` and `tool_run.settled` are the two Events its opening and
-- closing produce -- 031's reason, unchanged. An action row is covered by the
-- Receipt it names: `receipt.recorded` is written in the same transaction and
-- carries the exchange itself, which is the whole of what happened.
INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('test_replays', 'covered',
     'the extension of a Tool run, written with it; the opening and the closing are tool_run.proposed and tool_run.settled', '35'),
    ('test_replay_actions', 'covered',
     'written in the transaction that files the Receipt it names; the Receipt event is the record of what happened', '35');

SELECT attach_event_triggers();

GRANT SELECT, INSERT ON test_replays, test_replay_actions TO rk2_runtime;
GRANT UPDATE (test_run_id) ON test_replays TO rk2_runtime;

-- No UPDATE on an action row for anybody. Which Receipt answered which action
-- is settled when it is written, and a row that could be repointed afterwards
-- would let a run choose its own differential after seeing both answers.
CREATE TRIGGER test_replay_actions_immutable
    BEFORE UPDATE OR DELETE ON test_replay_actions
    FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_purging();


-- ---------------------------------------------------------------------------
-- 4. What a finished run carries
-- ---------------------------------------------------------------------------
-- Criterion 4 asks that a role survive from the action to the Evidence. 008's
-- `test_run_receipts` is the row in the middle of that chain and carried an
-- ordinal and nothing else, so the only thing a reader of a finished run could
-- do with a role was infer it from the order -- which is the inference the
-- criterion exists to forbid.
--
-- NOT NULL with no backfill, deliberately. Nothing in `src/` has ever written
-- this table -- 034 recorded that as a follow-up and it is still true -- so
-- there is no row to carry a role that nobody recorded. An ALTER that refused
-- here would be reporting a row whose role would have to be invented, and
-- inventing one is worse than refusing.

ALTER TABLE test_run_receipts ADD COLUMN role text NOT NULL
    CHECK (role = ANY (rk2_test_roles()));

COMMENT ON COLUMN test_run_receipts.role IS
    'Criterion 4. Copied from the recorded action, which copied it from the '
    'plan. The Evidence rows a run produces copy it from here, so the word an '
    'operator reads on a Finding is the word the Test was written with.';

CREATE FUNCTION rk2_assertion_results_problem(p_results jsonb) RETURNS text
LANGUAGE plpgsql IMMUTABLE AS $fn$
DECLARE
    v_key  text;
    v_item jsonb;
BEGIN
    IF jsonb_typeof(p_results) <> 'object' THEN
        RETURN 'the assertion results are not an object';
    END IF;
    FOR v_key IN SELECT jsonb_object_keys(p_results) LOOP
        IF v_key NOT IN ('assertions', 'failed', 'cleanup') THEN
            RETURN 'the assertion results carry no key named ' || v_key;
        END IF;
    END LOOP;
    IF jsonb_typeof(p_results -> 'assertions') IS DISTINCT FROM 'array' THEN
        RETURN 'the assertion results state no assertions';
    END IF;
    IF jsonb_typeof(p_results -> 'failed') IS DISTINCT FROM 'array' THEN
        RETURN 'the assertion results state no failed identifiers';
    END IF;
    IF NOT (coalesce(p_results ->> 'cleanup', '')
              = ANY (rk2_test_cleanup_states())) THEN
        RETURN 'the assertion results state no cleanup state';
    END IF;
    FOR v_item IN SELECT * FROM jsonb_array_elements(p_results -> 'assertions') LOOP
        IF jsonb_typeof(v_item) <> 'object'
           OR coalesce(v_item ->> 'id', '') = ''
           OR jsonb_typeof(v_item -> 'held') NOT IN ('boolean', 'null') THEN
            RETURN 'an assertion result names no assertion or states no verdict';
        END IF;
    END LOOP;
    FOR v_item IN SELECT * FROM jsonb_array_elements(p_results -> 'failed') LOOP
        IF jsonb_typeof(v_item) <> 'string' THEN
            RETURN 'a failed assertion is named by something other than its identifier';
        END IF;
    END LOOP;
    RETURN NULL;
END $fn$;

COMMENT ON FUNCTION rk2_assertion_results_problem(jsonb) IS
    'Criterion 5''s three facts, as a shape: every assertion with its verdict, '
    'the identifiers of the ones that failed, and what became of the cleanup. '
    'A verdict of null is an assertion that could not be evaluated, which is '
    'what makes the run inconclusive.';

ALTER TABLE test_runs ADD CONSTRAINT test_runs_assertion_results_shape_check
    CHECK (rk2_assertion_results_problem(assertion_results) IS NULL);


-- ---------------------------------------------------------------------------
-- 5. The door learns the replay Lane
-- ---------------------------------------------------------------------------
-- Criterion 3, at the only two places it can be enforced: the function that
-- writes an allowed Receipt, and the trigger that refuses one without a live
-- capability. Both are re-created whole; one arm changes in each.

CREATE FUNCTION rk2_replay_tool() RETURNS text
LANGUAGE sql IMMUTABLE AS $fn$
    SELECT 'mcp__rk2__replay'::text
$fn$;

COMMENT ON FUNCTION rk2_replay_tool() IS
    'The Tool name a replay''s Tool run carries. Under `mcp__rk2__*` in '
    '`tool_risk_classes`, so the gate classes it `constrained` without a new '
    'rule: every network verb inside it goes through the proxy.';

CREATE FUNCTION rk2_capability_lane(p_tool_run_id uuid) RETURNS text
LANGUAGE sql STABLE AS $fn$
    SELECT CASE WHEN EXISTS (SELECT 1 FROM test_replays tp
                              WHERE tp.tool_run_id = p_tool_run_id)
                THEN 'replay' ELSE 'agent' END
$fn$;

COMMENT ON FUNCTION rk2_capability_lane(uuid) IS
    'Which party a capability acts for. A Tool run that is performing a Test is '
    'the runtime replaying it; every other one is an agent acting. The Lane is '
    'read from the Tool run rather than taken from the caller, so no caller can '
    'name it and no Receipt can claim a Lane its capability was not minted for.';

CREATE OR REPLACE FUNCTION write_allowed_receipt(p_capability text, p_receipt jsonb)
RETURNS uuid
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
AS $fn$
DECLARE
    v_auth          record;
    v_receipt       receipts%ROWTYPE;
    v_scope_version integer;
    v_id            uuid;
BEGIN
    IF p_capability IS NULL
       OR coalesce(jsonb_typeof(p_receipt), 'null') <> 'object' THEN
        RAISE EXCEPTION 'egress capability refused' USING ERRCODE = '23514';
    END IF;
    IF position(p_capability IN p_receipt::text) > 0 THEN
        RAISE EXCEPTION 'receipt payload contains protected capability'
            USING ERRCODE = '23514';
    END IF;

    SELECT * INTO v_auth FROM resolve_egress_capability(p_capability);
    IF NOT FOUND THEN
        RAISE EXCEPTION 'egress capability refused' USING ERRCODE = '23514';
    END IF;
    SELECT scope_version INTO v_scope_version
      FROM programs WHERE id = v_auth.program_id;

    v_receipt := jsonb_populate_record(NULL::receipts, p_receipt);
    v_receipt.id := uuidv7();
    v_receipt.program_id := v_auth.program_id;
    v_receipt.label := '';
    v_receipt.tool_run_id := v_auth.tool_run_id;
    -- The one changed line. `agent` was correct while the only holder of a
    -- capability was a subagent; a replay holds one too, and which of them is
    -- acting is a fact about the Tool run rather than about this call.
    v_receipt.lane := rk2_capability_lane(v_auth.tool_run_id);
    v_receipt.decision := 'allowed';
    v_receipt.scope_version := v_scope_version;
    v_receipt.ts_arrival := coalesce(v_receipt.ts_arrival, clock_timestamp());
    v_receipt.intercepted := coalesce(v_receipt.intercepted, true);

    PERFORM set_actor('runtime');
    INSERT INTO receipts (
        id, program_id, label, tool_run_id, lane, decision, reason,
        identity_entity_id, identity_tls_cert_sha256,
        method, scheme, host, port, path, query_sha256,
        pinned_ips, status_code, ts_arrival, ts_egress, waited_ms,
        request_agent_sha, request_wire_sha, response_agent_sha,
        response_wire_sha, notes, scope_version, scope_class, intercepted,
        alpn_pin_mode, agent_tls_version, agent_cipher, agent_alpn,
        agent_cert_sha256, agent_cert_issuer, agent_cert_subject,
        agent_cert_not_after, wire_tls_version, wire_cipher, wire_alpn,
        wire_cert_sha256, wire_cert_issuer, wire_cert_subject,
        wire_cert_not_after, wire_sni, wire_chain_verified,
        wire_hostname_verified, interception_ca_id
    ) VALUES (
        v_receipt.id, v_receipt.program_id, v_receipt.label,
        v_receipt.tool_run_id, v_receipt.lane, v_receipt.decision,
        v_receipt.reason, v_receipt.identity_entity_id,
        v_receipt.identity_tls_cert_sha256, v_receipt.method,
        v_receipt.scheme, v_receipt.host, v_receipt.port, v_receipt.path,
        v_receipt.query_sha256, v_receipt.pinned_ips, v_receipt.status_code,
        v_receipt.ts_arrival, v_receipt.ts_egress, v_receipt.waited_ms,
        v_receipt.request_agent_sha, v_receipt.request_wire_sha,
        v_receipt.response_agent_sha, v_receipt.response_wire_sha,
        v_receipt.notes, v_receipt.scope_version, v_receipt.scope_class,
        v_receipt.intercepted, v_receipt.alpn_pin_mode,
        v_receipt.agent_tls_version, v_receipt.agent_cipher,
        v_receipt.agent_alpn, v_receipt.agent_cert_sha256,
        v_receipt.agent_cert_issuer, v_receipt.agent_cert_subject,
        v_receipt.agent_cert_not_after, v_receipt.wire_tls_version,
        v_receipt.wire_cipher, v_receipt.wire_alpn,
        v_receipt.wire_cert_sha256, v_receipt.wire_cert_issuer,
        v_receipt.wire_cert_subject, v_receipt.wire_cert_not_after,
        v_receipt.wire_sni, v_receipt.wire_chain_verified,
        v_receipt.wire_hostname_verified, v_receipt.interception_ca_id
    )
    RETURNING id INTO v_id;
    RETURN v_id;
END $fn$;

-- The refusals go with the answers. `write_blocked_receipt` derived the Lane
-- from the purpose alone -- control plane or agent -- which was complete while
-- an agent was the only party holding a capability. A replay holds one too, so
-- a request of its own that the door refuses was landing on the agent Lane
-- under the replay's own Tool run: 042's misattribution, in the one direction
-- nobody had a reason to look at. The Lane is derived here from the same Tool
-- run for the same reason it is derived in `write_allowed_receipt`, and a
-- refusal that resolved to no capability at all stays `agent`, because
-- `rk2_capability_lane` answers `agent` for a Tool run it cannot find.
--
-- Two lines change. Everything else is verbatim from
-- `20260811T230000Z__a_halt_is_named_in_the_refusal_it_causes.sql`.
CREATE OR REPLACE FUNCTION write_blocked_receipt(
    p_program uuid,
    p_receipt jsonb,
    p_capability text DEFAULT NULL
) RETURNS text LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    v_receipt receipts%ROWTYPE;
    v_label   text;
    v_tool_run_id uuid;
    v_purpose text;
BEGIN
    IF p_program IS DISTINCT FROM rk2_program()
       OR coalesce(jsonb_typeof(p_receipt), 'null') <> 'object' THEN
        RAISE EXCEPTION 'blocked receipt refused' USING ERRCODE = '23514';
    END IF;
    IF p_capability IS NOT NULL
       AND position(p_capability IN p_receipt::text) > 0 THEN
        RAISE EXCEPTION 'receipt payload contains protected capability'
            USING ERRCODE = '23514';
    END IF;
    IF p_capability IS NOT NULL THEN
        SELECT a.tool_run_id INTO v_tool_run_id
          FROM resolve_egress_capability(p_capability) a;
    END IF;

    v_receipt := jsonb_populate_record(NULL::receipts, p_receipt);
    v_receipt.id := uuidv7();
    v_receipt.program_id := p_program;
    v_receipt.label := '';
    v_receipt.tool_run_id := v_tool_run_id;
    -- The caller states a purpose, never a lane: who acted is derived from what
    -- the request was for. A capability is the agent's, so it settles both.
    v_purpose := CASE WHEN p_capability IS NULL
                           AND p_receipt ->> 'purpose' = 'control_plane'
                      THEN 'control_plane' ELSE 'target_traffic' END;
    v_receipt.purpose := v_purpose;
    -- The first changed line.
    v_receipt.lane := CASE WHEN v_purpose = 'control_plane'
                           THEN 'proxy_internal'
                           ELSE rk2_capability_lane(v_tool_run_id) END;
    v_receipt.decision := 'blocked';
    v_receipt.scope_version := CASE WHEN v_purpose = 'control_plane' THEN NULL
        ELSE (SELECT scope_version FROM programs WHERE id=p_program) END;
    v_receipt.scope_class := CASE WHEN v_purpose = 'control_plane'
        THEN 'control_plane' ELSE coalesce(v_receipt.scope_class, 'denied') END;
    v_receipt.ts_arrival := coalesce(v_receipt.ts_arrival, clock_timestamp());
    v_receipt.intercepted := coalesce(v_receipt.intercepted, true);

    -- Which of the things that resolve to no capability this one was. The door
    -- cannot tell -- it holds no read on `program_halts`, deliberately, and the
    -- refusal it caught carries one SQLSTATE and one message for all of them --
    -- so the answer is written here, where the Program is already known and the
    -- Halt is one row away. The control plane is excluded because it presents no
    -- capability: a Halt is not what refused it, whatever it says.
    --
    -- The second changed line. A Halt lands mid-run as readily as between runs,
    -- and the replay whose next request it refuses is owed the same name for it.
    v_receipt.reason := coalesce(v_receipt.reason, 'capability refused');
    IF v_receipt.lane IN ('agent', 'replay')
       AND v_receipt.reason = 'capability refused'
       AND EXISTS (SELECT 1 FROM program_halts h
                    WHERE h.program_id = p_program AND h.status = 'halted') THEN
        v_receipt.reason := 'program halted';
    END IF;

    PERFORM set_actor('runtime');
    INSERT INTO receipts (
        id, program_id, label, tool_run_id, lane, purpose, decision, reason,
        identity_entity_id, method, scheme, host, port, path, query_sha256,
        pinned_ips, status_code, ts_arrival, ts_egress, waited_ms, notes,
        retry_after, scope_version, scope_class, intercepted
    ) VALUES (
        v_receipt.id, v_receipt.program_id, v_receipt.label,
        v_receipt.tool_run_id, v_receipt.lane, v_receipt.purpose,
        v_receipt.decision, v_receipt.reason,
        v_receipt.identity_entity_id, v_receipt.method, v_receipt.scheme,
        v_receipt.host, v_receipt.port, v_receipt.path,
        v_receipt.query_sha256, v_receipt.pinned_ips, v_receipt.status_code,
        v_receipt.ts_arrival, v_receipt.ts_egress, v_receipt.waited_ms,
        v_receipt.notes, v_receipt.retry_after, v_receipt.scope_version,
        v_receipt.scope_class, v_receipt.intercepted
    )
    -- The trigger's word for the row, not the function's. Read back rather than
    -- recomputed: `free_label` may skip a taken name, so the only value certain
    -- to be on the row is the one the insert returns.
    RETURNING label INTO v_label;
    RETURN v_label;
END $fn$;

COMMENT ON FUNCTION write_blocked_receipt(uuid,jsonb,text) IS
  'Writes only blocked receipts, on the Lane of the capability that was '
  'presented or the harness''s own control-plane purpose; authority fields and '
  'the name of a Halt are derived, a valid capability is used only for '
  'attribution, and the return value is the Receipt label the agent may cite.';

-- And the Halt check goes with it. Its arm reads the refusals a Halt caused and
-- reports any that still call themselves a lapsed capability; written against
-- `lane = 'agent'`, it would stop seeing a replay's refusals the moment the
-- line above starts marking them. Re-created for that one condition; verbatim
-- otherwise.
CREATE OR REPLACE FUNCTION check_program_halt()
RETURNS TABLE(problem text, detail text)
LANGUAGE sql STABLE AS $fn$
    SELECT 'human_cannot_connect', 'rk2_human cannot connect to this database'
     WHERE NOT has_database_privilege('rk2_human', current_database(), 'CONNECT')
    UNION ALL
    SELECT 'human_cannot_use_schema', 'rk2_human cannot use the public schema'
     WHERE NOT has_schema_privilege('rk2_human', 'public', 'USAGE')
    UNION ALL
    SELECT 'human_cannot_change_halt', 'rk2_human cannot execute both Halt verbs'
     WHERE NOT has_function_privilege('rk2_human', 'halt_program(uuid,text)', 'EXECUTE')
        OR NOT has_function_privilege(
               'rk2_human', 'clear_program_halt(uuid,text)', 'EXECUTE')
    UNION ALL
    SELECT 'runtime_can_halt', 'rk2_runtime can execute halt_program'
     WHERE has_function_privilege('rk2_runtime', 'halt_program(uuid,text)', 'EXECUTE')
    UNION ALL
    SELECT 'runtime_can_clear_halt', 'rk2_runtime can execute clear_program_halt'
     WHERE has_function_privilege('rk2_runtime', 'clear_program_halt(uuid,text)', 'EXECUTE')
    UNION ALL
    SELECT 'proxy_can_change_halt', 'rk2_proxy can change Program Halt state'
     WHERE has_function_privilege('rk2_proxy', 'halt_program(uuid,text)', 'EXECUTE')
        OR has_function_privilege('rk2_proxy', 'clear_program_halt(uuid,text)', 'EXECUTE')
    UNION ALL
    -- The row itself. DELETE above all: the actor-kind guard is a BEFORE INSERT
    -- OR UPDATE trigger, so it never sees a delete, and a deleted Halt is an
    -- absent Halt -- which is what `resolve_egress_capability` reads.
    --
    -- INSERT is not asked, and is not revoked either: the guard does fire on it,
    -- one Program has one Halt row, and an insert cannot lift a Halt that is
    -- already there.
    SELECT 'halt_row_writable',
           h.grantee || ' holds ' || h.privilege_type || ' on program_halts'
      FROM (
        SELECT g.grantee, v.privilege_type
          FROM (VALUES ('UPDATE'), ('DELETE')) AS v(privilege_type),
               (VALUES ('rk2_runtime'), ('rk2_proxy'), ('rk2_state')) AS g(grantee)
         WHERE has_table_privilege(g.grantee, 'program_halts', v.privilege_type)
      ) h
    UNION ALL
    SELECT 'allowed_receipt_during_halt', r.label
      FROM receipts r JOIN program_halts h ON h.program_id = r.program_id
     WHERE h.status = 'halted' AND r.decision = 'allowed' AND r.ts_arrival >= h.changed_at
    UNION ALL
    SELECT 'halt_refusal_reads_as_a_lapsed_capability', r.label
      FROM receipts r JOIN program_halts h ON h.program_id = r.program_id
     WHERE h.status = 'halted' AND r.decision = 'blocked'
       AND r.lane IN ('agent', 'replay')
       AND r.ts_arrival >= h.changed_at AND r.reason = 'capability refused';
$fn$;

-- And the trigger that holds an allowed Receipt to a live capability. It read
-- `NEW.lane = 'agent'`, which was the whole of the allowed surface when it was
-- written and is now half of it: a `replay` Receipt would have skipped every
-- one of these checks. The body below is verbatim apart from that condition,
-- because every check in it is about the Tool run behind the capability and is
-- as true of a replay as of an agent.
CREATE OR REPLACE FUNCTION enforce_allowed_receipt_capability() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    IF NEW.lane IN ('agent', 'replay') AND NEW.decision = 'allowed'
       AND NOT EXISTS (
           SELECT 1
             FROM tool_runs tr
             JOIN programs p ON p.id = tr.program_id AND p.closed_at IS NULL
             JOIN agent_runs ar ON ar.id = tr.agent_run_id AND ar.program_id = tr.program_id
             LEFT JOIN tasks t ON t.id = tr.task_id AND t.program_id = tr.program_id
            WHERE tr.id = NEW.tool_run_id
              AND tr.program_id = NEW.program_id
              AND NOT EXISTS (SELECT 1 FROM program_halts h
                               WHERE h.program_id = tr.program_id AND h.status = 'halted')
              AND tr.status = 'running' AND tr.decision = 'allow'
              AND tr.egress_token_sha256 IS NOT NULL
              AND tr.egress_token_expires_at > clock_timestamp()
              AND ar.finished_at IS NULL
              AND ((tr.task_id IS NULL AND ar.task_id IS NULL)
                   OR (tr.task_id IS NOT NULL AND ar.task_id = tr.task_id
                       AND t.status IN ('claimed', 'running')
                       AND t.lease_expires_at > clock_timestamp()))
              AND (
                  (coalesce(tr.args ->> 'identity_slot', '') = ''
                   AND NEW.identity_entity_id IS NULL)
                  OR EXISTS (
                      SELECT 1 FROM identities i
                      JOIN identity_slots s ON s.identity_entity_id = i.entity_id
                      JOIN identity_leases l
                        ON l.identity_entity_id = i.entity_id
                       AND l.program_id = i.program_id
                       AND l.holder_agent_run_id = ar.id
                       AND l.released_at IS NULL
                       AND l.expires_at > clock_timestamp()
                     WHERE i.entity_id = NEW.identity_entity_id
                       AND i.program_id = NEW.program_id
                       AND i.slot_name = tr.args ->> 'identity_slot'
                       AND i.invalidated_at IS NULL
                  )
              )
       ) THEN
        RAISE EXCEPTION
            'allowed % receipt lacks a live authorized capability and Identity',
            NEW.lane
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $fn$;

-- The two arms of the door that dispatch on the Tool name. 031 wrote both and
-- its reasoning carries over unchanged.
--
-- The Identity arm listed the two tools whose capability names a slot. A replay
-- names one too, and left out of the list it would hold a capability that could
-- borrow any Identity the Program has -- which is the difference between
-- selecting an Identity and being able to use somebody else's.
--
-- The method arm splits by whether the Tool run declared one method or a set. A
-- replay is the browser's case: its plan derives the set of methods its actions
-- use, and a Test that only reads therefore holds a capability that cannot POST.
CREATE OR REPLACE FUNCTION authorize_egress_request(
    p_capability text,
    p_method     text,
    p_protocol   text,
    p_host       text,
    p_port       integer,
    p_path_raw   text,
    p_path_norm  text,
    p_identity   text DEFAULT NULL)
RETURNS TABLE (program_id uuid, tool_run_id uuid, scope_version integer,
               scope_class text)
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public
AS $fn$
DECLARE
    v_auth    record;
    v_version integer;
    v_class   text;
    v_tool    text;
    v_args    jsonb;
    v_method  text;
BEGIN
    SELECT * INTO v_auth FROM resolve_egress_capability(p_capability);
    IF NOT FOUND THEN
        RAISE EXCEPTION 'egress capability refused' USING ERRCODE = '23514';
    END IF;
    SELECT tr.tool, tr.args INTO v_tool, v_args
      FROM tool_runs tr WHERE tr.id = v_auth.tool_run_id;
    v_method := upper(coalesce(p_method, 'GET'));

    -- The canonical form, asserted rather than assumed. Each of these is a
    -- spelling the compiler's own canonicaliser cannot emit, so a request
    -- carrying one did not come through it.
    IF p_protocol IS NULL OR p_protocol NOT IN ('http', 'https') THEN
        RAISE EXCEPTION 'egress request states no known protocol'
            USING ERRCODE = '23514';
    END IF;
    IF p_host IS NULL OR scope_normalize_host(p_host) IS DISTINCT FROM p_host THEN
        RAISE EXCEPTION 'egress request states a host that is not in canonical form'
            USING ERRCODE = '23514';
    END IF;
    IF p_port IS NULL OR p_port < 1 OR p_port > 65535 THEN
        RAISE EXCEPTION 'egress request states no port in 1-65535'
            USING ERRCODE = '23514';
    END IF;
    IF p_path_raw IS NULL OR NOT starts_with(p_path_raw, '/')
       OR p_path_norm IS NULL OR NOT starts_with(p_path_norm, '/') THEN
        RAISE EXCEPTION 'egress request states a path that is not absolute'
            USING ERRCODE = '23514';
    END IF;
    -- A normalised path with a dot segment left in it is not normalised, and
    -- passing the raw spelling twice is exactly how 039 authorised
    -- `/public/../admin` under a rule that covers `/public`.
    IF p_path_norm ~ '(^|/)\.\.?(/|$)' THEN
        RAISE EXCEPTION 'egress request states a normalised path that still traverses'
            USING ERRCODE = '23514';
    END IF;

    -- Decided against the CURRENT policy and the request that actually arrived,
    -- not against the arguments that minted the capability. Subresources and
    -- redirects deliberately share one capability (§7); each still earns its own
    -- verdict, which is what makes sharing safe.
    SELECT p.scope_version INTO v_version
      FROM programs p WHERE p.id = v_auth.program_id;
    SELECT s.scope_class INTO v_class
      FROM scope_class_of(v_auth.program_id, v_version,
                          p_host, p_port, p_path_raw, p_path_norm,
                          p_protocol, 'request') s;
    IF coalesce(v_class, 'denied') NOT IN ('target', 'egress_support') THEN
        RAISE EXCEPTION 'egress request is outside current scope'
            USING ERRCODE = '23514';
    END IF;
    IF v_method <> 'CONNECT'
       AND v_tool IN ('mcp__rk2__net_request', rk2_browser_tool(), rk2_replay_tool())
       AND coalesce(p_identity, '') IS DISTINCT FROM
           coalesce(v_args ->> 'identity_slot', '') THEN
        RAISE EXCEPTION 'egress identity does not match authorized tool run'
            USING ERRCODE = '23514';
    END IF;
    IF v_tool IN (rk2_browser_tool(), rk2_replay_tool()) THEN
        -- CONNECT is exempt for ticket 10's reason: no tunnel is opened at all,
        -- so there is no request for a declared method to describe.
        IF v_method <> 'CONNECT'
           AND NOT (v_method = ANY (ARRAY(SELECT jsonb_array_elements_text(
                        coalesce(v_args -> 'methods', '[]'::jsonb))))) THEN
            RAISE EXCEPTION 'egress method is not one this plan derived'
                USING ERRCODE = '23514';
        END IF;
    -- The method the Tool run declared binds every request that could change
    -- something, and only those. §7 has subresources and redirects sharing one
    -- capability, and both arrive as GET whatever the declared method was: a
    -- page authorized as a POST pulls its scripts with GETs, and a 303 turns the
    -- POST itself into one. Refusing those would make the sharing unusable while
    -- protecting nothing, because a safe method is the one thing a caller who
    -- already holds the capability gains nothing by substituting. Anything
    -- outside the safe set is matched exactly.
    ELSIF v_method NOT IN ('GET', 'HEAD', 'OPTIONS', 'CONNECT')
       AND upper(coalesce(v_args ->> 'method', 'GET')) IS DISTINCT FROM v_method THEN
        RAISE EXCEPTION 'egress method does not match authorized tool run'
            USING ERRCODE = '23514';
    END IF;

    RETURN QUERY SELECT v_auth.program_id, v_auth.tool_run_id,
                        v_version, v_class;
END $fn$;


-- ---------------------------------------------------------------------------
-- 6. Opening one
-- ---------------------------------------------------------------------------
-- Criterion 2, in order: the Program is not Halted, the claim is testable, no
-- other replay of it is in flight, every url the plan names is in scope, the
-- Identity slot is leased by this run, and the budget admits the work. Then the
-- rows, then the gate -- `authorize_tool_run` is what classes the risk and
-- mints the capability, and it is called here rather than left to the caller so
-- that "verified before the Hypothesis moves" is a property of one function.
--
-- The Hypothesis does not move here. It moves when the first action produces a
-- Receipt, because 007 requires a Receipt for `testable -> testing` and at this
-- point no request has been made. Everything this function checks is therefore
-- checked before the move, which is what the criterion asks.

CREATE FUNCTION open_test_replay(
        p_agent_run_id  uuid,
        p_test_id       uuid,
        p_identity_slot text DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p          uuid := rk2_program_required();
    v_run      agent_runs%ROWTYPE;
    v_test     tests%ROWTYPE;
    v_status   text;
    v_refusal  text;
    v_action   jsonb;
    v_route    record;
    v_class    text;
    v_methods  text[] := '{}';
    v_id       uuid;
    v_label    text;
    v_gate     jsonb;
BEGIN
    SELECT * INTO v_run FROM agent_runs
     WHERE id = p_agent_run_id AND program_id = p;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'agent run % is not a run of this Program', p_agent_run_id
            USING ERRCODE = '23503';
    END IF;
    IF v_run.finished_at IS NOT NULL THEN
        RAISE EXCEPTION 'agent run % has already ended', v_run.label
            USING ERRCODE = '23514';
    END IF;

    IF EXISTS (SELECT 1 FROM program_halts h
                WHERE h.program_id = p AND h.status = 'halted') THEN
        RAISE EXCEPTION 'the Program is Halted and may not start new work'
            USING ERRCODE = '42501',
                  HINT = 'rk resume lifts the Halt';
    END IF;

    SELECT * INTO v_test FROM tests WHERE id = p_test_id AND program_id = p;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'test % is not a Test of this Program', p_test_id
            USING ERRCODE = '23503';
    END IF;

    -- The claim has to be waiting for exactly this. A claim already in
    -- `testing` is one another replay is performing; anything else is a claim
    -- 007's machine will refuse to move when the first Receipt lands, and
    -- refusing it now means no request is made rather than one that is made and
    -- then cannot be recorded.
    SELECT status INTO v_status FROM hypotheses WHERE id = v_test.hypothesis_id
       FOR UPDATE;
    IF v_status <> 'testable' THEN
        RAISE EXCEPTION 'hypothesis is % and a Test may only be run against a testable claim',
            v_status USING ERRCODE = '23514';
    END IF;

    IF EXISTS (
        SELECT 1 FROM test_replays tp
          JOIN tool_runs tr ON tr.id = tp.tool_run_id
          JOIN tests te     ON te.id = tp.test_id
         WHERE te.hypothesis_id = v_test.hypothesis_id
           AND tr.status = 'running') THEN
        RAISE EXCEPTION 'a replay of this claim is already in flight'
            USING ERRCODE = '23514';
    END IF;

    -- The Identity is named once for the whole run and resolved by the door.
    -- Checked now so a run holding a slot it does not lease is refused before
    -- anything is sent, and checked again on every request by
    -- `resolve_egress_identity`, which is the one that counts.
    IF p_identity_slot IS NOT NULL THEN
        IF NOT EXISTS (
            SELECT 1 FROM identities i
              JOIN identity_leases l
                ON l.identity_entity_id = i.entity_id
               AND l.program_id = i.program_id
               AND l.holder_agent_run_id = v_run.id
               AND l.released_at IS NULL
               AND l.expires_at > clock_timestamp()
             WHERE i.program_id = p
               AND i.slot_name = p_identity_slot
               AND i.invalidated_at IS NULL) THEN
            RAISE EXCEPTION 'Identity lease refused' USING ERRCODE = '23514';
        END IF;
    END IF;

    -- A budget is a property of a Task, so a run carrying none has none to
    -- consult. That is not a way past the criterion: 025 puts the ceiling on
    -- the Task, and a run without one holds no Task lease either, which is what
    -- `enforce_allowed_receipt_capability` requires before the door may write
    -- an allowed Receipt at all. Such a run is refused a Receipt rather than a
    -- budget, one request later.
    IF v_run.task_id IS NOT NULL THEN
        SELECT budget_refusal_for(t.*) INTO v_refusal
          FROM tasks t WHERE t.id = v_run.task_id;
        IF v_refusal IS NOT NULL THEN
            RAISE EXCEPTION 'the budget refuses this replay: %', v_refusal
                USING ERRCODE = '23514';
        END IF;
    END IF;

    -- Every request the plan will make, scope-classed before one is sent. The
    -- setup and the cleanup are held to the same rule as the actions: a
    -- cleanup step pointing outside the scope is a request the door would
    -- refuse, at the moment the run is least able to do anything about it.
    FOR v_action IN
        SELECT * FROM jsonb_array_elements(
            (v_test.spec -> 'actions') || (v_test.spec -> 'setup')
                                       || (v_test.spec -> 'cleanup'))
    LOOP
        SELECT * INTO v_route FROM rk2_test_route(v_action ->> 'url');
        SELECT s.scope_class INTO v_class
          FROM programs pr
          CROSS JOIN LATERAL scope_class_of(
                pr.id, pr.scope_version, v_route.host, v_route.port,
                v_route.path, v_route.path, v_route.scheme, 'request') s
         WHERE pr.id = p;
        IF coalesce(v_class, 'denied') NOT IN ('target', 'egress_support') THEN
            RAISE EXCEPTION 'the Test reaches outside the current scope: %',
                v_action ->> 'url'
                USING ERRCODE = '42501',
                      HINT = 'the door would refuse it; the run is refused instead';
        END IF;
        IF NOT (upper(v_action ->> 'method') = ANY (v_methods)) THEN
            v_methods := array_append(v_methods, upper(v_action ->> 'method'));
        END IF;
    END LOOP;

    PERFORM set_actor('runtime');
    INSERT INTO tool_runs
        (program_id, agent_run_id, task_id, tool, args, status, transport)
    VALUES
        (p, v_run.id, v_run.task_id, rk2_replay_tool(),
         jsonb_build_object('identity_slot', p_identity_slot,
                            'methods', to_jsonb(v_methods),
                            'test', v_test.label,
                            'spec_sha256', v_test.spec_sha256),
         'running', 'runtime')
    RETURNING id, label INTO v_id, v_label;

    -- Before the gate, and that ordering is the whole of criterion 3: the row
    -- that makes this Tool run a replay has to exist by the time a capability
    -- does, or the first Receipt would be written into the agent Lane.
    INSERT INTO test_replays (tool_run_id, program_id, test_id, spec_sha256)
    VALUES (v_id, p, v_test.id, v_test.spec_sha256);

    v_gate := authorize_tool_run(v_id);

    RETURN v_gate || jsonb_build_object(
        'tool_run_id', v_id,
        'tool_run', v_label,
        'test', v_test.label,
        'spec_sha256', v_test.spec_sha256,
        'identity_slot', p_identity_slot,
        'methods', to_jsonb(v_methods),
        'preconditions', v_test.spec -> 'preconditions',
        'setup', v_test.spec -> 'setup',
        'actions', v_test.spec -> 'actions',
        'cleanup', v_test.spec -> 'cleanup');
END $fn$;

COMMENT ON FUNCTION open_test_replay(uuid, uuid, text) IS
    'Verify one Test against scope, risk, the Identity lease and the budget, '
    'record the row that makes its Tool run a replay, and answer with the plan '
    'and the capability. Every refusal is a raise: a Halt, a claim that is not '
    'testable, a claim already being replayed, a url outside the scope, a slot '
    'this run does not hold, and a budget that will not carry the work.';


-- ---------------------------------------------------------------------------
-- 7. Performing one
-- ---------------------------------------------------------------------------
-- One action at a time, each naming the Receipt the door wrote for it. The role
-- is not a parameter: it is read out of the plan by ordinal, which is what
-- keeps a role from being something the runtime decides after seeing the
-- answer.
--
-- This is also where the claim moves to `testing`. 007 requires a Receipt for
-- that transition -- "only the tool runtime may start a test, and only with a
-- receipt" -- and the first action is the first moment one exists.

CREATE FUNCTION record_test_action(
        p_tool_run_id uuid,
        p_ordinal     integer,
        p_receipt     text)
RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p          uuid := rk2_program_required();
    v_replay   test_replays%ROWTYPE;
    v_run      tool_runs%ROWTYPE;
    v_spec     jsonb;
    v_action   jsonb;
    v_receipt  receipts%ROWTYPE;
    v_test     tests%ROWTYPE;
    v_first    boolean;
    v_route    record;
BEGIN
    SELECT tp.* INTO v_replay FROM test_replays tp
     WHERE tp.tool_run_id = p_tool_run_id AND tp.program_id = p
       FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'tool run % is not a replay of this Program', p_tool_run_id
            USING ERRCODE = '23503';
    END IF;
    SELECT * INTO v_run FROM tool_runs WHERE id = p_tool_run_id;
    IF v_run.status <> 'running' THEN
        RAISE EXCEPTION 'replay % was already closed as %', v_run.label, v_run.status
            USING ERRCODE = '23514';
    END IF;

    SELECT * INTO v_test FROM tests WHERE id = v_replay.test_id;
    v_spec := v_test.spec;
    v_action := v_spec -> 'actions' -> (p_ordinal - 1);
    IF v_action IS NULL THEN
        RAISE EXCEPTION 'this Test performs no action %', p_ordinal
            USING ERRCODE = '22023';
    END IF;

    SELECT * INTO v_receipt FROM receipts
     WHERE label = p_receipt AND program_id = p;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'no receipt named % in this Program', p_receipt
            USING ERRCODE = '23503';
    END IF;
    -- Criterion 6's second refusal, at the first place it can be made: a
    -- Receipt some other Tool run produced is not this run's evidence, whatever
    -- Lane it carries.
    IF v_receipt.tool_run_id IS DISTINCT FROM p_tool_run_id THEN
        RAISE EXCEPTION 'receipt % was not produced by this replay', p_receipt
            USING ERRCODE = '23514';
    END IF;
    IF v_receipt.lane <> 'replay' THEN
        RAISE EXCEPTION 'receipt % is lane % and a Test run is performed in the replay Lane',
            p_receipt, v_receipt.lane USING ERRCODE = '23514';
    END IF;

    -- And the Receipt has to be the answer to the action it is being recorded
    -- as. Everything above it is satisfied by any Receipt this replay produced:
    -- a setup request, or the answer to a different action. An assertion names
    -- an action and is evaluated against whatever Receipt sits under it, so a
    -- run that could record action 3's answer as action 2 could produce a
    -- differential out of one exchange and a plan nobody wrote. The comparison
    -- is over what the plan states and the scope is stated over -- the method,
    -- the scheme, the host, the port and the path. The query is not compared
    -- because only its digest is on the Receipt, over a normalisation the door
    -- owns.
    SELECT * INTO v_route FROM rk2_test_route(v_action ->> 'url');
    IF v_receipt.method IS DISTINCT FROM upper(v_action ->> 'method')
       OR v_receipt.scheme IS DISTINCT FROM v_route.scheme
       OR v_receipt.host   IS DISTINCT FROM v_route.host
       OR v_receipt.port   IS DISTINCT FROM v_route.port
       OR v_receipt.path   IS DISTINCT FROM v_route.path THEN
        RAISE EXCEPTION
            'receipt % answers % %, and action % states % %',
            p_receipt, v_receipt.method,
            v_receipt.scheme || '://' || v_receipt.host || v_receipt.path,
            p_ordinal, upper(v_action ->> 'method'), v_action ->> 'url'
            USING ERRCODE = '23514';
    END IF;

    SELECT NOT EXISTS (SELECT 1 FROM test_replay_actions a
                        WHERE a.tool_run_id = p_tool_run_id)
      INTO v_first;

    PERFORM set_actor('runtime');
    INSERT INTO test_replay_actions
        (tool_run_id, ordinal, program_id, role, receipt_id)
    VALUES (p_tool_run_id, p_ordinal, p, v_action ->> 'role', v_receipt.id);

    IF v_first THEN
        INSERT INTO hypothesis_transitions
            (program_id, hypothesis_id, from_status, to_status, actor_kind,
             agent_run_id, receipt_id, rationale)
        VALUES (p, v_test.hypothesis_id, 'testable', 'testing', 'runtime',
                v_run.agent_run_id, v_receipt.id,
                'the replay of ' || v_test.label || ' reached the target');
    END IF;

    RETURN jsonb_build_object(
        'tool_run', v_run.label,
        'ordinal', p_ordinal,
        'role', v_action ->> 'role',
        'receipt', p_receipt,
        'started_testing', v_first);
END $fn$;

COMMENT ON FUNCTION record_test_action(uuid, integer, text) IS
    'Tie one Receipt to one planned action, under the role the plan gave it, '
    'and move the claim to `testing` on the first one. Refuses a Receipt from '
    'another Tool run, a Receipt outside the replay Lane, a Receipt that '
    'answers a different request than the action states, and an ordinal this '
    'Test does not perform.';


-- ---------------------------------------------------------------------------
-- 8. Deriving the outcome
-- ---------------------------------------------------------------------------
-- Criterion 5. Every assertion is a comparison over columns the door wrote, so
-- the verdict is a function of canonical state: the same run evaluated twice
-- answers the same thing, and a runtime that would like a different answer has
-- nothing to pass in.
--
-- A verdict of null is the whole of `inconclusive`. An action that was never
-- recorded, a Receipt with no status line because the request never reached the
-- target, a comparison against a body nobody stored -- each of them is a
-- question this run did not answer, and a Test that did not answer its own
-- question has not refuted anything.

CREATE FUNCTION evaluate_test_assertions(p_tool_run_id uuid) RETURNS jsonb
LANGUAGE plpgsql STABLE AS $fn$
DECLARE
    v_spec      jsonb;
    v_assertion jsonb;
    v_kind      text;
    v_left      receipts%ROWTYPE;
    v_right     receipts%ROWTYPE;
    v_held      boolean;
    v_results   jsonb := '[]'::jsonb;
    v_failed    text[] := '{}';
    v_unknown   boolean := false;
    v_outcome   text;
BEGIN
    SELECT te.spec INTO v_spec
      FROM test_replays tp JOIN tests te ON te.id = tp.test_id
     WHERE tp.tool_run_id = p_tool_run_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'tool run % is not a replay', p_tool_run_id
            USING ERRCODE = '23503';
    END IF;

    FOR v_assertion IN SELECT * FROM jsonb_array_elements(v_spec -> 'assertions')
    LOOP
        v_kind := v_assertion ->> 'kind';
        v_left := NULL;
        v_right := NULL;
        SELECT r.* INTO v_left
          FROM test_replay_actions a JOIN receipts r ON r.id = a.receipt_id
         WHERE a.tool_run_id = p_tool_run_id
           AND a.ordinal = (v_assertion ->> 'action')::numeric::integer;
        IF v_assertion ? 'against' THEN
            SELECT r.* INTO v_right
              FROM test_replay_actions a JOIN receipts r ON r.id = a.receipt_id
             WHERE a.tool_run_id = p_tool_run_id
               AND a.ordinal = (v_assertion ->> 'against')::numeric::integer;
        END IF;

        v_held := CASE
            -- The two comparisons a missing row makes unanswerable, first,
            -- because every arm below reads a column off one of them.
            WHEN v_left.id IS NULL THEN NULL
            WHEN v_assertion ? 'against' AND v_right.id IS NULL THEN NULL
            WHEN v_kind = 'status_equals' THEN
                v_left.status_code = (v_assertion ->> 'status')::numeric::integer
            WHEN v_kind = 'status_differs' THEN
                CASE WHEN v_left.status_code IS NULL OR v_right.status_code IS NULL
                     THEN NULL
                     ELSE v_left.status_code <> v_right.status_code END
            -- `IS DISTINCT FROM` is deliberately not used on the bodies: two
            -- Receipts that both stored nothing are not two identical bodies,
            -- they are two answers nobody kept, and reading them as equal would
            -- turn an unanswered question into a refutation.
            WHEN v_left.response_agent_sha IS NULL
                 OR v_right.response_agent_sha IS NULL THEN NULL
            WHEN v_kind = 'body_equals' THEN
                v_left.response_agent_sha = v_right.response_agent_sha
            WHEN v_kind = 'body_differs' THEN
                v_left.response_agent_sha <> v_right.response_agent_sha
        END;

        IF v_held IS NULL THEN
            v_unknown := true;
        ELSIF NOT v_held THEN
            v_failed := array_append(v_failed, v_assertion ->> 'id');
        END IF;

        v_results := v_results || jsonb_build_object(
            'id', v_assertion ->> 'id',
            'kind', v_kind,
            'held', v_held);
    END LOOP;

    v_outcome := CASE WHEN v_unknown THEN 'inconclusive'
                      WHEN cardinality(v_failed) > 0 THEN 'refutes'
                      ELSE 'holds' END;

    RETURN jsonb_build_object(
        'assertions', v_results,
        'failed', to_jsonb(v_failed),
        'outcome', v_outcome);
END $fn$;

COMMENT ON FUNCTION evaluate_test_assertions(uuid) IS
    'What a replay concluded, read off its own Receipts. Answers every '
    'assertion with true, false or null, the identifiers of the ones that '
    'failed, and the outcome the three add up to: one unanswerable assertion '
    'makes the run inconclusive, one failed assertion refutes, and everything '
    'holding holds.';


-- ---------------------------------------------------------------------------
-- 9. Closing one
-- ---------------------------------------------------------------------------
-- The Test run row, its Receipts under their roles, the Evidence the roles
-- carry into 007's machine, and the transition that settles the claim -- all in
-- one transaction, because a run that recorded its Receipts and failed to
-- settle would leave a claim in `testing` with nothing able to move it.
--
-- The order matters twice. `test_run_receipts` is written before the
-- transition, because 007's `requires_test_linked_receipt` looks for exactly
-- those rows and 034's settle trigger reads them again to decide whether a
-- refutation is `settled` or `unverified`. And the Evidence is written before
-- the transition for the same reason: the rule for `-> supported` counts it.


-- 007 may refuse the settle, and the ordinary way is a plan that performed too
-- few roles: the shape rule makes every Test carry a control, and a control the
-- door blocked is an action with no Receipt, so a run can hold every assertion
-- it stated and still be one Observation short of what `-> supported` asks for.
--
-- A refusal raised through the close would take the Test run and the Receipts
-- this transaction just recorded down with it and leave the Tool run running,
-- which no check reports -- every one of them waits for a run that stopped --
-- and which a retry would reach the same way. So the close asks first.
--
-- Asking means the rule has to be a question and not only an exception, and it
-- has to be the same rule: a second copy of 007's arithmetic here would be a
-- second answer to "may this claim move", which is the one thing 007 exists to
-- be the only one of. So the guard's verdict is extracted, and the guard is
-- what calls it -- the trigger keeps the two questions that are its own (does
-- the claim exist, is it where the row says it is) because those need the row
-- lock the trigger already took, and hands the rest here. Every message is the
-- one 015 raised, in the same words.

CREATE FUNCTION hypothesis_transition_refusal(
        p_hypothesis uuid,
        p_from       text,
        p_to         text,
        p_actor_kind text,
        p_receipt    uuid,
        p_agent_run  uuid)
RETURNS text
LANGUAGE plpgsql AS $fn$
DECLARE
    r         transition_rules%ROWTYPE;
    n_support integer;
    n_control integer;
    lane      text;
    v_profile text;
    v_ok      boolean;
BEGIN
    SELECT * INTO r FROM transition_rules
     WHERE machine = 'hypothesis'
       AND from_status = p_from
       AND to_status = p_to;
    IF NOT FOUND THEN
        RETURN format('illegal transition %s -> %s', p_from, p_to);
    END IF;

    IF r.required_actor_kind IS NOT NULL AND p_actor_kind <> r.required_actor_kind THEN
        RETURN format('transition %s -> %s requires actor_kind %s, got %s',
            p_from, p_to, r.required_actor_kind, p_actor_kind);
    END IF;

    IF r.requires_receipt AND p_receipt IS NULL THEN
        RETURN format('transition %s -> %s requires a tool receipt', p_from, p_to);
    END IF;

    -- D7 / C23: decision 15 applied to transitions, not only to observations.
    -- The proxy fetching its own CSRF token is not evidence of anything.
    IF p_receipt IS NOT NULL THEN
        SELECT receipts.lane INTO lane FROM receipts WHERE id = p_receipt;
        IF lane = 'proxy_internal' THEN
            RETURN format(
                'receipt %s is lane proxy_internal and cannot back a transition',
                p_receipt);
        END IF;
    END IF;

    -- The stronger form: the cited receipt must be one this hypothesis's test run
    -- produced, so a conclusion cannot rest on an unrelated request that happened
    -- to be receipted.
    IF r.requires_test_linked_receipt AND NOT EXISTS (
            SELECT 1
              FROM test_run_receipts trr
              JOIN test_runs tr ON tr.id = trr.test_run_id
              JOIN tests te     ON te.id = tr.test_id
             WHERE trr.receipt_id = p_receipt
               AND te.hypothesis_id = p_hypothesis) THEN
        RETURN format(
            'transition %s -> %s must cite a receipt produced by a test run of hypothesis %s',
            p_from, p_to, p_hypothesis);
    END IF;

    SELECT count(*) FILTER (WHERE role IN ('baseline','variant')),
           count(*) FILTER (WHERE role = 'control')
      INTO n_support, n_control
      FROM hypothesis_evidence WHERE hypothesis_id = p_hypothesis;

    IF n_support < r.min_supporting_evidence THEN
        RETURN format('transition %s -> %s needs %s evidence rows, found %s',
            p_from, p_to, r.min_supporting_evidence, n_support);
    END IF;
    IF n_control < r.min_control_evidence THEN
        RETURN format('transition %s -> %s needs a control observation', p_from, p_to);
    END IF;

    -- Ticket 09: a skill may be stricter than the default, never looser. The
    -- profile arrives on the task row from the PreToolUse hook. A transition with
    -- no agent run is not attributable to a skill and gets the default.
    IF r.consults_evidence_profile AND p_agent_run IS NOT NULL THEN
        SELECT tk.evidence_profile_id INTO v_profile
          FROM agent_runs ar JOIN tasks tk ON tk.id = ar.task_id
         WHERE ar.id = p_agent_run;
        IF v_profile IS NOT NULL THEN
            EXECUTE format('SELECT %I($1)', 'evidence_profile_' || v_profile)
               INTO v_ok USING p_hypothesis;
            IF NOT coalesce(v_ok, false) THEN
                RETURN format('evidence profile %s is not satisfied for hypothesis %s',
                    v_profile, p_hypothesis);
            END IF;
        END IF;
    END IF;

    RETURN NULL;
END $fn$;

COMMENT ON FUNCTION hypothesis_transition_refusal(uuid, text, text, text, uuid, uuid) IS
    'Why 007 would refuse this hypothesis transition, or NULL if it admits it. '
    'The body of enforce_hypothesis_transition from the rule lookup onward, so '
    'a caller that wants to know before it writes asks the same rule that would '
    'stop it -- the two questions the trigger keeps are about the row it locked.';

-- No REVOKE follows, and that is the decision rather than the omission: this is
-- the guard's own body, it runs for whoever inserted the row, and it reads
-- every table under that caller's own privileges exactly as it did inline. A
-- narrower grant would be a role that may write a transition and may not run
-- the rule that admits it.

CREATE OR REPLACE FUNCTION enforce_hypothesis_transition() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE
    cur      text;
    refusal  text;
BEGIN
    SELECT status INTO cur FROM hypotheses WHERE id = NEW.hypothesis_id FOR UPDATE;
    IF cur IS NULL THEN
        RAISE EXCEPTION 'no hypothesis %', NEW.hypothesis_id;
    END IF;
    IF cur IS DISTINCT FROM NEW.from_status THEN
        RAISE EXCEPTION 'stale transition: hypothesis % is %, not %',
            NEW.hypothesis_id, cur, NEW.from_status;
    END IF;

    refusal := hypothesis_transition_refusal(
        NEW.hypothesis_id, NEW.from_status, NEW.to_status, NEW.actor_kind,
        NEW.receipt_id, NEW.agent_run_id);
    IF refusal IS NOT NULL THEN
        RAISE EXCEPTION '%', refusal;
    END IF;

    -- The cache write is the AFTER trigger's, so the transition row is already
    -- visible when guard_hypothesis_status_cache() looks for it.
    RETURN NEW;
END $fn$;


CREATE FUNCTION close_test_replay(
        p_tool_run_id uuid,
        p_cleanup     text,
        p_detail      text DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p          uuid := rk2_program_required();
    v_replay   test_replays%ROWTYPE;
    v_run      tool_runs%ROWTYPE;
    v_test     tests%ROWTYPE;
    v_eval     jsonb;
    v_outcome  text;
    v_means    record;
    v_run_id   uuid;
    v_actions  bigint;
    v_status   text;
    v_first    uuid;
    v_action   record;
    v_kind     text;
    v_observed uuid;
    v_said     text;
    v_refused  text;
BEGIN
    IF NOT (p_cleanup = ANY (rk2_test_cleanup_states())) THEN
        RAISE EXCEPTION 'a replay reports its cleanup as done, failed or skipped, not %',
            p_cleanup USING ERRCODE = '22023';
    END IF;

    SELECT tp.* INTO v_replay FROM test_replays tp
     WHERE tp.tool_run_id = p_tool_run_id AND tp.program_id = p
       FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'tool run % is not a replay of this Program', p_tool_run_id
            USING ERRCODE = '23503';
    END IF;
    SELECT * INTO v_run FROM tool_runs WHERE id = p_tool_run_id FOR UPDATE;
    IF v_run.status <> 'running' THEN
        RAISE EXCEPTION 'replay % was already closed as %', v_run.label, v_run.status
            USING ERRCODE = '23514';
    END IF;
    SELECT * INTO v_test FROM tests WHERE id = v_replay.test_id;

    v_eval := evaluate_test_assertions(p_tool_run_id);
    v_outcome := v_eval ->> 'outcome';
    SELECT * INTO v_means FROM rk2_test_outcome(v_outcome);
    SELECT count(*) INTO v_actions FROM test_replay_actions
     WHERE tool_run_id = p_tool_run_id;

    PERFORM set_actor('runtime');
    INSERT INTO test_runs
        (program_id, test_id, agent_run_id, lane, outcome, assertion_results,
         started_at, finished_at)
    VALUES
        (p, v_replay.test_id, v_run.agent_run_id, 'replay', v_outcome,
         (v_eval - 'outcome') || jsonb_build_object('cleanup', p_cleanup),
         v_replay.started_at, now())
    RETURNING id INTO v_run_id;

    -- The link first, and the Receipts under it. Section 10's second arm asks
    -- which Tool run a Test run's Receipts may come from, and it reads the
    -- answer off `test_replays.test_run_id`; written the other way round, the
    -- rows this function inserts would arrive before there was anything to
    -- check them against, and the arm would hold for every writer except the
    -- one that produces every row it will ever see.
    UPDATE test_replays SET test_run_id = v_run_id WHERE tool_run_id = p_tool_run_id;

    INSERT INTO test_run_receipts (program_id, test_run_id, receipt_id, ordinal, role)
    SELECT p, v_run_id, a.receipt_id, a.ordinal, a.role
      FROM test_replay_actions a
     WHERE a.tool_run_id = p_tool_run_id
     ORDER BY a.ordinal;

    -- The Evidence, one row per action that was performed, under the role the
    -- plan gave it. Nothing is written for an inconclusive run: an Observation
    -- is a statement about the target, and a run that could not evaluate its
    -- own assertions has none to make.
    IF v_outcome <> 'inconclusive' THEN
        FOR v_action IN
            SELECT a.ordinal, a.role, a.receipt_id, r.status_code, r.method, r.host
              FROM test_replay_actions a JOIN receipts r ON r.id = a.receipt_id
             WHERE a.tool_run_id = p_tool_run_id
             ORDER BY a.ordinal
        LOOP
            -- Which kind of Observation this action produced is a property of
            -- the assertions that name it, not of the role it carries: an
            -- action nothing compares against was observed for what it is, and
            -- one that a comparison names was observed for how it differs.
            SELECT CASE WHEN EXISTS (
                       SELECT 1 FROM jsonb_array_elements(v_test.spec -> 'assertions') x
                        WHERE x ->> 'kind' IN ('status_differs', 'body_differs')
                          AND v_action.ordinal IN (
                              (x ->> 'action')::numeric::integer,
                              (x ->> 'against')::numeric::integer))
                   THEN 'response_differential' ELSE 'response_invariant' END
              INTO v_kind;

            INSERT INTO observations
                (program_id, agent_run_id, subject_entity_id, kind, summary,
                 provenance_kind, receipt_id)
            SELECT p, v_run.agent_run_id, h.subject_entity_id, v_kind,
                   'the ' || v_action.role || ' action of ' || v_test.label
                          || ' answered ' || coalesce(v_action.status_code::text, 'nothing'),
                   'receipt', v_action.receipt_id
              FROM hypotheses h WHERE h.id = v_test.hypothesis_id
            RETURNING id INTO v_observed;

            INSERT INTO hypothesis_evidence
                (program_id, hypothesis_id, observation_id, polarity, role)
            VALUES (p, v_test.hypothesis_id, v_observed, v_means.polarity,
                    v_action.role);
        END LOOP;
    END IF;

    -- And the settling. A run that recorded no action never moved the claim to
    -- `testing`, so there is nothing to settle and nothing to explain: the
    -- Test run row above is the record that the attempt happened and reached
    -- nothing.
    SELECT a.receipt_id INTO v_first
      FROM test_replay_actions a
     WHERE a.tool_run_id = p_tool_run_id
     ORDER BY a.ordinal LIMIT 1;

    IF v_first IS NOT NULL THEN
        v_status := v_means.settles;
        v_said := 'the replay of ' || v_test.label || ' ' || v_outcome
                      || coalesce(': ' || nullif(p_detail, ''), '');
        -- Asked, not attempted. What comes back is a verdict about the
        -- conclusion and not an error in this transaction, and the run settles
        -- for what it can still say: `inconclusive` asks for nothing but the
        -- Receipt this run already has, and it is the honest word -- the
        -- assertions held, and the claim they were meant to settle has not been
        -- settled by them. A run already concluding `inconclusive` writes what
        -- it was going to write; there is nothing weaker to fall back to, so a
        -- refusal of that is about something else and is left to be raised by
        -- the guard, where every other unexpected refusal is raised.
        IF v_status <> 'inconclusive' THEN
            -- Under the same lock the guard will take, so that the answer is
            -- still the answer when the row that acts on it is written.
            PERFORM 1 FROM hypotheses WHERE id = v_test.hypothesis_id FOR UPDATE;
            v_refused := hypothesis_transition_refusal(
                v_test.hypothesis_id, 'testing', v_status, 'runtime',
                v_first, v_run.agent_run_id);
            IF v_refused IS NOT NULL THEN
                v_status := 'inconclusive';
                v_said := v_said || ', and could not settle as ' || v_means.settles
                                 || ': ' || v_refused;
            END IF;
        END IF;

        INSERT INTO hypothesis_transitions
            (program_id, hypothesis_id, from_status, to_status, actor_kind,
             agent_run_id, receipt_id, rationale)
        VALUES (p, v_test.hypothesis_id, 'testing', v_status, 'runtime',
                v_run.agent_run_id, v_first, v_said);
    END IF;

    -- The credential dies with the run: `guard_tool_run_authorization` clears
    -- it on any row that stops running, which is why this statement says
    -- nothing about it.
    UPDATE tool_runs
       SET status = v_means.tool_run_status,
           finished_at = now()
     WHERE id = p_tool_run_id;

    RETURN jsonb_build_object(
        'tool_run', v_run.label,
        -- The word on the row, read back rather than restated. A caller that
        -- had to name the Tool run's status for its own report would be
        -- inventing a second vocabulary for a column it just wrote.
        'status', (SELECT status FROM tool_runs WHERE id = p_tool_run_id),
        'test_run_id', v_run_id,
        'outcome', v_outcome,
        'failed', v_eval -> 'failed',
        'cleanup', p_cleanup,
        'actions', v_actions,
        'hypothesis_status', coalesce(v_status, 'testable'),
        'settle_refused', v_refused);
END $fn$;

COMMENT ON FUNCTION close_test_replay(uuid, text, text) IS
    'Close one replay, once: derive the outcome from its Receipts, write the '
    'Test run and its Receipts under their roles, file the Evidence each role '
    'produced, and settle the claim. A run that recorded no action closes as '
    'inconclusive and leaves the claim where it was; one whose conclusion the '
    'epistemic machine refuses settles inconclusive and reports the refusal.';

-- The verbs and what only they need. The vocabulary functions of section 2 are
-- deliberately not here: each one backs a CHECK constraint, so every role that
-- may write the table it guards must be able to execute it, and a REVOKE on
-- them would be a refusal to insert dressed as a privilege.
REVOKE ALL ON FUNCTION rk2_replay_tool(),
                       rk2_capability_lane(uuid),
                       rk2_test_route(text),
                       rk2_test_outcome(text),
                       open_test_replay(uuid, uuid, text),
                       record_test_action(uuid, integer, text),
                       evaluate_test_assertions(uuid),
                       close_test_replay(uuid, text, text)
    FROM PUBLIC, rk2_state, rk2_proxy, rk2_human;
GRANT EXECUTE ON FUNCTION rk2_replay_tool(),
                          rk2_test_route(text),
                          rk2_test_outcome(text),
                          open_test_replay(uuid, uuid, text),
                          record_test_action(uuid, integer, text),
                          evaluate_test_assertions(uuid),
                          close_test_replay(uuid, text, text)
    TO rk2_runtime;

-- The door calls it while writing a Receipt, and that call is inside a
-- SECURITY DEFINER function owned by the schema owner, so the proxy role needs
-- no privilege of its own on it.
GRANT EXECUTE ON FUNCTION rk2_capability_lane(uuid) TO rk2_runtime;


-- ---------------------------------------------------------------------------
-- 10. What may be attached to a run
-- ---------------------------------------------------------------------------
-- Criterion 6, as one trigger with three arms. Section 9 writes rows that pass
-- all three by construction; the trigger is for every other writer, which is
-- the point -- a rule that only the intended caller obeys is a convention.
--
-- 042 wrote the first arm and it stays as it was, re-created here only because
-- the other two belong beside it. `proxy_internal` remains exempt for its
-- reason: the proxy fetching its own CSRF token is not the party that ran the
-- test, and it is not evidence either.

CREATE OR REPLACE FUNCTION enforce_test_run_receipt_lane() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE
    v_run_lane     text;
    v_receipt      receipts%ROWTYPE;
    v_replay_run   uuid;
    v_foreign      text;
BEGIN
    SELECT lane INTO v_run_lane FROM test_runs WHERE id = NEW.test_run_id;
    SELECT * INTO v_receipt FROM receipts WHERE id = NEW.receipt_id;

    IF v_receipt.lane IN ('agent', 'replay') AND v_receipt.lane <> v_run_lane THEN
        RAISE EXCEPTION
            'test run % is lane=%, so it cannot cite a lane=% receipt: the '
            'party that caused the request is not the party that ran the test',
            NEW.test_run_id, v_run_lane, v_receipt.lane
            USING ERRCODE = '23514';
    END IF;

    -- The Tool run. A replay's evidence is what its own capability produced;
    -- another Tool run's Receipt is another run's evidence however it was
    -- obtained, and a Test run that could cite one could rest a conclusion on a
    -- request nothing about this Test caused.
    --
    -- Which Tool run is this run's own is asked twice, because there are two
    -- ways to know. A replay says so, and that is the answer whenever a Test
    -- run came from one. A Test run that came from somewhere else has no replay
    -- row to ask, and there the run's own Receipts are the answer: they all
    -- came from one Tool run or the citation is already mixed. That leaves the
    -- first Receipt on a hand-written run unchecked, which is the honest limit
    -- of a rule with nothing yet to compare against.
    SELECT tp.tool_run_id INTO v_replay_run
      FROM test_replays tp WHERE tp.test_run_id = NEW.test_run_id;
    IF v_replay_run IS NULL THEN
        SELECT r.tool_run_id INTO v_replay_run
          FROM test_run_receipts trr JOIN receipts r ON r.id = trr.receipt_id
         WHERE trr.test_run_id = NEW.test_run_id
         ORDER BY trr.ordinal LIMIT 1;
    END IF;
    IF v_replay_run IS NOT NULL
       AND v_receipt.tool_run_id IS DISTINCT FROM v_replay_run THEN
        RAISE EXCEPTION
            'receipt % was produced by another tool run and is not this test '
            'run''s evidence', NEW.receipt_id
            USING ERRCODE = '23514';
    END IF;

    -- The Artifacts. Bytes are content-addressed and therefore global, so the
    -- one thing that makes an Artifact this Program's is the seal over it. A
    -- Receipt naming bytes sealed to another Program is a Receipt carrying
    -- somebody else's evidence, and 017's isolation is exactly what it would
    -- cross.
    SELECT string_agg(DISTINCT s.sha256, ', ') INTO v_foreign
      FROM artifact_seal s
     WHERE s.scope_kind = 'program'
       AND s.scope_id IS DISTINCT FROM NEW.program_id
       AND s.sha256 IN (v_receipt.request_agent_sha, v_receipt.request_wire_sha,
                        v_receipt.response_agent_sha, v_receipt.response_wire_sha);
    IF v_foreign IS NOT NULL THEN
        RAISE EXCEPTION
            'receipt % names artifact(s) sealed to another Program: %',
            NEW.receipt_id, v_foreign
            USING ERRCODE = '23514';
    END IF;

    RETURN NEW;
END $fn$;

COMMENT ON FUNCTION enforce_test_run_receipt_lane() IS
    'Criterion 6. What a Test run may cite: a Receipt of its own Lane, produced '
    'by its own Tool run, naming no bytes sealed to another Program.';


-- ---------------------------------------------------------------------------
-- 11. What the model may read
-- ---------------------------------------------------------------------------
-- The role, and nothing else. 008's `test_run_receipts` is already published
-- and the new column belongs with the rest of the row -- an agent writing up a
-- Finding needs to say which request was the control.
--
-- The in-flight tables stay unpublished. A replay is the runtime's work, not
-- the agent's; what the agent gets to see is the finished run, which carries
-- every fact the in-flight rows held.

INSERT INTO state_read_surface (table_name, column_name, added_by) VALUES
    ('test_run_receipts', 'role', '35');

SELECT apply_state_grants();


-- ---------------------------------------------------------------------------
-- 12. The check
-- ---------------------------------------------------------------------------

CREATE FUNCTION check_test_replays()
RETURNS TABLE (problem text, subject text, detail text)
LANGUAGE sql STABLE AS $fn$
    -- A replay whose Tool run ended without producing a Test run. The row is
    -- the only trace that work was done, and nothing else in the schema would
    -- report it: the Tool run looks closed and the claim looks untouched.
    SELECT 'replay_without_run', tr.label,
           'closed as ' || tr.status || ' and wrote no Test run'
      FROM test_replays tp JOIN tool_runs tr ON tr.id = tp.tool_run_id
     WHERE tr.status <> 'running' AND tp.test_run_id IS NULL

    UNION ALL
    -- A Receipt this replay produced that no action cites and no closing
    -- carried over. Setup and cleanup are exactly this and are not a problem;
    -- an action ordinal that was performed and never recorded is, and the two
    -- are told apart by the claim being left in `testing`.
    SELECT 'replay_left_testing', h.label,
           'a replay of ' || te.label || ' closed and the claim is still testing'
      FROM test_replays tp
      JOIN tool_runs tr  ON tr.id = tp.tool_run_id
      JOIN tests te      ON te.id = tp.test_id
      JOIN hypotheses h  ON h.id = te.hypothesis_id
     WHERE tr.status <> 'running' AND h.status = 'testing'

    UNION ALL
    -- The Lane, held against the run rather than against the Receipt: 042's
    -- trigger refuses the pairing on write, and this reports one that exists.
    SELECT 'test_run_receipt_lane', r.label,
           'lane ' || r.lane || ' cited by a lane ' || run.lane || ' test run'
      FROM test_run_receipts trr
      JOIN test_runs run ON run.id = trr.test_run_id
      JOIN receipts r    ON r.id = trr.receipt_id
     WHERE r.lane IN ('agent', 'replay') AND r.lane <> run.lane

    UNION ALL
    -- A Test run in the replay Lane that settled a claim on no evidence at all.
    -- `inconclusive` is the one outcome that legitimately has none.
    SELECT 'replay_run_without_receipts', te.label,
           'a replay run concluded ' || run.outcome || ' citing no Receipt'
      FROM test_runs run JOIN tests te ON te.id = run.test_id
     WHERE run.lane = 'replay' AND run.outcome <> 'inconclusive'
       AND NOT EXISTS (SELECT 1 FROM test_run_receipts trr
                        WHERE trr.test_run_id = run.id)

    UNION ALL
    -- A stored specification the shape rule would refuse. The constraint makes
    -- this unreachable; it is here because the constraint is a function, and a
    -- later ticket that tightens the function does not revalidate what is
    -- already stored.
    SELECT 'test_spec_refused', te.label, rk2_test_spec_problem(te.spec)
      FROM tests te
     WHERE rk2_test_spec_problem(te.spec) IS NOT NULL
$fn$;

COMMENT ON FUNCTION check_test_replays() IS
    'What a replay leaves behind when it goes wrong: a Tool run that ended '
    'without a Test run, a claim stuck in testing, a Receipt cited across '
    'Lanes, a conclusion resting on nothing, and a specification the current '
    'shape rule would no longer accept.';

REVOKE ALL ON FUNCTION check_test_replays() FROM PUBLIC, rk2_state, rk2_proxy;
GRANT EXECUTE ON FUNCTION check_test_replays() TO rk2_runtime, rk2_human;

INSERT INTO standing_checks(name, query, owner_ticket, note) VALUES
    ('test_replays', 'SELECT * FROM check_test_replays()', '35',
     'every replay that ended wrote a Test run, left no claim in testing, cited only Receipts of its own Lane, and rested every conclusion it drew on at least one of them');



-- ---------------------------------------------------------------------------
-- 13. The rules that were written when there was one Lane
-- ---------------------------------------------------------------------------
-- A new Lane is a new way to be invisible. Every standing rule about egress was
-- written when `agent` was the only Lane a request could be made in, and each
-- says so in a predicate -- so a replay's Receipts, which are egress by every
-- other measure, would go unread by all of them: a request with no Tool run
-- behind it, one made after the gate said no, one closed as denied that nothing
-- refused, one recorded on the agent's side of an intercepted handshake and not
-- the wire's, and a Program past the request budget its scope carries.
--
-- The five rules below are re-created with the Lane widened to the pair and
-- nothing else changed. `proxy_internal` stays outside all of them for the
-- reason 042 gave: the proxy fetching its own CSRF token is not a request this
-- harness made, and it is not evidence either.
--
-- Both CHECKs keep their names. 022's `check_hook_provenance` looks the first
-- one up by name to assert the guarantee statically, and 20260811T210000Z does
-- the same for the second, so a rename here would be an edit to two other
-- tickets' static checks to make them say what they already say.

ALTER TABLE receipts DROP CONSTRAINT receipts_served_agent_needs_tool_run;
ALTER TABLE receipts ADD CONSTRAINT receipts_served_agent_needs_tool_run
    CHECK (NOT (lane IN ('agent', 'replay') AND decision = 'allowed'
                AND tool_run_id IS NULL));

-- 025's rule, last written by 20260811T210000Z: a Receipt that describes the
-- handshake the agent saw must describe the one the proxy made as well, or the
-- record claims a connection nobody watched. The converse stays allowed -- the
-- wire side alone is the honest record of a hop where the agent was not offered
-- TLS -- and the reasoning does not mention which Lane asked, because a replay
-- goes through the same door and is interceptable in the same way.

ALTER TABLE receipts DROP CONSTRAINT receipts_agent_transport_records_both_sides;
ALTER TABLE receipts ADD CONSTRAINT receipts_agent_transport_records_both_sides
    CHECK (lane NOT IN ('agent', 'replay')
           OR agent_tls_version IS NULL
           OR wire_tls_version IS NOT NULL);

-- 022's row-side detector, last written by 20260812T020000Z. Arms (a), (b)
-- and (i) read the Lane; the other seven are here because a function is
-- replaced whole.

CREATE OR REPLACE FUNCTION check_receipt_integrity(
        p_program uuid DEFAULT NULL,
        p_open_after interval DEFAULT interval '1 hour')
RETURNS TABLE (problem text, detail text, count bigint)
LANGUAGE plpgsql AS $$
BEGIN
    -- (a) egress that happened with no hook receipt behind it, observed from
    -- the side the model cannot forge, plus any receipt naming a tool run that
    -- is not there. 035: in either Lane a request may be made in.
    RETURN QUERY
    SELECT 'egress_without_tool_run',
           r.host || ' ' || coalesce(r.method,'?') || ' ' || coalesce(r.path,''),
           count(*)::bigint
      FROM receipts r
     WHERE r.lane IN ('agent', 'replay')
       AND (p_program IS NULL OR r.program_id = p_program)
       AND ((r.tool_run_id IS NULL AND r.ts_egress IS NOT NULL)
            OR (r.tool_run_id IS NOT NULL
                AND NOT EXISTS (SELECT 1 FROM tool_runs t WHERE t.id = r.tool_run_id)))
     GROUP BY 1,2;

    -- (b) the hook said no -- or was never asked -- and the network happened
    -- anyway. The gate's verdict is `decision`; `status` is the outcome, and a
    -- Tool run closed as denied because the door enforced a budget is the door
    -- working.
    RETURN QUERY
    SELECT 'egress_after_denial', t.label, count(*)::bigint
      FROM tool_runs t
      JOIN receipts r ON r.tool_run_id = t.id
                     AND r.lane IN ('agent', 'replay')
     WHERE t.decision IS DISTINCT FROM 'allow'
       AND r.ts_egress IS NOT NULL
       AND (p_program IS NULL OR t.program_id = p_program)
     GROUP BY 1,2;

    -- (c) opened and never closed. Expected transiently; a standing count means
    -- PostToolUse is not firing, or the sweep is not running.
    RETURN QUERY
    SELECT 'receipt_open_past_deadline', t.label, count(*)::bigint
      FROM tool_runs t
     WHERE t.status = 'running'
       AND t.started_at < now() - p_open_after
       AND (p_program IS NULL OR t.program_id = p_program)
     GROUP BY 1,2;

    -- (d) a tool call attributed to nothing. The runtime carries the
    -- correlation; a receipt without it cannot answer "which task did this".
    RETURN QUERY
    SELECT 'receipt_without_attribution', t.label, count(*)::bigint
      FROM tool_runs t
     WHERE t.transport <> 'runtime'
       AND (t.agent_run_id IS NULL OR t.task_id IS NULL)
       AND (p_program IS NULL OR t.program_id = p_program)
     GROUP BY 1,2;

    -- (e) a decision that did not come from the policy table -- and, for the one
    -- class whose policy is to ask, one that did not come from the human either.
    --
    -- `approval_required` resolves to `ask`, and both of ticket 11's outcomes
    -- move off it: parking writes `deny`, because a request that stopped at a
    -- question did not go out, and a live grant writes `allow` under rule 5.
    -- Neither is exempted on the shape of the row alone. Each must name the
    -- decision that authorises it -- the question it opened, or the approval it
    -- was admitted under -- which is the same column read the same way, and is
    -- what makes "who authorised this request" answerable from the row.
    RETURN QUERY
    SELECT 'decision_disagrees_with_risk_class',
           t.label || ' ' || t.tool || ' ' || t.risk_class || '/' || t.decision,
           count(*)::bigint
      FROM tool_runs t JOIN risk_classes rc ON rc.risk_class = t.risk_class
     WHERE t.decision IS DISTINCT FROM rc.decision
       AND (p_program IS NULL OR t.program_id = p_program)
       AND NOT (rc.decision = 'ask' AND t.decision = 'deny' AND t.status = 'parked'
                AND EXISTS (SELECT 1 FROM pending_decisions d
                             WHERE d.id = t.pending_decision_id
                               AND d.tool_run_id = t.id))
       AND NOT (rc.decision = 'ask' AND t.decision = 'allow'
                AND EXISTS (SELECT 1 FROM pending_decisions d
                             WHERE d.id = t.pending_decision_id
                               AND d.status = 'approved'
                               AND d.grant_expires_at IS NOT NULL))
     GROUP BY 1,2;

    -- (f) a hook failure with no receipt on either side of it. PostToolUse
    -- failing open is tolerable; PreToolUse failing without leaving the attempt
    -- on the record is not.
    RETURN QUERY
    SELECT 'hook_failure_without_receipt',
           e.payload ->> 'hook_event', count(*)::bigint
      FROM events e
     WHERE e.type = 'hook.failed'
       AND (p_program IS NULL OR e.program_id = p_program)
       AND e.payload ->> 'tool_use_id' IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM tool_runs t
                        WHERE t.program_id = e.program_id
                          AND t.tool_use_id = e.payload ->> 'tool_use_id')
     GROUP BY 1,2;

    -- (g) the hook-side detector for the load-bearing claim: a tool that
    -- finished without a PreToolUse receipt behind it. The close path writes
    -- these rather than dropping the call, so the count is the direct measure
    -- of "tool calls that completed without producing a receipt first".
    RETURN QUERY
    SELECT 'completed_without_pretooluse', t.label, count(*)::bigint
      FROM tool_runs t
     WHERE t.decision IS NULL
       AND t.transport <> 'runtime'
       AND t.closed_by IN ('PostToolUse','PostToolUseFailure')
       AND (p_program IS NULL OR t.program_id = p_program)
     GROUP BY 1,2;

    -- (h) a live egress credential on a receipt that is no longer running. The
    -- proxy refuses it (resolve_egress_token requires 'running'), but a token
    -- left behind means the runtime's revoke path did not run.
    RETURN QUERY
    SELECT 'egress_token_outlives_receipt', t.label, count(*)::bigint
      FROM tool_runs t
     WHERE t.egress_token_sha256 IS NOT NULL
       AND t.status <> 'running'
       AND (p_program IS NULL OR t.program_id = p_program)
     GROUP BY 1,2;

    -- (i) a run closed with the word for a refusal when nothing refused it.
    -- `denied` is what the runtime writes when the door turned a request away;
    -- a target that did not answer is the target's state, and this run's own
    -- `decision` column still says the gate allowed it.
    --
    -- Read from the Receipts and not from the status alone, because one run may
    -- make several requests: a run that really was refused, and separately met
    -- an unreachable target, closed as denied for a reason that is on the
    -- record. What this counts is a `denied` with no refusal anywhere under it.
    RETURN QUERY
    SELECT 'denied_without_a_refusal', t.label, count(*)::bigint
      FROM tool_runs t
     WHERE t.status = 'denied'
       AND t.decision = 'allow'
       AND (p_program IS NULL OR t.program_id = p_program)
       AND EXISTS (SELECT 1 FROM receipts r
                    WHERE r.tool_run_id = t.id AND r.lane IN ('agent', 'replay')
                      AND r.decision = 'blocked'
                      AND r.reason IN ('target unresolved','target unreachable'))
       AND NOT EXISTS (SELECT 1 FROM receipts r
                        WHERE r.tool_run_id = t.id
                          AND r.lane IN ('agent', 'replay')
                          AND r.decision = 'blocked'
                          AND r.reason NOT IN ('target unresolved','target unreachable'))
     GROUP BY 1,2;

    -- (j) the gate asked for a human and the run closed with a verdict anyway.
    -- `ask` is not a refusal and not a permission; it is the request this
    -- harness may not settle by itself. A `denied` under it claims a refusal
    -- nobody made, and a `success` under it says the request went out while the
    -- question was still open -- the graver of the two, and left standing here
    -- rather than corrected below, because only a human can say what should
    -- happen to a call that was made without them.
    --
    -- The parking path closes such a run as `parked`, which the table already
    -- requires to name the decision it opened, so it can never be a question
    -- nobody was asked.
    RETURN QUERY
    SELECT 'ask_closed_as_a_verdict', t.label || ' ' || t.status, count(*)::bigint
      FROM tool_runs t
     WHERE t.decision = 'ask'
       AND t.status IN ('denied','success')
       AND (p_program IS NULL OR t.program_id = p_program)
     GROUP BY 1,2;
END $$;


-- 013's budget check. Arm (c) counts the allowed exchanges a Program has
-- made against the widest budget it ever carried, and a replay spends a
-- reservation at the door like anything else -- so leaving it out counted
-- fewer requests than were made.

CREATE OR REPLACE FUNCTION check_egress_budget()
RETURNS TABLE(problem text, detail text)
LANGUAGE sql STABLE AS $fn$
    -- (a) The verbs are the proxy's and nobody else's.
    SELECT 'proxy_cannot_reserve', 'rk2_proxy cannot execute the egress budget verbs'
     WHERE NOT has_function_privilege(
               'rk2_proxy',
               'reserve_egress_slot(text,text,text,integer,text,text)', 'EXECUTE')
        OR NOT has_function_privilege('rk2_proxy', 'release_egress_slot(uuid,boolean)', 'EXECUTE')
    UNION ALL
    SELECT 'runtime_can_reserve', 'rk2_runtime can execute reserve_egress_slot'
     WHERE has_function_privilege(
               'rk2_runtime',
               'reserve_egress_slot(text,text,text,integer,text,text)', 'EXECUTE')
    UNION ALL
    -- (b) ...and the counters are nobody's to change directly. A role that could
    --     UPDATE the bucket could refill it, which is the same as having no
    --     bucket at all, and one that could DELETE a reservation could free its
    --     own concurrency. Every role below the owner is named, the runtime most
    --     of all: it is the process the model runs inside, and it is the one the
    --     owner's default privileges hand new tables to.
    --
    --     INSERT is asked of the roles that should not reach these tables at all
    --     and not of the runtime, which keeps it deliberately -- see the revoke.
    SELECT 'budget_tables_writable',
           p.grantee || ' holds ' || p.privilege_type || ' on ' || p.table_name
      FROM (
        SELECT g.grantee, t.table_name, g.privilege_type
          FROM (VALUES ('program_egress_spend'), ('program_egress_budget'),
                       ('egress_reservations')) AS t(table_name),
               (VALUES ('rk2_runtime', 'UPDATE'), ('rk2_runtime', 'DELETE'),
                       ('rk2_proxy', 'INSERT'), ('rk2_proxy', 'UPDATE'),
                       ('rk2_proxy', 'DELETE'),
                       ('rk2_state', 'INSERT'), ('rk2_state', 'UPDATE'),
                       ('rk2_state', 'DELETE'),
                       ('rk2_human', 'INSERT'), ('rk2_human', 'UPDATE'),
                       ('rk2_human', 'DELETE')) AS g(grantee, privilege_type)
         WHERE has_table_privilege(g.grantee, t.table_name, g.privilege_type)
      ) p
    UNION ALL
    -- (c) The rows, not the shapes: a Program whose door let through more
    --     exchanges than any policy it has ever carried allows. Counted over
    --     allowed Receipts because those are the exchanges an auditor can see,
    --     and every one of them spent a reservation.
    --
    --     Against the widest version rather than the live one, because a check
    --     that read only the live one would fire for good on the day an operator
    --     narrowed a budget: the exchanges already made were authorised by the
    --     policy that was live when they were made, and a standing check nobody
    --     can clear stops being a signal.
    SELECT 'budget_overspent',
           p.slug || ': ' || count(r.id) || ' allowed of ' || w.widest
      FROM programs p
      JOIN (
        SELECT sv.program_id, max(sv.budget_requests) AS widest
          FROM program_scope_versions sv
         WHERE sv.budget_requests IS NOT NULL
         GROUP BY sv.program_id
      ) w ON w.program_id = p.id
      JOIN receipts r
        ON r.program_id = p.id AND r.decision = 'allowed'
       AND r.lane IN ('agent', 'replay')
     GROUP BY p.slug, w.widest
    HAVING count(r.id) > w.widest
    UNION ALL
    -- (d) A reservation that says it is both held and finished. The pair is
    --     what the concurrency count reads, so a row that disagrees with itself
    --     is a slot that is either leaked or double-counted.
    SELECT 'reservation_state_incoherent', res.id::text
      FROM egress_reservations res
     WHERE (res.released_at IS NULL) <> (res.contacted IS NULL);
$fn$;


-- 025's transport rules. Arm 4 is the one that reads the Lane: a Receipt
-- carrying the agent side of an intercepted handshake and not the wire side
-- is a claim about a connection nobody watched, whichever Lane made it.

CREATE OR REPLACE FUNCTION check_transport_claims(p_program uuid DEFAULT NULL)
RETURNS TABLE (problem text, subject text, detail text)
LANGUAGE sql STABLE AS $$
    -- 1. a transport claim resting on an intercepted receipt.
    SELECT 'claim_from_intercepted_receipt', o.label,
           'cites ' || r.label || ' (purpose=' || r.purpose
                    || ', lane=' || r.lane || ')'
      FROM observations o JOIN receipts r ON r.id = o.receipt_id
     WHERE o.kind = 'transport_parameters_observed'
       AND NOT r.transport_citable
       AND (p_program IS NULL OR o.program_id = p_program)

    UNION ALL
    -- 2. a supported hypothesis on a probe-only class with no citable support.
    SELECT 'unsupported_transport_hypothesis', h.label, h.property_class
      FROM hypotheses h JOIN transport_makeability tm
             ON tm.property_class = h.property_class
     WHERE h.status = 'supported' AND tm.makeability = 'probe_only'
       AND NOT EXISTS (
             SELECT 1 FROM hypothesis_evidence e
               JOIN observations o ON o.id = e.observation_id
               JOIN receipts r ON r.id = o.receipt_id
              WHERE e.hypothesis_id = h.id AND e.polarity = 'supports'
                AND r.transport_citable)
       AND (p_program IS NULL OR h.program_id = p_program)

    UNION ALL
    -- 3. an unmakeable class present at all.
    SELECT 'unmakeable_class_present', h.label, h.property_class
      FROM hypotheses h JOIN transport_makeability tm
             ON tm.property_class = h.property_class
     WHERE tm.makeability = 'unmakeable'
       AND (p_program IS NULL OR h.program_id = p_program)

    UNION ALL
    -- 4. a receipt that recorded only one side of the handshake, in either
    --    Lane the harness makes requests in.
    SELECT 'one_sided_handshake_record', r.label, 'agent side without wire side'
      FROM receipts r
     WHERE r.lane IN ('agent', 'replay') AND r.agent_tls_version IS NOT NULL
       AND r.wire_tls_version IS NULL
       AND (p_program IS NULL OR r.program_id = p_program)

    UNION ALL
    -- 5. an intercepted leaf naming no CA -- an unattributable forging key.
    SELECT 'unattributed_forged_leaf', r.label, coalesce(r.agent_cert_issuer,'?')
      FROM receipts r
     WHERE r.intercepted AND r.agent_cert_sha256 IS NOT NULL
       AND r.interception_ca_id IS NULL
       AND (p_program IS NULL OR r.program_id = p_program)

    UNION ALL
    -- 6. a CA past its window still current.
    SELECT 'expired_ca_still_current', c.label, c.not_after::text
      FROM interception_cas c
     WHERE c.retired_at IS NULL AND c.not_after < now()
       AND (p_program IS NULL OR c.program_id = p_program)

    UNION ALL
    -- 7. the guards themselves. A dropped trigger is the failure this ticket is
    --    about: nothing raises, and everything looks fine.
    SELECT 'guard_missing', t, 'no ENABLE ALWAYS trigger'
      FROM unnest(ARRAY['transport_hypothesis_guard','transport_observation_guard',
                        'transport_evidence_guard','transport_finding_guard']) t
     WHERE NOT EXISTS (SELECT 1 FROM pg_trigger g
                        WHERE g.tgname = t AND NOT g.tgisinternal
                          AND g.tgenabled = 'A')

    UNION ALL
    -- 8. citability must stay derived. If a later migration makes it writable,
    --    every guard above becomes advisory.
    SELECT 'citability_writable', 'receipts.transport_citable',
           'column is not GENERATED'
     WHERE NOT EXISTS (SELECT 1 FROM pg_attribute
                        WHERE attrelid = 'receipts'::regclass
                          AND attname = 'transport_citable'
                          AND attgenerated = 's')

    UNION ALL
    -- 9. the agent connection can reach the ticket-15 reference for the
    --    forging key. Ticket 13's defect 3, one table over.
    SELECT 'ca_secret_ref_readable', 'interception_cas.secret_ref',
           'rk2_state holds SELECT on the ticket-15 secret reference'
     WHERE has_column_privilege('rk2_state', 'interception_cas', 'secret_ref', 'SELECT')

    UNION ALL
    -- 10. a table-level grant on receipts means the NEXT migration's column
    --     reaches the agent without anyone deciding that it should.
    SELECT 'receipts_grant_table_level', 'receipts',
           'rk2_state holds table-level SELECT rather than named columns'
     WHERE EXISTS (SELECT 1 FROM information_schema.table_privileges
                    WHERE table_name = 'receipts' AND grantee = 'rk2_state'
                      AND privilege_type = 'SELECT');
$$;


-- ---------------------------------------------------------------------------
-- 14. The invariants this file must not have broken
-- ---------------------------------------------------------------------------

SELECT enforce_always_triggers();
-- Section 1 takes two immutability triggers off to rename a word inside them
-- and puts them back. `ENABLE ALWAYS` is what they were and what 016 requires,
-- and the difference between that and a plain `ENABLE` is invisible in every
-- test that does not connect as a replicating session -- so it is asserted here
-- rather than trusted to the two lines that wrote it.

-- The split in section 9 holds only while the guard is the shared rule's one
-- caller. A later file that replaces `enforce_hypothesis_transition` with the
-- arithmetic inline again would leave `close_test_replay` asking a question the
-- guard no longer answers with, and the two would drift apart quietly -- the
-- close would settle `supported` and the guard would refuse it, which is the
-- state this ticket removed. Asserted rather than commented, because the file
-- that would break it is one nobody has written yet.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_proc
         WHERE proname = 'enforce_hypothesis_transition'
           AND prosrc LIKE '%hypothesis_transition_refusal(%') THEN
        RAISE EXCEPTION
            'enforce_hypothesis_transition no longer asks hypothesis_transition_refusal';
    END IF;
END $$;
