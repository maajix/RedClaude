-- ---------------------------------------------------------------------------
-- 20260816T000000Z__impact_is_authorized_before_it_is_proved.sql  (ticket 38)
-- ---------------------------------------------------------------------------
--
--   037 closed the detection question: a Finding is validated by a blind reader
--   of one holding replay. This ticket opens the second question and keeps it
--   apart from the first. Demonstrated impact is not something that can be read
--   off a banner, an error string or a model's confidence; it is a request that
--   was made, a state that was afterwards read back, and a cleanup that was
--   performed. So it is its own Task, its own immutable Test, its own operator
--   grant and its own holding run -- and none of it is allowed to move the claim
--   the detection rests on.
--
--   The shape, and why it is this shape:
--
--    * The grant cannot ride on `gate_tool_call`. `canonical_request` gives every
--      tool other than `mcp__rk2__net_request` a nonce, so a replay call's
--      equivalence key is unique per call and no approval can ever match it. The
--      impact decision is therefore about a *Test*, not about a call: the thing
--      the operator is shown, and the thing that stays fixed between the asking
--      and the running, is the specification digest.
--
--    * `open_test_replay` cannot be reused. It requires the claim to be
--      `testable`, and an impact Test runs against a Finding whose claim is
--      already `supported`. Rather than branch that verb on a flag, the parts
--      both openers share are extracted -- subject, plan, open, settle -- and
--      each verb keeps only the questions that are its own.
--
--    * The impact Task is a `hunt` Task naming the Finding. A new task kind is
--      not free: `check_role_kind_mapping` requires exactly one role per kind and
--      a default lane per kind, `scheduler_lanes` is immutable after 032, and the
--      roster is generated from 018's document. A new kind is a roster change,
--      and this ticket was not given one. `hunt` is also the honest word: the
--      role that runs replays is the role that runs this one.

-- ===========================================================================
-- 1. What an impact class is
-- ===========================================================================
--
-- The bridge between what a Test says it would do and what this harness will
-- let anyone approve. Three classes are things an operator may grant; three
-- are things nobody may grant, and they are `forbidden` so that
-- `pending_decisions_never_forbidden` refuses the question before a human can
-- answer it. That is criterion 5, and it holds however valuable the Finding
-- underneath is.

CREATE TABLE impact_classes (
    impact_class text PRIMARY KEY,
    risk_class   text NOT NULL REFERENCES risk_classes(risk_class),
    description  text NOT NULL
);

COMMENT ON TABLE impact_classes IS
  'The impact vocabulary of ticket 38: what a Test says it would do, mapped onto the risk class that decides whether it may be asked about at all. A forbidden class cannot be filed as a question, so no answer exists that admits it.';

INSERT INTO impact_classes (impact_class, risk_class, description) VALUES
    ('read_other_data',     'approval_required',
     'read data belonging to another account, tenant or user of the target'),
    ('write_target_state',  'approval_required',
     'create, modify or delete state the target holds'),
    ('escalate_privilege',  'approval_required',
     'obtain a capability the leased Identity is not entitled to'),
    ('degrade_availability', 'forbidden',
     'reduce the availability of the target to its own users: never demonstrated, at any severity'),
    ('reach_third_party',   'forbidden',
     'produce an effect on a system the Program does not own: their consent is not the Program''s to give'),
    ('pivot_out_of_scope',  'forbidden',
     'use the target as a route to a host outside the scope document');

INSERT INTO program_global_tables (table_name, reason) VALUES
    ('impact_classes', 'the impact vocabulary and its risk mapping: one per harness, like risk_classes itself');

INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('impact_classes', 'reference',
     'a vocabulary written by migration and never at runtime', '38');

-- ===========================================================================
-- 2. A Test may state the impact it would have
-- ===========================================================================
--
-- 035's specification gained one optional part. It is a statement and not a
-- performance: the class, the effect in prose, the cleanup in prose, and the
-- ordinal of the action that reads the state the Test leaves behind. The three
-- prose fields are what the operator's grant is about; the ordinal is what
-- criterion 4 is checked against, because an after-state nobody fetched is an
-- assertion about a world nobody looked at.

CREATE FUNCTION rk2_impact_problem(p_spec jsonb) RETURNS text
LANGUAGE plpgsql IMMUTABLE AS $fn$
DECLARE
    v_impact  jsonb := p_spec -> 'impact';
    v_key     text;
    v_actions integer;
    v_after   integer;
BEGIN
    IF v_impact IS NULL THEN
        -- A Test that states no impact has none to check. That is 035's Test,
        -- unchanged, and it stays the default so every existing specification
        -- still validates.
        RETURN NULL;
    END IF;
    IF jsonb_typeof(v_impact) <> 'object' THEN
        RETURN 'the impact of a Test is an object';
    END IF;
    FOR v_key IN SELECT jsonb_object_keys(v_impact) LOOP
        IF v_key NOT IN ('class', 'effect', 'cleanup', 'after_state') THEN
            RETURN 'the impact carries no key named ' || v_key;
        END IF;
    END LOOP;

    IF coalesce(v_impact ->> 'class', '') !~ '^[a-z][a-z0-9_]{2,40}$' THEN
        RETURN 'the impact states no class';
    END IF;
    FOREACH v_key IN ARRAY ARRAY['effect', 'cleanup'] LOOP
        IF coalesce(v_impact ->> v_key, '') = ''
           OR length(v_impact ->> v_key) > 500 THEN
            RETURN 'the impact states no ' || v_key;
        END IF;
    END LOOP;

    v_actions := jsonb_array_length(p_spec -> 'actions');
    IF jsonb_typeof(v_impact -> 'after_state') IS DISTINCT FROM 'number' THEN
        RETURN 'the impact names no action that reads the state it leaves';
    END IF;
    v_after := (v_impact ->> 'after_state')::numeric::integer;
    IF v_after NOT BETWEEN 1 AND v_actions THEN
        RETURN 'the impact reads the state after action ' || v_after
               || ', which this Test does not perform';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM jsonb_array_elements(p_spec -> 'assertions') x
         WHERE v_after IN ((x ->> 'action')::numeric::integer,
                           (x ->> 'against')::numeric::integer)) THEN
        RETURN 'no assertion reads action ' || v_after
               || ', so the after-state is fetched and never checked';
    END IF;
    IF jsonb_array_length(p_spec -> 'cleanup') = 0 THEN
        RETURN 'a Test that states an impact states the requests that undo it';
    END IF;
    RETURN NULL;
END $fn$;

COMMENT ON FUNCTION rk2_impact_problem(jsonb) IS
  'Ticket 38: the shape of the optional impact block of a Test specification, or NULL. Called by rk2_test_spec_problem after the parts it reads are known to be well formed.';

-- 035's validator, with one key admitted and one call added at the end. The
-- five performed parts are unchanged and still required.
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
        -- `impact` is stated, not performed, so it is not one of the parts the
        -- loop below requires to be an array.
        IF NOT (v_key = ANY (v_parts)) AND v_key <> 'impact' THEN
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

-- The class again, on a column, so every question about impact is a join and
-- not a jsonb walk -- and generated from the specification rather than beside
-- it, so the two cannot drift. `tests` is already immutable and `spec_sha256`
-- already covers the impact block, so the effect and cleanup prose the
-- operator approves is pinned by the digest they are shown.
ALTER TABLE tests
    ADD COLUMN impact_class text REFERENCES impact_classes(impact_class),
    ADD CONSTRAINT tests_impact_class_agrees_check
        CHECK (impact_class IS NOT DISTINCT FROM (spec -> 'impact' ->> 'class'));

COMMENT ON COLUMN tests.impact_class IS
  'Ticket 38: the impact class this Test states, or NULL for a detection Test. Held equal to spec -> impact ->> class by a CHECK.';

-- ===========================================================================
-- 3. A decision may be about a Test
-- ===========================================================================
--
-- 011 built `pending_decisions` around one call: the digest is the request, the
-- Tool run is the thing waiting. An impact grant is about a specification that
-- has not been run yet and may be run more than once, so the two run columns
-- become optional and a Test column joins them -- exactly one of the two
-- subjects, always.

ALTER TABLE pending_decisions
    ALTER COLUMN agent_run_id DROP NOT NULL,
    ALTER COLUMN tool_run_id  DROP NOT NULL,
    ADD COLUMN test_id uuid,
    ADD CONSTRAINT pending_decisions_test_id_program_id_fkey
        FOREIGN KEY (test_id, program_id) REFERENCES tests (id, program_id),
    ADD CONSTRAINT pending_decisions_names_one_subject
        CHECK (num_nonnulls(tool_run_id, test_id) = 1
               AND (tool_run_id IS NOT NULL) = (agent_run_id IS NOT NULL)),
    -- A question about impact is a question about work, and 008's parked shape
    -- is where the work waits. Without this the grant could be asked for with
    -- nothing parked behind it, and criterion 2 would be a comment.
    ADD CONSTRAINT pending_decisions_impact_names_a_task
        CHECK (test_id IS NULL OR task_id IS NOT NULL);

COMMENT ON COLUMN pending_decisions.test_id IS
  'Ticket 38: the Test this decision authorizes, for a question whose subject is a specification rather than a call in flight. Mutually exclusive with tool_run_id.';

-- Naming the Task is half of it. The other half is that the Task is actually
-- waiting on this question, and that cannot be a CHECK: the question is filed
-- and the Task parked in two statements of one transaction, so the row is
-- legitimately wrong in between. Deferred to the commit, where both halves are
-- written or neither is -- which is what makes criterion 2's park a condition
-- of the question rather than a convention the opener happens to follow.
CREATE FUNCTION assert_impact_question_parks_its_task() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE v tasks%ROWTYPE;
BEGIN
    IF NEW.test_id IS NULL OR NEW.status <> 'pending' THEN
        RETURN NEW;
    END IF;
    SELECT * INTO v FROM tasks WHERE id = NEW.task_id;
    IF v.status <> 'parked' OR v.pending_decision_id IS DISTINCT FROM NEW.id THEN
        RAISE EXCEPTION 'decision % asks about impact and task % is % on %',
            NEW.label, v.label, v.status,
            coalesce(v.pending_decision_id::text, 'nothing')
            USING ERRCODE = '23514',
                  HINT = 'a question about work that is not waiting is a request nobody stopped';
    END IF;
    RETURN NEW;
END $fn$;

CREATE CONSTRAINT TRIGGER pending_decisions_impact_parks_a_task
    AFTER INSERT OR UPDATE ON pending_decisions
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION assert_impact_question_parks_its_task();
ALTER TABLE pending_decisions
    ENABLE ALWAYS TRIGGER pending_decisions_impact_parks_a_task;

-- 029 took the table-level SELECT away from `rk2_runtime` and gave back every
-- column except the answer, one grant per column, generated from the table as
-- it stood. A column added after that is outside the grant it should have been
-- inside: the rule is "everything but the answer", and a new subject the
-- runtime writes and cannot read afterwards is that rule quietly not holding.
GRANT SELECT (test_id) ON pending_decisions TO rk2_runtime;

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('pending_decisions', 'test_id',
     'NO ACTION to tests, like every other key on this table: a decision outlives what it was about, and the purge reaches it through program_id');

INSERT INTO decision_question_codes (question_code, meaning, asked_when, owner_ticket) VALUES
    ('impact_unauthorized',
     'a validated Finding has an impact Test, and no live operator grant covers it',
     'open_impact_replay finds no approved, unexpired grant for the Test digest',
     '38');

-- The immutable half grows the new subject. Without this a denied impact
-- decision could be re-pointed at another Test on its way to `approved`.
CREATE OR REPLACE FUNCTION assert_decision_closes_once() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    IF OLD.status <> 'pending' THEN
        RAISE EXCEPTION 'decision % is already %', OLD.label, OLD.status
            USING ERRCODE = '23514';
    END IF;
    IF NEW.status = 'pending' THEN
        RAISE EXCEPTION 'the only legal update to a pending decision is closing it'
            USING ERRCODE = '23514';
    END IF;
    IF (NEW.id, NEW.program_id, NEW.label, NEW.equivalence_key, NEW.request_digest,
        NEW.deadline_at, NEW.tool_run_id, NEW.test_id)
       IS DISTINCT FROM
       (OLD.id, OLD.program_id, OLD.label, OLD.equivalence_key, OLD.request_digest,
        OLD.deadline_at, OLD.tool_run_id, OLD.test_id) THEN
        RAISE EXCEPTION 'the request half of decision % is immutable', OLD.label
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $fn$;

-- What the operator is shown, and what their answer is therefore about. The
-- class, the Finding, the Test, the hosts the Test would reach, the scope
-- version those hosts were classified under, the Identity the run would hold,
-- the specification digest -- and the two sentences the Test states about
-- itself: what it would do to the target, and what would put it back.
--
-- The prose is in the digest rather than beside it for the reason the sha256 is
-- there at all. Criterion 1 says the grant is over an explicit side effect and
-- cleanup, and a grant is over what it was computed from: prose alongside a
-- digest that does not cover it is prose that can change between the asking and
-- the running. The Identity is in it because `escalate_privilege` is defined
-- against the Identity the run holds -- an approval given for one slot is not
-- an approval to try the same Test as somebody else.
CREATE FUNCTION rk2_impact_digest(p_program uuid, p_finding uuid, p_test uuid,
                                  p_identity_slot text)
RETURNS jsonb
LANGUAGE sql STABLE AS $fn$
    SELECT jsonb_build_object(
               'kind',          'impact',
               'finding',       f.label,
               'test',          t.label,
               'impact_class',  t.impact_class,
               'risk_class',    ic.risk_class,
               'effect',        t.spec -> 'impact' ->> 'effect',
               'undone_by',     t.spec -> 'impact' ->> 'cleanup',
               'identity_slot', p_identity_slot,
               'spec_sha256',   t.spec_sha256,
               'scope_version', pr.scope_version,
               'hosts', (
                   SELECT coalesce(jsonb_agg(DISTINCT h.host), '[]'::jsonb)
                     FROM jsonb_array_elements(
                              (t.spec -> 'actions') || (t.spec -> 'setup')
                                                    || (t.spec -> 'cleanup')) a
                     CROSS JOIN LATERAL rk2_test_route(a ->> 'url') h))
      FROM tests t
      JOIN findings f  ON f.id = p_finding AND f.program_id = p_program
      JOIN programs pr ON pr.id = p_program
      JOIN impact_classes ic ON ic.impact_class = t.impact_class
     WHERE t.id = p_test AND t.program_id = p_program;
$fn$;

COMMENT ON FUNCTION rk2_impact_digest(uuid, uuid, uuid, text) IS
  'Ticket 38: the request half of an impact decision. What the Test states it would do and undo, the Identity it would hold, and the specification digest, so a grant covers exactly the work the operator read and stops covering it the moment the scope, the specification or the Identity moves.';

-- 011's renderer, which `assert_question_is_rendered` compares every question
-- against, gains the arm for the new digest shape. A grant for a Test has no
-- method and no path, so the old format string would have printed two blanks
-- and told the operator nothing; what it has instead is the work in the Test's
-- own words, which is what criterion 1 says the answer is about.
CREATE OR REPLACE FUNCTION render_decision_question(p_digest jsonb, p_risk text, p_rule text)
RETURNS text
LANGUAGE sql IMMUTABLE AS $fn$
    SELECT CASE WHEN p_digest ->> 'kind' = 'impact' THEN
                format('[%s] prove %s on %s via %s against %s (identity %s) -- %s'
                       || ' | effect: %s | undone by: %s',
                       p_risk,
                       coalesce(p_digest ->> 'impact_class', ''),
                       coalesce(p_digest ->> 'finding', ''),
                       coalesce(p_digest ->> 'test', ''),
                       coalesce((SELECT string_agg(x, ', ' ORDER BY x)
                                   FROM jsonb_array_elements_text(
                                            p_digest -> 'hosts') x), ''),
                       coalesce(nullif(p_digest ->> 'identity_slot',''), 'none'),
                       p_rule,
                       coalesce(p_digest ->> 'effect', ''),
                       coalesce(p_digest ->> 'undone_by', ''))
           ELSE format('[%s] %s %s%s (identity %s) -- %s',
                       p_risk,
                       coalesce(p_digest ->> 'method', p_digest ->> 'tool'),
                       coalesce(p_digest ->> 'host', ''),
                       coalesce(p_digest ->> 'path_template', ''),
                       coalesce(nullif(p_digest ->> 'identity_slot',''), 'none'),
                       p_rule)
           END;
$fn$;

-- Criterion 5, in one place. The question is asked twice -- once when the Test
-- is written and once at the moment a request would be sent -- because a
-- migration can move a class between the two and the answer that matters is the
-- one in force now. Asking twice is the rule; saying it twice is not, so the
-- sentence the operator would read lives here.
CREATE FUNCTION rk2_refuse_forbidden_impact(p_class text, p_risk text)
RETURNS void LANGUAGE plpgsql STABLE AS $fn$
BEGIN
    IF (SELECT rc.decision FROM risk_classes rc WHERE rc.risk_class = p_risk)
       = 'deny' THEN
        RAISE EXCEPTION 'impact class % is %, and no grant admits it', p_class, p_risk
            USING ERRCODE = '42501',
                  HINT = 'availability, third-party effect and out-of-scope pivots stay refused however the Finding is scored';
    END IF;
END $fn$;

COMMENT ON FUNCTION rk2_refuse_forbidden_impact(text, text) IS
  'Ticket 38 criterion 5: refuse an impact class whose risk class denies. Asked when the Test is written and again before a request is sent, because a class can be moved to forbidden between the two.';

-- 011's rule 5, lifted out of `gate_tool_call` so the impact opener asks the
-- same question of the same rows rather than a second copy of it.
CREATE FUNCTION live_grant_for(p_program uuid, p_key text) RETURNS text
LANGUAGE sql STABLE AS $fn$
    SELECT d.label
      FROM pending_decisions d
     WHERE d.program_id = p_program
       AND d.status = 'approved'
       AND d.equivalence_key = p_key
       AND d.grant_expires_at IS NOT NULL
       AND d.grant_expires_at > now()
     ORDER BY d.grant_expires_at DESC LIMIT 1;
$fn$;

COMMENT ON FUNCTION live_grant_for(uuid, text) IS
  'Ticket 11 rule 5, ticket 38 extraction: the label of a live approval covering an equivalence key, or NULL. One reading of what a standing grant is, for the gate and for the impact opener.';

CREATE OR REPLACE FUNCTION gate_tool_call(p_tool_run_id uuid) RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    tr      tool_runs%ROWTYPE;
    digest  jsonb;
    verdict jsonb;
    grant_l text;
BEGIN
    SELECT * INTO tr FROM tool_runs WHERE id = p_tool_run_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'no tool_run %', p_tool_run_id; END IF;

    digest  := current_request_digest(p_tool_run_id);
    verdict := assess_call_risk(tr.tool, digest);

    IF (SELECT decision FROM risk_classes
         WHERE risk_class = verdict ->> 'risk_class') <> 'ask' THEN
        RETURN verdict || jsonb_build_object(
            'decision', (SELECT decision FROM risk_classes
                          WHERE risk_class = verdict ->> 'risk_class'),
            'digest', digest, 'approval', NULL);
    END IF;

    -- rule 5: a live grant answers the question instead of re-asking it
    grant_l := live_grant_for(tr.program_id, equivalence_key(digest));

    RETURN verdict || jsonb_build_object(
        'decision', CASE WHEN grant_l IS NULL THEN 'ask' ELSE 'allow' END,
        'digest', digest, 'approval', grant_l);
END $fn$;

-- 029 re-asks a question at the moment it is answered, and the impact question
-- has a different digest to rebuild. Everything either side is unchanged: a
-- closed Program, a Halt and an unparked Task end an impact grant for the same
-- reasons they end a call grant.
CREATE OR REPLACE FUNCTION revalidate_decision(p_label text) RETURNS text
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path TO 'pg_catalog', 'public' AS $fn$
DECLARE
    d      pending_decisions%ROWTYPE;
    now_d  jsonb;
    v      jsonb;
    v_find uuid;
BEGIN
    SELECT * INTO d FROM pending_decisions
     WHERE label = p_label AND program_id = rk2_program_required();
    IF NOT FOUND THEN
        RAISE EXCEPTION 'no decision % in the bound Program', p_label
            USING ERRCODE = '23514';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM programs
                    WHERE id = d.program_id AND closed_at IS NULL) THEN
        RETURN 'program_closed';
    END IF;
    IF EXISTS (SELECT 1 FROM program_halts h
                WHERE h.program_id = d.program_id AND h.status = 'halted') THEN
        RETURN 'program_halted';
    END IF;
    -- A question whose Task was abandoned underneath it -- by the deadline
    -- sweep, by a purge of the hypothesis it was testing -- is a question about
    -- work that is over.
    IF d.task_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM tasks t
                        WHERE t.id = d.task_id AND t.status = 'parked'
                          AND t.pending_decision_id = d.id) THEN
        RETURN 'task_no_longer_parked';
    END IF;

    IF d.test_id IS NOT NULL THEN
        -- The Finding is read through the parked Task rather than off the
        -- decision, because the Task is the thing this ticket parks and the
        -- clause above has just established it is still parked here.
        SELECT t.finding_id INTO v_find FROM tasks t WHERE t.id = d.task_id;
        IF v_find IS NULL THEN RETURN 'task_no_longer_parked'; END IF;
        IF NOT EXISTS (SELECT 1 FROM findings f
                        WHERE f.id = v_find AND f.status = 'validated') THEN
            -- The detection this impact would be proved on is no longer a
            -- validated one, so the question is about nothing.
            RETURN 'request_reclassified';
        END IF;
        -- The Identity is read back off the question rather than guessed at.
        -- It is part of what was approved, so rebuilding the digest without it
        -- would answer about a request nobody asked about.
        now_d := rk2_impact_digest(d.program_id, v_find, d.test_id,
                                   d.request_digest ->> 'identity_slot');
        IF equivalence_key(now_d) IS DISTINCT FROM d.equivalence_key THEN
            -- The digest carries the scope version, so an edited scope document
            -- lands here: the same Test, reaching hosts nobody has classified
            -- since, is a different request as far as this approval goes.
            RETURN 'request_reclassified';
        END IF;
        IF (SELECT rc.decision FROM impact_classes ic
              JOIN risk_classes rc ON rc.risk_class = ic.risk_class
             WHERE ic.impact_class = now_d ->> 'impact_class') = 'deny' THEN
            RETURN 'now_forbidden';
        END IF;
        IF 'impact_classes:' || (now_d ->> 'impact_class')
           IS DISTINCT FROM d.risk_rule THEN
            RETURN 'policy_changed';
        END IF;
        RETURN NULL;
    END IF;

    now_d := current_request_digest(d.tool_run_id);
    IF equivalence_key(now_d) IS DISTINCT FROM d.equivalence_key THEN
        -- The digest carries the scope class, so this is where an edited scope
        -- document lands: same URL, different classification, different
        -- request as far as every approval in this corpus is concerned.
        RETURN 'request_reclassified';
    END IF;

    v := assess_call_risk(d.tool, now_d);
    IF v ->> 'risk_class' = 'forbidden' THEN RETURN 'now_forbidden'; END IF;
    IF v ->> 'rule' IS DISTINCT FROM d.risk_rule THEN RETURN 'policy_changed'; END IF;
    RETURN NULL;
END $fn$;

-- ===========================================================================
-- 4. One replay, opened two ways
-- ===========================================================================
--
-- 035's opener asked eight questions in a fixed order and then wrote three
-- rows. Six of the questions and all three writes are the same for an impact
-- run; two of them -- the claim is `testable`, no replay of this claim is in
-- flight -- are the detection run's alone. Extracted rather than branched, so
-- the ordering that makes 035 safe (nothing is sent before the scope walk, no
-- capability exists before `test_replays` does) is stated once and inherited by
-- both callers.

CREATE FUNCTION rk2_replay_subject(p_program uuid, p_agent_run_id uuid, p_test_id uuid)
RETURNS TABLE (r_run agent_runs, r_test tests)
LANGUAGE plpgsql AS $fn$
BEGIN
    SELECT * INTO r_run FROM agent_runs
     WHERE id = p_agent_run_id AND program_id = p_program;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'agent run % is not a run of this Program', p_agent_run_id
            USING ERRCODE = '23503';
    END IF;
    IF r_run.finished_at IS NOT NULL THEN
        RAISE EXCEPTION 'agent run % has already ended', r_run.label
            USING ERRCODE = '23514';
    END IF;

    IF EXISTS (SELECT 1 FROM program_halts h
                WHERE h.program_id = p_program AND h.status = 'halted') THEN
        RAISE EXCEPTION 'the Program is Halted and may not start new work'
            USING ERRCODE = '42501',
                  HINT = 'rk resume lifts the Halt';
    END IF;

    SELECT * INTO r_test FROM tests WHERE id = p_test_id AND program_id = p_program;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'test % is not a Test of this Program', p_test_id
            USING ERRCODE = '23503';
    END IF;
    RETURN NEXT;
END $fn$;

COMMENT ON FUNCTION rk2_replay_subject(uuid, uuid, uuid) IS
  'Ticket 35 steps a-c, ticket 38 extraction: the run and the Test a replay is about, or a refusal. Asked before anything else so a Halt stops a replay before its plan is even read.';

CREATE FUNCTION rk2_replay_plan(p_program uuid, p_run agent_runs, p_test tests,
                                p_identity_slot text)
RETURNS text[]
LANGUAGE plpgsql AS $fn$
DECLARE
    v_refusal text;
    v_action  jsonb;
    v_route   record;
    v_class   text;
    v_methods text[] := '{}';
BEGIN
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
               AND l.holder_agent_run_id = p_run.id
               AND l.released_at IS NULL
               AND l.expires_at > clock_timestamp()
             WHERE i.program_id = p_program
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
    IF p_run.task_id IS NOT NULL THEN
        SELECT budget_refusal_for(t.*) INTO v_refusal
          FROM tasks t WHERE t.id = p_run.task_id;
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
            (p_test.spec -> 'actions') || (p_test.spec -> 'setup')
                                       || (p_test.spec -> 'cleanup'))
    LOOP
        SELECT * INTO v_route FROM rk2_test_route(v_action ->> 'url');
        SELECT s.scope_class INTO v_class
          FROM programs pr
          CROSS JOIN LATERAL scope_class_of(
                pr.id, pr.scope_version, v_route.host, v_route.port,
                v_route.path, v_route.path, v_route.scheme, 'request') s
         WHERE pr.id = p_program;
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

    RETURN v_methods;
END $fn$;

COMMENT ON FUNCTION rk2_replay_plan(uuid, agent_runs, tests, text) IS
  'Ticket 35 steps f-h, ticket 38 extraction: the Identity lease, the budget and the scope walk over every request the plan would make, answering with the distinct methods the run will need. Raises rather than returns, because none of the three is a thing a caller may proceed past.';

CREATE FUNCTION rk2_open_replay(p_program uuid, p_run agent_runs, p_test tests,
                                p_identity_slot text, p_methods text[])
RETURNS uuid
LANGUAGE plpgsql AS $fn$
DECLARE v_id uuid;
BEGIN
    PERFORM set_actor('runtime');
    INSERT INTO tool_runs
        (program_id, agent_run_id, task_id, tool, args, status, transport)
    VALUES
        (p_program, p_run.id, p_run.task_id, rk2_replay_tool(),
         jsonb_build_object('identity_slot', p_identity_slot,
                            'methods', to_jsonb(p_methods),
                            'test', p_test.label,
                            'spec_sha256', p_test.spec_sha256),
         'running', 'runtime')
    RETURNING id INTO v_id;

    -- Before the gate, and that ordering is the whole of 035's criterion 3: the
    -- row that makes this Tool run a replay has to exist by the time a
    -- capability does, or the first Receipt would be written into the agent
    -- Lane. Ticket 38's `impact_replays` row is inserted by its caller for the
    -- same reason and in the same window.
    INSERT INTO test_replays (tool_run_id, program_id, test_id, spec_sha256)
    VALUES (v_id, p_program, p_test.id, p_test.spec_sha256);

    RETURN v_id;
END $fn$;

COMMENT ON FUNCTION rk2_open_replay(uuid, agent_runs, tests, text, text[]) IS
  'Ticket 35 steps i-j, ticket 38 extraction: the Tool run and the row that makes it a replay, both before any capability exists. The caller mints the capability once every row that must precede it has been written.';

CREATE FUNCTION rk2_replay_offer(p_test tests, p_tool_run_id uuid,
                                 p_identity_slot text, p_methods text[])
RETURNS jsonb
LANGUAGE plpgsql AS $fn$
BEGIN
    RETURN authorize_tool_run(p_tool_run_id) || jsonb_build_object(
        'tool_run_id', p_tool_run_id,
        'tool_run', (SELECT label FROM tool_runs WHERE id = p_tool_run_id),
        'test', p_test.label,
        'spec_sha256', p_test.spec_sha256,
        'identity_slot', p_identity_slot,
        'methods', to_jsonb(p_methods),
        'preconditions', p_test.spec -> 'preconditions',
        'setup', p_test.spec -> 'setup',
        'actions', p_test.spec -> 'actions',
        'cleanup', p_test.spec -> 'cleanup');
END $fn$;

COMMENT ON FUNCTION rk2_replay_offer(tests, uuid, text, text[]) IS
  'Ticket 35 steps k-l, ticket 38 extraction: the capability, and the plan the runner performs under it. One document shape for both openers, so the runner parses one.';

CREATE OR REPLACE FUNCTION open_test_replay(p_agent_run_id uuid, p_test_id uuid,
                                            p_identity_slot text DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p         uuid := rk2_program_required();
    v_subject record;
    v_run     agent_runs%ROWTYPE;
    v_test    tests%ROWTYPE;
    v_status  text;
    v_methods text[];
BEGIN
    SELECT * INTO v_subject FROM rk2_replay_subject(p, p_agent_run_id, p_test_id);
    v_run  := v_subject.r_run;
    v_test := v_subject.r_test;

    -- Ticket 38: an impact Test settles no claim, needs an operator grant and
    -- is opened by the verb that asks for one. Refused here rather than
    -- silently admitted, because everything below this line would move the
    -- claim the Finding rests on.
    IF v_test.impact_class IS NOT NULL THEN
        RAISE EXCEPTION 'test % states an impact and is not run as a detection replay',
            v_test.label
            USING ERRCODE = '42501',
                  HINT = 'open_impact_replay runs it, under a grant, without touching the claim';
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

    v_methods := rk2_replay_plan(p, v_run, v_test, p_identity_slot);
    RETURN rk2_replay_offer(
        v_test, rk2_open_replay(p, v_run, v_test, p_identity_slot, v_methods),
        p_identity_slot, v_methods);
END $fn$;

CREATE FUNCTION rk2_settle_replay(p_tool_run_id uuid, p_cleanup text)
RETURNS TABLE (r_replay test_replays, r_run tool_runs, r_test tests,
               r_test_run_id uuid, r_outcome text, r_eval jsonb, r_actions bigint)
LANGUAGE plpgsql AS $fn$
DECLARE p uuid := rk2_program_required();
BEGIN
    IF NOT (p_cleanup = ANY (rk2_test_cleanup_states())) THEN
        RAISE EXCEPTION 'a replay reports its cleanup as done, failed or skipped, not %',
            p_cleanup USING ERRCODE = '22023';
    END IF;

    SELECT tp.* INTO r_replay FROM test_replays tp
     WHERE tp.tool_run_id = p_tool_run_id AND tp.program_id = p
       FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'tool run % is not a replay of this Program', p_tool_run_id
            USING ERRCODE = '23503';
    END IF;
    SELECT * INTO r_run FROM tool_runs WHERE id = p_tool_run_id FOR UPDATE;
    IF r_run.status <> 'running' THEN
        RAISE EXCEPTION 'replay % was already closed as %', r_run.label, r_run.status
            USING ERRCODE = '23514';
    END IF;
    SELECT * INTO r_test FROM tests WHERE id = r_replay.test_id;

    r_eval    := evaluate_test_assertions(p_tool_run_id);
    r_outcome := r_eval ->> 'outcome';
    SELECT count(*) INTO r_actions FROM test_replay_actions
     WHERE tool_run_id = p_tool_run_id;

    PERFORM set_actor('runtime');
    INSERT INTO test_runs
        (program_id, test_id, agent_run_id, lane, outcome, assertion_results,
         started_at, finished_at)
    VALUES
        (p, r_replay.test_id, r_run.agent_run_id, 'replay', r_outcome,
         (r_eval - 'outcome') || jsonb_build_object('cleanup', p_cleanup),
         r_replay.started_at, now())
    RETURNING id INTO r_test_run_id;

    -- The link first, and the Receipts under it. 035's section 10 second arm
    -- asks which Tool run a Test run's Receipts may come from, and it reads the
    -- answer off `test_replays.test_run_id`; written the other way round, the
    -- rows below would arrive before there was anything to check them against,
    -- and the arm would hold for every writer except the one that produces
    -- every row it will ever see.
    UPDATE test_replays SET test_run_id = r_test_run_id
     WHERE tool_run_id = p_tool_run_id;

    INSERT INTO test_run_receipts (program_id, test_run_id, receipt_id, ordinal, role)
    SELECT p, r_test_run_id, a.receipt_id, a.ordinal, a.role
      FROM test_replay_actions a
     WHERE a.tool_run_id = p_tool_run_id
     ORDER BY a.ordinal;

    RETURN NEXT;
END $fn$;

COMMENT ON FUNCTION rk2_settle_replay(uuid, text) IS
  'Ticket 35, ticket 38 extraction: everything both close verbs do first -- lock the replay, evaluate the assertions, write the Test run and its Receipts. The Tool run is deliberately left running, because what each caller writes next is written while its own capability is still the one that is open; `rk2_finish_replay` is the other half, and both callers end with it.';

-- The other half, and the last thing either closer does. The credential dies
-- with the run: `guard_tool_run_authorization` clears it on any row that stops
-- running, which is why this statement says nothing about it. The status is
-- read back off the row rather than restated, so no caller has to name the
-- Tool run's vocabulary for a column it just wrote.
CREATE FUNCTION rk2_finish_replay(p_tool_run_id uuid, p_outcome text) RETURNS text
LANGUAGE plpgsql AS $fn$
DECLARE v_status text;
BEGIN
    UPDATE tool_runs
       SET status = (SELECT o.tool_run_status FROM rk2_test_outcome(p_outcome) o),
           finished_at = now()
     WHERE id = p_tool_run_id
    RETURNING status INTO v_status;
    RETURN v_status;
END $fn$;

COMMENT ON FUNCTION rk2_finish_replay(uuid, text) IS
  'Ticket 38. Stops a replay Tool run at the word its outcome maps to, and hands that word back. One statement, because both closers end the same way and a second copy of it is how one of them comes to leave a run running.';

CREATE OR REPLACE FUNCTION close_test_replay(p_tool_run_id uuid, p_cleanup text,
                                             p_detail text DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    v_settled  record;
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
    v_finished text;
    p          uuid := rk2_program_required();
BEGIN
    SELECT * INTO v_settled FROM rk2_settle_replay(p_tool_run_id, p_cleanup);
    v_run     := v_settled.r_run;
    v_test    := v_settled.r_test;
    v_run_id  := v_settled.r_test_run_id;
    v_outcome := v_settled.r_outcome;
    v_eval    := v_settled.r_eval;
    v_actions := v_settled.r_actions;
    SELECT * INTO v_means FROM rk2_test_outcome(v_outcome);

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

    v_finished := rk2_finish_replay(p_tool_run_id, v_outcome);

    RETURN jsonb_build_object(
        'tool_run', v_run.label,
        'status', v_finished,
        'test_run_id', v_run_id,
        'outcome', v_outcome,
        'failed', v_eval -> 'failed',
        'cleanup', p_cleanup,
        'actions', v_actions,
        'hypothesis_status', coalesce(v_status, 'testable'),
        'settle_refused', v_refused);
END $fn$;

-- ===========================================================================
-- 5. The impact run, and the grant it ran under
-- ===========================================================================

CREATE TABLE impact_replays (
    tool_run_id  uuid PRIMARY KEY,
    program_id   uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    finding_id   uuid NOT NULL,
    impact_class text NOT NULL REFERENCES impact_classes(impact_class),
    pending_decision_id uuid NOT NULL,
    equivalence_key     text NOT NULL,
    UNIQUE (tool_run_id, program_id),
    FOREIGN KEY (tool_run_id, program_id)
        REFERENCES test_replays (tool_run_id, program_id) ON DELETE CASCADE,
    FOREIGN KEY (finding_id, program_id)
        REFERENCES findings (id, program_id) ON DELETE CASCADE,
    FOREIGN KEY (pending_decision_id, program_id)
        REFERENCES pending_decisions (id, program_id) ON DELETE CASCADE
);

COMMENT ON TABLE impact_replays IS
  'Ticket 38: a replay that is proving impact, and the operator grant that was live when it opened. The equivalence key is kept beside the decision label so a grant that is later superseded still says what this run was authorized to be.';

CREATE TABLE impact_demonstrations (
    id           uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id   uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    finding_id   uuid NOT NULL,
    tool_run_id  uuid NOT NULL,
    test_run_id  uuid NOT NULL,
    run_outcome  text NOT NULL DEFAULT 'holds' CHECK (run_outcome = 'holds'),
    impact_class text NOT NULL REFERENCES impact_classes(impact_class),
    after_state_receipt_id uuid NOT NULL,
    cleanup      text NOT NULL CHECK (cleanup = 'done'),
    -- How many of the Test's stated undo requests actually reached the target
    -- under this run. `cleanup` is the supervisor's word for it; this is the
    -- door's, and a demonstration is only recorded when they agree.
    cleanup_receipts integer NOT NULL CHECK (cleanup_receipts >= 1),
    receipts     integer NOT NULL CHECK (receipts >= 1),
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, program_id),
    UNIQUE (test_run_id),
    FOREIGN KEY (finding_id, program_id)
        REFERENCES findings (id, program_id) ON DELETE CASCADE,
    FOREIGN KEY (tool_run_id, program_id)
        REFERENCES impact_replays (tool_run_id, program_id) ON DELETE CASCADE,
    FOREIGN KEY (test_run_id, program_id)
        REFERENCES test_runs (id, program_id) ON DELETE CASCADE,
    -- MATCH FULL, as 036 does for a validated Finding: the row cannot name a
    -- Test run whose outcome is anything but `holds`, and cannot be left
    -- pointing at one whose outcome later reads differently.
    FOREIGN KEY (test_run_id, run_outcome)
        REFERENCES test_runs (id, outcome) MATCH FULL,
    FOREIGN KEY (after_state_receipt_id, program_id)
        REFERENCES receipts (id, program_id) ON DELETE CASCADE
);

COMMENT ON TABLE impact_demonstrations IS
  'Ticket 38 criterion 4: impact that was demonstrated rather than inferred. One row per holding impact run whose cleanup was performed and whose after-state action produced a Receipt. Every column is a fact about a run that happened; there is no field a model writes.';

-- ===========================================================================
-- 6. Opening the impact work, and running it
-- ===========================================================================

CREATE FUNCTION open_impact_task(p_finding uuid, p_spec jsonb,
                                 p_created_by_run uuid DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p       uuid := rk2_program_required();
    v_find  findings%ROWTYPE;
    v_class text := p_spec -> 'impact' ->> 'class';
    v_risk  text;
    v_hyp   uuid;
    v_test  tests%ROWTYPE;
    v_task  tasks%ROWTYPE;
BEGIN
    SELECT * INTO v_find FROM findings
     WHERE id = p_finding AND program_id = p FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'finding % is not a Finding of this Program', p_finding
            USING ERRCODE = '23503';
    END IF;
    -- Criterion 3 read forwards: impact is proved on a detection that is
    -- already validated, so nothing this ticket does can be what validates one.
    IF v_find.status <> 'validated' THEN
        RAISE EXCEPTION 'finding % is % and impact is proved on a validated detection',
            v_find.label, v_find.status USING ERRCODE = '23514';
    END IF;
    IF v_class IS NULL THEN
        RAISE EXCEPTION 'this specification states no impact to authorize'
            USING ERRCODE = '22023',
                  HINT = 'a Test with no impact block is a detection Test and runs through rk test replay';
    END IF;

    SELECT ic.risk_class INTO v_risk FROM impact_classes ic
     WHERE ic.impact_class = v_class;
    IF v_risk IS NULL THEN
        RAISE EXCEPTION 'no impact class named %', v_class USING ERRCODE = '23503';
    END IF;
    -- Criterion 5, at the earliest point it can be said. A forbidden class is
    -- refused here rather than at the door, because the alternative is a Test
    -- row, a Task row and a question a human might feel able to answer.
    PERFORM rk2_refuse_forbidden_impact(v_class, v_risk);

    SELECT fh.hypothesis_id INTO v_hyp FROM finding_hypotheses fh
     WHERE fh.finding_id = p_finding ORDER BY fh.hypothesis_id LIMIT 1;
    IF v_hyp IS NULL THEN
        RAISE EXCEPTION 'finding % rests on no claim to test against', v_find.label
            USING ERRCODE = '23503';
    END IF;

    PERFORM set_actor('runtime');
    INSERT INTO tests (program_id, hypothesis_id, spec, spec_sha256, impact_class,
                       created_by_run_id)
    VALUES (p, v_hyp, p_spec, rk2_test_spec_digest(p_spec), v_class, p_created_by_run)
    RETURNING * INTO v_test;

    -- A `hunt` Task naming the Finding: distinct from the hunt that produced
    -- the claim, because that one names no Finding, so 008's live-dedup index
    -- separates them without being told to.
    INSERT INTO tasks (program_id, kind, subject_entity_id, hypothesis_id, finding_id)
    VALUES (p, 'hunt', v_find.subject_entity_id, v_hyp, p_finding)
    RETURNING * INTO v_task;

    -- No equivalence key is handed back. The grant is over the Identity the run
    -- will hold as well as over the Test, and which Identity that is belongs to
    -- the run and not to the writing of the Test: a key computed here would be
    -- one no approval could ever match.
    RETURN jsonb_build_object(
        'finding', v_find.label, 'test', v_test.label, 'task', v_task.label,
        'impact_class', v_class, 'risk_class', v_risk);
END $fn$;

COMMENT ON FUNCTION open_impact_task(uuid, jsonb, uuid) IS
  'Ticket 38: turn a validated Finding into impact work -- one immutable Test stating class, effect, cleanup and after-state, and one Task to run it under. Refuses a Finding that is not validated and a class no operator may grant.';

-- 029's rule about who may read a question: the runtime writes one and never
-- reads one, so `rk2_runtime` holds INSERT on `pending_decisions` and no SELECT
-- at all. `RETURNING *` is a read, which is why 026's own park is a definer
-- function -- and why this is one too. It hands back the three fields the caller
-- has to park a Task and answer with, and nothing else: the answer column is
-- still out of the runtime's reach.
--
-- A question already waiting is answered rather than asked again. 026's unique
-- index only covers approvals, so nothing above this would stop a second run
-- from filing a second copy of a question nobody has got to yet -- and each
-- park overwrites `tasks.pending_decision_id`, so the first copy would be left
-- pointing at a Task that no longer points back. One key, one open question.
CREATE FUNCTION rk2_ask_about_impact(p_task uuid, p_test uuid, p_risk text,
                                     p_rule text, p_digest jsonb, p_ttl interval)
RETURNS TABLE (r_id uuid, r_label text, r_question text)
LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'public' AS $fn$
DECLARE p uuid := rk2_program_required();
BEGIN
    SELECT d.id, d.label, d.question INTO r_id, r_label, r_question
      FROM pending_decisions d
     WHERE d.program_id = p AND d.status = 'pending'
       AND d.equivalence_key = equivalence_key(p_digest)
       AND d.deadline_at > now()
     ORDER BY d.deadline_at DESC LIMIT 1;
    IF FOUND THEN
        RETURN NEXT;
        RETURN;
    END IF;

    PERFORM set_actor('runtime');
    INSERT INTO pending_decisions
        (program_id, task_id, test_id, tool, risk_class, risk_rule,
         question_code, request_digest, equivalence_key, question, deadline_at)
    VALUES (p, p_task, p_test, rk2_replay_tool(), p_risk, p_rule,
            'impact_unauthorized', p_digest, equivalence_key(p_digest),
            render_decision_question(p_digest, p_risk, p_rule), now() + p_ttl)
    RETURNING id, label, question INTO r_id, r_label, r_question;
    RETURN NEXT;
END $fn$;

COMMENT ON FUNCTION rk2_ask_about_impact(uuid, uuid, text, text, jsonb, interval) IS
  'Ticket 38: file the impact question and hand back its id, label and words, or hand back the open question that already asks it. Definer because the runtime may write a question and may not read one.';

CREATE FUNCTION open_impact_replay(p_agent_run_id uuid, p_test_id uuid,
                                   p_identity_slot text DEFAULT NULL,
                                   p_ttl interval DEFAULT interval '24 hours')
RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p          uuid := rk2_program_required();
    v_subject  record;
    v_run      agent_runs%ROWTYPE;
    v_test     tests%ROWTYPE;
    v_task     tasks%ROWTYPE;
    v_find     findings%ROWTYPE;
    v_risk     text;
    v_rule     text;
    v_digest   jsonb;
    v_key      text;
    v_grant    text;
    v_decision record;
    v_methods  text[];
    v_id       uuid;
BEGIN
    SELECT * INTO v_subject FROM rk2_replay_subject(p, p_agent_run_id, p_test_id);
    v_run  := v_subject.r_run;
    v_test := v_subject.r_test;

    IF v_test.impact_class IS NULL THEN
        RAISE EXCEPTION 'test % states no impact', v_test.label
            USING ERRCODE = '42501',
                  HINT = 'open_test_replay runs a detection Test and settles its claim';
    END IF;
    IF v_run.task_id IS NULL THEN
        RAISE EXCEPTION 'impact is proved under its own Task, and run % holds none',
            v_run.label USING ERRCODE = '23514';
    END IF;
    SELECT * INTO v_task FROM tasks WHERE id = v_run.task_id AND program_id = p
       FOR UPDATE;
    IF v_task.finding_id IS NULL THEN
        RAISE EXCEPTION 'task % names no Finding to prove impact on', v_task.label
            USING ERRCODE = '23514';
    END IF;

    SELECT * INTO v_find FROM findings
     WHERE id = v_task.finding_id AND program_id = p FOR UPDATE;
    IF v_find.status <> 'validated' THEN
        RAISE EXCEPTION 'finding % is % and impact is proved on a validated detection',
            v_find.label, v_find.status USING ERRCODE = '23514';
    END IF;

    SELECT ic.risk_class INTO v_risk FROM impact_classes ic
     WHERE ic.impact_class = v_test.impact_class;
    -- Asked twice on purpose: `open_impact_task` refused the class when the
    -- Test was written, and this is the same question at the moment a request
    -- would be sent.
    PERFORM rk2_refuse_forbidden_impact(v_test.impact_class, v_risk);

    IF EXISTS (SELECT 1 FROM impact_replays ir
                 JOIN tool_runs tr ON tr.id = ir.tool_run_id
                WHERE ir.program_id = p AND ir.finding_id = v_find.id
                  AND tr.status = 'running') THEN
        RAISE EXCEPTION 'an impact replay of % is already in flight', v_find.label
            USING ERRCODE = '23514';
    END IF;

    v_rule   := 'impact_classes:' || v_test.impact_class;
    v_digest := rk2_impact_digest(p, v_find.id, v_test.id, p_identity_slot);
    v_key    := equivalence_key(v_digest);
    v_grant  := live_grant_for(p, v_key);

    IF v_grant IS NULL THEN
        -- Criterion 2. Nothing has been written that could reach the target:
        -- there is no Tool run, so there is no capability, so the door has
        -- nothing to let through. The Task waits, the run ends, the leases go
        -- back, and a human is asked.
        PERFORM set_actor('runtime');
        SELECT * INTO v_decision
          FROM rk2_ask_about_impact(v_task.id, v_test.id, v_risk, v_rule,
                                    v_digest, p_ttl);

        UPDATE tasks SET status = 'parked', pending_decision_id = v_decision.r_id,
                         claimed_at = NULL, priority = NULL
         WHERE id = v_task.id;
        PERFORM release_leases(v_run.id);
        UPDATE agent_runs SET finished_at = now(), stop_reason = 'parked', result = NULL
         WHERE id = v_run.id AND finished_at IS NULL;
        UPDATE agent_sessions SET unbound_at = now()
         WHERE agent_run_id = v_run.id AND unbound_at IS NULL;

        RETURN jsonb_build_object(
            'parked', v_decision.r_label, 'question', v_decision.r_question,
            'finding', v_find.label, 'test', v_test.label, 'task', v_task.label,
            'impact_class', v_test.impact_class, 'risk_class', v_risk,
            'refusal', 'no live operator grant covers ' || v_test.label);
    END IF;

    v_methods := rk2_replay_plan(p, v_run, v_test, p_identity_slot);
    v_id      := rk2_open_replay(p, v_run, v_test, p_identity_slot, v_methods);

    -- Before the gate, for 035's reason: the row that says this replay is
    -- authorized impact has to exist by the time a capability does, so a
    -- Receipt can never arrive under a run nobody can attribute to a grant.
    INSERT INTO impact_replays (tool_run_id, program_id, finding_id, impact_class,
                                pending_decision_id, equivalence_key)
    SELECT v_id, p, v_find.id, v_test.impact_class, d.id, v_key
      FROM pending_decisions d WHERE d.program_id = p AND d.label = v_grant;

    RETURN rk2_replay_offer(v_test, v_id, p_identity_slot, v_methods)
           || jsonb_build_object(
                  'finding', v_find.label, 'grant', v_grant,
                  'impact_class', v_test.impact_class, 'risk_class', v_risk,
                  'impact', v_test.spec -> 'impact');
END $fn$;

COMMENT ON FUNCTION open_impact_replay(uuid, uuid, text, interval) IS
  'Ticket 38 criterion 2: open a replay of an impact Test, or park the Task for a human. The grant is looked for before any Tool run exists, so a missing or mismatched one costs the target nothing.';

CREATE FUNCTION close_impact_replay(p_tool_run_id uuid, p_cleanup text,
                                    p_detail text DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p         uuid := rk2_program_required();
    v_impact  impact_replays%ROWTYPE;
    v_settled record;
    v_run     tool_runs%ROWTYPE;
    v_test    tests%ROWTYPE;
    v_run_id  uuid;
    v_outcome text;
    v_eval    jsonb;
    v_actions bigint;
    v_after   integer;
    v_receipt uuid;
    v_shown   uuid;
    v_refusal text;
    v_undone  bigint;
    v_undo    bigint;
    v_finished text;
BEGIN
    SELECT * INTO v_impact FROM impact_replays
     WHERE tool_run_id = p_tool_run_id AND program_id = p FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'tool run % is not an impact replay of this Program',
            p_tool_run_id USING ERRCODE = '23503';
    END IF;

    SELECT * INTO v_settled FROM rk2_settle_replay(p_tool_run_id, p_cleanup);
    v_run     := v_settled.r_run;
    v_test    := v_settled.r_test;
    v_run_id  := v_settled.r_test_run_id;
    v_outcome := v_settled.r_outcome;
    v_eval    := v_settled.r_eval;
    v_actions := v_settled.r_actions;

    -- Criterion 4: the demonstration is the conjunction, not any one of them.
    -- A holding run whose cleanup failed left the target changed; a run whose
    -- after-state action produced no Receipt read nothing back; a run that did
    -- not hold proved what it set out to disprove or nothing at all.
    v_after := (v_test.spec -> 'impact' ->> 'after_state')::numeric::integer;
    SELECT a.receipt_id INTO v_receipt FROM test_replay_actions a
     WHERE a.tool_run_id = p_tool_run_id AND a.ordinal = v_after;

    -- And the cleanup, which is otherwise a word the supervisor chose. The Test
    -- states the requests that put the target back; the door wrote a Receipt for
    -- each one it actually sent. A run reporting `done` having sent none of them
    -- is a run reporting on work it did not do -- and the operator's grant was
    -- over a side effect *and its undoing*, so the two are one condition.
    -- Counted per stated request rather than over the run's Receipts as a whole,
    -- because a setup request answers no recorded action either.
    v_undo := jsonb_array_length(v_test.spec -> 'cleanup');
    SELECT count(*) INTO v_undone
      FROM jsonb_array_elements(v_test.spec -> 'cleanup') c
      CROSS JOIN LATERAL rk2_test_route(c ->> 'url') u
     WHERE EXISTS (SELECT 1 FROM receipts r
                    WHERE r.tool_run_id = p_tool_run_id
                      AND r.method = upper(c ->> 'method')
                      AND r.scheme = u.scheme AND r.host = u.host
                      AND r.port = u.port AND r.path = u.path);

    -- The supervisor's own account of what went wrong is carried into the
    -- refusal rather than stored: an impact run writes no transition, so there
    -- is no rationale column for it, and the sentence an operator reads is the
    -- only place it would ever be looked for.
    v_refusal := CASE
        WHEN v_outcome <> 'holds'  THEN 'the run concluded ' || v_outcome
        WHEN p_cleanup <> 'done'   THEN 'the cleanup was reported ' || p_cleanup
        WHEN v_receipt IS NULL     THEN 'no Receipt answered the after-state action'
        WHEN v_undone < v_undo     THEN format('the cleanup was reported done and %s of'
                                               || ' the %s requests that undo it were sent',
                                               v_undone, v_undo)
    END;
    IF v_refusal IS NOT NULL THEN
        v_refusal := 'no impact is demonstrated: ' || v_refusal
                     || coalesce(' (' || nullif(p_detail, '') || ')', '');
    END IF;

    IF v_refusal IS NULL THEN
        INSERT INTO impact_demonstrations
            (program_id, finding_id, tool_run_id, test_run_id, impact_class,
             after_state_receipt_id, cleanup, cleanup_receipts, receipts)
        VALUES (p, v_impact.finding_id, p_tool_run_id, v_run_id,
                v_impact.impact_class, v_receipt, p_cleanup, v_undone, v_actions)
        RETURNING id INTO v_shown;
    END IF;

    -- Criterion 3, and the whole reason this verb exists beside the other one:
    -- no Observation, no Evidence edge, no transition. Whatever this run did,
    -- the claim the detection rests on is exactly as `close_test_replay` left it.
    v_finished := rk2_finish_replay(p_tool_run_id, v_outcome);

    RETURN jsonb_build_object(
        'tool_run', v_run.label,
        'status', v_finished,
        'test_run_id', v_run_id,
        'outcome', v_outcome,
        'failed', v_eval -> 'failed',
        'cleanup', p_cleanup,
        'actions', v_actions,
        'finding', (SELECT label FROM findings WHERE id = v_impact.finding_id),
        'hypothesis_status',
            (SELECT status FROM hypotheses WHERE id = v_test.hypothesis_id),
        'demonstration', v_shown,
        'cleanup_receipts', v_undone,
        'demonstration_refused', v_refusal);
END $fn$;

COMMENT ON FUNCTION close_impact_replay(uuid, text, text) IS
  'Ticket 38 criteria 3 and 4: close an impact replay, and record a demonstration only when the run held, the after-state was read back and every request the Test states as its undo was actually sent. Writes nothing about the Hypothesis: an impact run is not evidence for or against the detection.';


-- The recorder both closers sit on. 035 wrote a `testable` -> `testing`
-- transition on the first action of a replay, because in 035 the only reason to
-- replay a Test was to settle the claim it was written for. An impact run
-- replays a Test whose claim is already `supported`, and the transition would be
-- refused by `enforce_hypothesis_transition` -- correctly, and one action too
-- late, with the Receipt already sent. Criterion 3 is the same rule as the one
-- `close_impact_replay` keeps at the other end of the run: an impact replay
-- moves nothing about the Hypothesis, so it does not start it testing either.
-- `started_testing` is the answer to that question and not to 'is this the first
-- action', which is why the flag itself carries the condition.
CREATE OR REPLACE FUNCTION record_test_action(
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
       AND NOT EXISTS (SELECT 1 FROM impact_replays i
                        WHERE i.tool_run_id = p_tool_run_id)
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
    'and move the claim to `testing` on the first one -- unless the run is an '
    'impact replay, which moves nothing about the Hypothesis. Refuses a Receipt '
    'from another Tool run, a Receipt outside the replay Lane, a Receipt that '
    'answers a different request than the action states, and an ordinal this '
    'Test does not perform.';

-- ===========================================================================
-- 7. Severity is stated, with a basis and a reason
-- ===========================================================================
--
-- Criterion 6. 019 gave `findings` a `severity_basis` column and a CHECK that a
-- non-info severity carries one; nothing ever wrote either. Two things were
-- missing: somewhere to put the rationale, and a rule that the column cannot be
-- set except by something that produced one.

CREATE TABLE severity_statements (
    id            uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id    uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    finding_id    uuid NOT NULL,
    severity      text NOT NULL
        CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    basis         text NOT NULL
        CHECK (basis IN ('demonstrated_impact', 'constrained_inference',
                         'program_context')),
    rationale     text NOT NULL CHECK (length(rationale) BETWEEN 20 AND 2000),
    impact_demonstration_id uuid,
    scope_version integer NOT NULL,
    stated_by_run_id uuid,
    actor_kind    text NOT NULL CHECK (actor_kind IN ('human', 'runtime')),
    created_at    timestamptz NOT NULL DEFAULT now(),
    -- The basis and the evidence for it are one fact: a demonstrated severity
    -- names the demonstration, and nothing else may.
    CONSTRAINT severity_statements_basis_names_its_evidence
        CHECK ((basis = 'demonstrated_impact') = (impact_demonstration_id IS NOT NULL)),
    UNIQUE (id, program_id),
    FOREIGN KEY (finding_id, program_id)
        REFERENCES findings (id, program_id) ON DELETE CASCADE,
    FOREIGN KEY (impact_demonstration_id, program_id)
        REFERENCES impact_demonstrations (id, program_id) ON DELETE CASCADE,
    FOREIGN KEY (stated_by_run_id, program_id)
        REFERENCES agent_runs (id, program_id) ON DELETE CASCADE,
    FOREIGN KEY (program_id, scope_version)
        REFERENCES program_scope_versions (program_id, version)
);

COMMENT ON TABLE severity_statements IS
  'Ticket 38 criterion 6: every severity this harness has ever put on a Finding, with the basis it was read from, the reason in words, and the scope version in force when it was said. Append-only: a severity that changed is two rows, and the later one has to say why.';

CREATE INDEX severity_statements_finding_idx
    ON severity_statements (finding_id, created_at DESC, id DESC);

CREATE FUNCTION state_severity(p_finding uuid, p_severity text, p_basis text,
                               p_rationale text)
RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p       uuid := rk2_program_required();
    v_find  findings%ROWTYPE;
    v_shown uuid;
    v_scope integer;
    v_id    uuid;
BEGIN
    SELECT * INTO v_find FROM findings
     WHERE id = p_finding AND program_id = p FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'finding % is not a Finding of this Program', p_finding
            USING ERRCODE = '23503';
    END IF;
    IF v_find.status NOT IN ('validated', 'reported') THEN
        RAISE EXCEPTION 'finding % is % and severity is stated about a validated Finding',
            v_find.label, v_find.status USING ERRCODE = '23514';
    END IF;

    -- The three bases, and the thing each one requires to exist before the word
    -- may be said. This is the whole of criterion 6: they are distinguished
    -- because each is refused unless its own evidence is there.
    IF p_basis = 'demonstrated_impact' THEN
        SELECT d.id INTO v_shown FROM impact_demonstrations d
         WHERE d.finding_id = p_finding AND d.program_id = p
         ORDER BY d.created_at DESC, d.id DESC LIMIT 1;
        IF v_shown IS NULL THEN
            RAISE EXCEPTION 'no impact has been demonstrated for %', v_find.label
                USING ERRCODE = '23514',
                      HINT = 'run the impact Test and let it hold, or state the severity on the basis you have';
        END IF;
    ELSIF p_basis = 'constrained_inference' THEN
        -- The word means what it says: the behaviour was witnessed and what it
        -- is worth was reasoned about rather than shown. A Finding that has a
        -- demonstration is not one anybody has to infer about, and calling an
        -- inference what there is proof of is how a severity comes to rest on
        -- the weaker of the two things somebody was holding.
        IF EXISTS (SELECT 1 FROM impact_demonstrations d
                    WHERE d.finding_id = p_finding AND d.program_id = p) THEN
            RAISE EXCEPTION 'finding % has a demonstrated impact and needs no inference',
                v_find.label
                USING ERRCODE = '23514',
                      HINT = 'state it on demonstrated_impact, which is the basis that is there';
        END IF;
    ELSIF p_basis = 'program_context' THEN
        -- Nothing was demonstrated and nothing about worth was witnessed: what
        -- is left is what this Program says it pays for. That is a real basis
        -- and it is the weakest of the three, so it does not reach the two words
        -- that make a Finding somebody else's emergency. Those are claims about
        -- the target; this basis is a reading of a document.
        IF p_severity IN ('high', 'critical') THEN
            RAISE EXCEPTION 'the Program context alone does not make % a % Finding',
                v_find.label, p_severity
                USING ERRCODE = '23514',
                      HINT = 'demonstrate the impact, or infer it from what the Finding itself showed';
        END IF;
    ELSE
        RAISE EXCEPTION 'severity rests on a demonstration, a constrained inference or the Program context, not on %',
            p_basis USING ERRCODE = '22023';
    END IF;

    SELECT pr.scope_version INTO v_scope FROM programs pr WHERE pr.id = p;

    PERFORM set_actor(CASE WHEN human_actor_session() THEN 'human' ELSE 'runtime' END);
    INSERT INTO severity_statements
        (program_id, finding_id, severity, basis, rationale,
         impact_demonstration_id, scope_version, stated_by_run_id, actor_kind)
    VALUES (p, p_finding, p_severity, p_basis, p_rationale, v_shown, v_scope,
            nullif(current_setting('app.agent_run_id', true), '')::uuid,
            CASE WHEN human_actor_session() THEN 'human' ELSE 'runtime' END)
    RETURNING id INTO v_id;

    UPDATE findings SET severity = p_severity, severity_basis = p_basis
     WHERE id = p_finding;

    RETURN jsonb_build_object(
        'finding', v_find.label, 'statement', v_id,
        'severity', p_severity, 'was', v_find.severity,
        'basis', p_basis, 'demonstration', v_shown, 'scope_version', v_scope);
END $fn$;

COMMENT ON FUNCTION state_severity(uuid, text, text, text) IS
  'Ticket 38 criterion 6: the only writer of findings.severity. The three bases are distinguished because each is refused for its own reason -- a demonstrated severity with no demonstration, an inference about a Finding that has one, and a high or critical severity read out of nothing but the Program document.';

-- And the other half: the column cannot be moved by anything else. The guard
-- reads the latest statement rather than trusting the caller, so a hand-written
-- UPDATE is refused even inside the same transaction as a statement that says
-- something different.
CREATE FUNCTION assert_severity_was_stated() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE s record;
BEGIN
    IF (NEW.severity, NEW.severity_basis) IS NOT DISTINCT FROM
       (OLD.severity, OLD.severity_basis) THEN
        RETURN NEW;
    END IF;
    SELECT st.severity, st.basis INTO s FROM severity_statements st
     WHERE st.finding_id = NEW.id
     ORDER BY st.created_at DESC, st.id DESC LIMIT 1;
    IF s IS NULL THEN
        RAISE EXCEPTION 'nothing has stated a severity for %', NEW.label
            USING ERRCODE = '23514',
                  HINT = 'state_severity() records the basis and the reason, and then moves the column';
    END IF;
    IF (NEW.severity, NEW.severity_basis) IS DISTINCT FROM (s.severity, s.basis) THEN
        RAISE EXCEPTION 'the latest severity stated for % is % on %, not % on %',
            NEW.label, s.severity, s.basis, NEW.severity, NEW.severity_basis
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $fn$;

CREATE TRIGGER findings_severity_is_stated
    BEFORE UPDATE ON findings
    FOR EACH ROW EXECUTE FUNCTION assert_severity_was_stated();

-- 019 wrote a function that set a severity from a CVSS vector with no basis and
-- no reason, and nothing in this corpus ever called it. Criterion 6 is exactly
-- the rule it would break, so what it computed stays and what it decided goes:
-- the vector is a derived fact, the band is a judgement, and only
-- `state_severity` makes judgements now.
DROP FUNCTION apply_computed_severity(uuid);

CREATE FUNCTION apply_computed_cvss(p_finding uuid) RETURNS text
LANGUAGE plpgsql AS $fn$
DECLARE v text;
BEGIN
    v := compute_finding_cvss(p_finding);
    IF v IS NULL THEN
        RAISE EXCEPTION 'finding % has no witnessed effect: nothing to score', p_finding;
    END IF;
    PERFORM set_actor('runtime');
    UPDATE findings SET cvss_vector = v WHERE id = p_finding;
    RETURN v;
END $fn$;

COMMENT ON FUNCTION apply_computed_cvss(uuid) IS
  'Ticket 19, narrowed by ticket 38: writes the CVSS vector derived from what the Finding witnessed, and nothing else. The severity band that used to be written beside it is a judgement, and judgements go through state_severity.';

-- 019's report gate. Six of its seven arms are untouched. The seventh asked
-- one question about two things -- the vector, and the band derived from it --
-- and the band is no longer derived: `state_severity` puts it there with a
-- basis, so a Finding whose stated severity differs from what CVSS would have
-- computed is a Finding somebody made a judgement about, not a stale one. What
-- is left of that arm is the vector, and the two questions criterion 6 asks
-- about the band are added beside it.
CREATE OR REPLACE FUNCTION report_blockers(p_finding uuid)
RETURNS TABLE (severity text, code text, detail text)
LANGUAGE sql STABLE AS $fn$
    -- a program said in writing it does not want this
    SELECT 'hard', 'known_issue', k.note
      FROM findings f
      JOIN entities e ON e.id = f.subject_entity_id
      JOIN program_known_issues k
        ON k.program_id = f.program_id AND k.class_id = f.class_id
       AND (k.entity_like IS NULL OR e.dedup_key LIKE k.entity_like)
     WHERE f.id = p_finding
    UNION ALL
    -- already told them, or about to tell them twice
    SELECT 'hard', 'duplicate', 'same signature as ' || o.label || ' (' || o.status || ')'
      FROM findings f JOIN findings o
        ON o.program_id = f.program_id AND o.id <> f.id
       AND finding_signature(o.id) = finding_signature(f.id)
       AND o.status IN ('validated','reported')
     WHERE f.id = p_finding AND f.duplicate_of_finding_id IS NULL
    UNION ALL
    -- ticket 06's rule, restated where the reporter can see it
    SELECT 'hard', 'not_validated', 'status=' || f.status ||
           ', validated_by_test_run_id=' || coalesce(f.validated_by_test_run_id::text,'null')
      FROM findings f
     WHERE f.id = p_finding
       AND (f.status <> 'validated' OR f.validated_by_test_run_id IS NULL)
    UNION ALL
    SELECT 'hard', 'no_effect', 'no finding_effects row: the impact sentence has nothing to say'
      FROM findings f WHERE f.id = p_finding
       AND NOT EXISTS (SELECT 1 FROM finding_effects fe WHERE fe.finding_id = f.id)
    UNION ALL
    SELECT 'hard', 'no_chain', 'no finding_chain_steps row'
      FROM findings f WHERE f.id = p_finding
       AND NOT EXISTS (SELECT 1 FROM finding_chain_steps s WHERE s.finding_id = f.id)
    UNION ALL
    -- ticket 38: the vector alone. The band beside it is now a stated
    -- judgement, and the two arms below are what may be wrong with it.
    SELECT 'hard', 'cvss_stale',
           'stored ' || coalesce(f.cvss_vector,'null') || ', computed ' || c.vec
      FROM findings f CROSS JOIN LATERAL (SELECT compute_finding_cvss(f.id) AS vec) c
     WHERE f.id = p_finding AND c.vec IS NOT NULL
       AND f.cvss_vector IS DISTINCT FROM c.vec
    UNION ALL
    -- ticket 38 criterion 6: a severity nobody stated is a severity nobody can
    -- be asked to defend
    SELECT 'hard', 'severity_unstated',
           'severity=' || f.severity || ' on an undetermined basis'
      FROM findings f
     WHERE f.id = p_finding AND f.severity_basis = 'undetermined'
    UNION ALL
    -- ticket 38 criterion 6: the statement the band rests on read a scope
    -- document that has since moved, so the program context it weighed is not
    -- the program context now
    SELECT 'soft', 'severity_scope_moved',
           'stated at scope version ' || s.scope_version ||
           ', the Program is at ' || pr.scope_version
      FROM findings f
      JOIN programs pr ON pr.id = f.program_id
      JOIN LATERAL (SELECT x.scope_version FROM severity_statements x
                     WHERE x.finding_id = f.id
                     ORDER BY x.created_at DESC, x.id DESC LIMIT 1) s ON true
     WHERE f.id = p_finding AND s.scope_version <> pr.scope_version
    UNION ALL
    -- a witnessed effect whose witness is not among the finding's evidence
    SELECT 'hard', 'unwitnessed_effect', 'effect ' || fe.effect_id || ' cites an observation the finding does not'
      FROM finding_effects fe
     WHERE fe.finding_id = p_finding
       AND NOT EXISTS (SELECT 1 FROM finding_evidence x
                        WHERE x.finding_id = fe.finding_id AND x.observation_id = fe.witness_observation_id)
$fn$;

-- ===========================================================================
-- 8. Wiring: events, purge, isolation, grants
-- ===========================================================================

INSERT INTO event_types (id, family, subject_table, description) VALUES
    ('impact.demonstrated', 'row', 'impact_demonstrations',
     'an impact Test held, cleaned up after itself and read back the state it left'),
    ('finding.severity_stated', 'row', 'severity_statements',
     'a severity was put on a Finding, with the basis it was read from');

INSERT INTO event_table_config (table_name, created_type) VALUES
    ('impact_demonstrations', 'impact.demonstrated'),
    ('severity_statements',   'finding.severity_stated');

INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('impact_replays', 'covered',
     'written in the same transaction as the tool_runs row it decorates, which emits its own event', '38');

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('impact_replays', 'program_id',
     'program-scoped: the purge root'),
    ('impact_replays', 'tool_run_id',
     'ON DELETE CASCADE to test_replays: the replay this row says was authorized impact'),
    ('impact_replays', 'finding_id',
     'ON DELETE CASCADE to findings: the detection the impact was being proved on'),
    ('impact_replays', 'pending_decision_id',
     'ON DELETE CASCADE to pending_decisions: the grant it ran under'),
    ('impact_demonstrations', 'program_id',
     'program-scoped: the purge root'),
    ('impact_demonstrations', 'finding_id',
     'ON DELETE CASCADE to findings: a demonstration of nothing is nothing'),
    ('impact_demonstrations', 'tool_run_id',
     'ON DELETE CASCADE to impact_replays: the run that demonstrated it'),
    ('impact_demonstrations', 'test_run_id',
     'ON DELETE CASCADE to test_runs: the holding run this is the reading of'),
    ('impact_demonstrations', 'after_state_receipt_id',
     'ON DELETE CASCADE to receipts: the after-state is the Receipt, and without it there is no demonstration'),
    ('severity_statements', 'program_id',
     'program-scoped: the purge root'),
    ('severity_statements', 'finding_id',
     'ON DELETE CASCADE to findings: a severity about a Finding that is gone'),
    ('severity_statements', 'impact_demonstration_id',
     'ON DELETE CASCADE to impact_demonstrations: the evidence the basis names'),
    ('severity_statements', 'stated_by_run_id',
     'ON DELETE CASCADE to agent_runs: the run that said it');

SELECT attach_event_triggers();
SELECT attach_actor_kind_guards();

-- `rk2_state` is not granted here: 021 gives the state role its reads through
-- `state_read_surface` and `apply_state_grants()`, and a relation-level SELECT
-- beside that is a second read surface nobody registered.
GRANT SELECT ON impact_classes TO rk2_runtime, rk2_human;
GRANT SELECT, INSERT ON impact_replays, impact_demonstrations, severity_statements
    TO rk2_runtime;
GRANT SELECT ON impact_replays, impact_demonstrations, severity_statements
    TO rk2_human;

REVOKE ALL ON FUNCTION rk2_impact_problem(jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION rk2_impact_digest(uuid, uuid, uuid, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION rk2_refuse_forbidden_impact(text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION live_grant_for(uuid, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION rk2_replay_subject(uuid, uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION rk2_replay_plan(uuid, agent_runs, tests, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION rk2_open_replay(uuid, agent_runs, tests, text, text[]) FROM PUBLIC;
REVOKE ALL ON FUNCTION rk2_replay_offer(tests, uuid, text, text[]) FROM PUBLIC;
REVOKE ALL ON FUNCTION rk2_settle_replay(uuid, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION rk2_finish_replay(uuid, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION rk2_ask_about_impact(uuid, uuid, text, text, jsonb, interval)
    FROM PUBLIC;
REVOKE ALL ON FUNCTION open_impact_task(uuid, jsonb, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION open_impact_replay(uuid, uuid, text, interval) FROM PUBLIC;
REVOKE ALL ON FUNCTION close_impact_replay(uuid, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION state_severity(uuid, text, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION apply_computed_cvss(uuid) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION rk2_impact_problem(jsonb) TO rk2_state, rk2_runtime, rk2_human;
GRANT EXECUTE ON FUNCTION rk2_impact_digest(uuid, uuid, uuid, text) TO rk2_runtime, rk2_human;
GRANT EXECUTE ON FUNCTION rk2_refuse_forbidden_impact(text, text) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION live_grant_for(uuid, text) TO rk2_runtime, rk2_human;
GRANT EXECUTE ON FUNCTION rk2_replay_subject(uuid, uuid, uuid) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION rk2_replay_plan(uuid, agent_runs, tests, text) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION rk2_open_replay(uuid, agent_runs, tests, text, text[]) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION rk2_replay_offer(tests, uuid, text, text[]) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION rk2_settle_replay(uuid, text) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION rk2_finish_replay(uuid, text) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION rk2_ask_about_impact(uuid, uuid, text, text, jsonb, interval)
    TO rk2_runtime;
GRANT EXECUTE ON FUNCTION open_impact_task(uuid, jsonb, uuid) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION open_impact_replay(uuid, uuid, text, interval) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION close_impact_replay(uuid, text, text) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION state_severity(uuid, text, text, text) TO rk2_runtime, rk2_human;
GRANT EXECUTE ON FUNCTION apply_computed_cvss(uuid) TO rk2_runtime;

SELECT apply_state_rls();
SELECT apply_state_grants();
SELECT enforce_always_triggers();

-- ===========================================================================
-- 9. The standing check
-- ===========================================================================

CREATE FUNCTION check_impact_authorization()
RETURNS TABLE (problem text, detail text) LANGUAGE sql STABLE AS $fn$
    -- (a) a Test stating an impact nobody may ever grant
    SELECT 'test_states_a_forbidden_impact'::text, t.label
      FROM tests t
      JOIN impact_classes ic ON ic.impact_class = t.impact_class
      JOIN risk_classes rc   ON rc.risk_class = ic.risk_class
     WHERE rc.decision = 'deny'
UNION ALL
    -- (b) an impact run whose grant is not, and by 011's closing rule never
    --     was, an approval
    SELECT 'impact_replay_without_an_approval', tr.label
      FROM impact_replays ir
      JOIN tool_runs tr        ON tr.id = ir.tool_run_id
      JOIN pending_decisions d ON d.id = ir.pending_decision_id
     WHERE d.status <> 'approved' OR d.equivalence_key <> ir.equivalence_key
UNION ALL
    -- (c) an impact run whose Test does not state the class it was granted
    SELECT 'impact_replay_class_disagrees_with_its_test', tr.label
      FROM impact_replays ir
      JOIN tool_runs tr    ON tr.id = ir.tool_run_id
      JOIN test_replays rp ON rp.tool_run_id = ir.tool_run_id
      JOIN tests t         ON t.id = rp.test_id
     WHERE t.impact_class IS DISTINCT FROM ir.impact_class
UNION ALL
    -- (d) criterion 3: an impact run that moved a claim. Its Receipts are the
    --     Observations' provenance, so an Observation citing one is evidence
    --     this ticket promised not to produce.
    SELECT 'impact_run_produced_evidence', tr.label
      FROM impact_replays ir
      JOIN tool_runs tr ON tr.id = ir.tool_run_id
      JOIN test_replay_actions a ON a.tool_run_id = ir.tool_run_id
      JOIN observations o ON o.receipt_id = a.receipt_id
UNION ALL
    -- (d, the other half) an impact run that moved a claim directly. The
    -- transition carries the Receipt that occasioned it, which is how a run
    -- says which claim it was settling.
    SELECT 'impact_run_moved_a_claim', tr.label
      FROM impact_replays ir
      JOIN tool_runs tr ON tr.id = ir.tool_run_id
      JOIN test_replay_actions a ON a.tool_run_id = ir.tool_run_id
      JOIN hypothesis_transitions ht ON ht.receipt_id = a.receipt_id
UNION ALL
    -- (e) criterion 4: an after-state Receipt from a different run
    SELECT 'demonstration_cites_a_foreign_receipt', d.id::text
      FROM impact_demonstrations d
     WHERE NOT EXISTS (SELECT 1 FROM test_replay_actions a
                        WHERE a.tool_run_id = d.tool_run_id
                          AND a.receipt_id = d.after_state_receipt_id)
UNION ALL
    -- (f) criterion 6: the column and the latest statement disagree
    SELECT 'severity_disagrees_with_its_statement', f.label
      FROM findings f
      JOIN LATERAL (SELECT s.severity, s.basis FROM severity_statements s
                     WHERE s.finding_id = f.id
                     ORDER BY s.created_at DESC, s.id DESC LIMIT 1) st ON true
     WHERE (f.severity, f.severity_basis) IS DISTINCT FROM (st.severity, st.basis)
UNION ALL
    -- (g) criterion 6 the other way: a severity with a basis and nothing that
    --     ever stated it
    SELECT 'severity_with_no_statement', f.label
      FROM findings f
     WHERE f.severity_basis <> 'undetermined'
       AND NOT EXISTS (SELECT 1 FROM severity_statements s WHERE s.finding_id = f.id)
UNION ALL
    -- (h) a demonstrated severity whose demonstration is about another Finding
    SELECT 'statement_cites_another_findings_demonstration', s.id::text
      FROM severity_statements s
      JOIN impact_demonstrations d ON d.id = s.impact_demonstration_id
     WHERE d.finding_id <> s.finding_id
$fn$;

COMMENT ON FUNCTION check_impact_authorization() IS
    'Ticket 38. Everything about impact that is true of the corpus as a whole rather than of one row: no Test states a class nobody may grant, every impact run names a live approval for its own Test and class, no impact run touched the claim underneath, every demonstration cites a Receipt from its own run, and every severity on a Finding is the last one something stated with a basis.';

REVOKE ALL ON FUNCTION check_impact_authorization() FROM PUBLIC, rk2_state, rk2_proxy;
GRANT EXECUTE ON FUNCTION check_impact_authorization() TO rk2_runtime, rk2_human;

INSERT INTO standing_checks (name, query, owner_ticket, note) VALUES
    ('check_impact_authorization',
     'SELECT * FROM check_impact_authorization()',
     '38',
     'Impact is authorized before it is proved: no forbidden class is testable, every impact run names a live approval for its own Test, no impact run produced evidence about the claim or moved it, every demonstration cites its own after-state Receipt, and every severity on a Finding is the one something stated.');

-- ===========================================================================
-- 10. What this migration asserts about itself
-- ===========================================================================

DO $$
DECLARE v text; n integer;
BEGIN
    -- The three forbidden classes cannot become questions, because
    -- `pending_decisions_never_forbidden` refuses the risk class they map to.
    SELECT count(*) INTO n
      FROM impact_classes ic JOIN risk_classes rc ON rc.risk_class = ic.risk_class
     WHERE rc.decision = 'deny';
    IF n <> 3 THEN
        RAISE EXCEPTION 'criterion 5 wants availability, third-party and out-of-scope pivots refused; % classes are', n;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint
                    WHERE conname = 'pending_decisions_never_forbidden') THEN
        RAISE EXCEPTION 'the constraint that turns a forbidden class into an unaskable question is gone';
    END IF;

    -- The detection opener refuses an impact Test, which is what keeps
    -- criterion 3 from depending on a caller choosing the right verb.
    SELECT prosrc INTO v FROM pg_proc WHERE proname = 'open_test_replay';
    IF v NOT LIKE '%impact_class IS NOT NULL%' THEN
        RAISE EXCEPTION 'open_test_replay would run an impact Test and settle a claim with it';
    END IF;

    -- And the recorder in the middle does not start one testing, which is the
    -- other end of the same rule: 035 moved the claim on the first action, and
    -- an impact run's first action must move nothing.
    SELECT prosrc INTO v FROM pg_proc WHERE proname = 'record_test_action';
    IF v NOT LIKE '%impact_replays%' THEN
        RAISE EXCEPTION 'record_test_action would start an impact run testing the claim';
    END IF;

    -- And the impact closer writes nothing about the claim.
    SELECT prosrc INTO v FROM pg_proc WHERE proname = 'close_impact_replay';
    IF v LIKE '%hypothesis_transitions%' OR v LIKE '%hypothesis_evidence%'
       OR v LIKE '%INSERT INTO observations%' THEN
        RAISE EXCEPTION 'close_impact_replay writes evidence about the claim it was told not to touch';
    END IF;

    -- Severity has exactly one writer.
    SELECT count(*) INTO n FROM pg_proc
     WHERE pronamespace = 'public'::regnamespace
       AND prosrc ~ 'UPDATE findings SET severity'
       AND proname <> 'state_severity';
    IF n <> 0 THEN
        RAISE EXCEPTION '% functions besides state_severity write findings.severity', n;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger
                    WHERE tgname = 'findings_severity_is_stated'
                      AND tgrelid = 'findings'::regclass) THEN
        RAISE EXCEPTION 'the severity column can be moved without stating a basis';
    END IF;

    -- Every question this corpus can ask still renders from its digest.
    IF render_decision_question(
           jsonb_build_object('kind', 'impact', 'impact_class', 'write_target_state',
                              'finding', 'F1', 'test', 'TST1',
                              'identity_slot', 'shopper',
                              'effect', 'a note is rewritten by a stranger',
                              'undone_by', 'the note is put back',
                              'hosts', jsonb_build_array('b.example', 'a.example')),
           'approval_required', 'impact_classes:write_target_state')
       <> '[approval_required] prove write_target_state on F1 via TST1'
          || ' against a.example, b.example (identity shopper)'
          || ' -- impact_classes:write_target_state'
          || ' | effect: a note is rewritten by a stranger'
          || ' | undone by: the note is put back' THEN
        RAISE EXCEPTION 'the impact question does not render from its digest';
    END IF;

    -- Criterion 2's park is a condition of the question rather than a habit of
    -- the opener, and what makes it one is the trigger being deferred: an
    -- immediate one would refuse the INSERT that comes before the park.
    IF NOT EXISTS (SELECT 1 FROM pg_trigger
                    WHERE tgname = 'pending_decisions_impact_parks_a_task'
                      AND tgrelid = 'pending_decisions'::regclass
                      AND tgdeferrable AND tginitdeferred) THEN
        RAISE EXCEPTION 'an impact question can be asked about a Task nobody stopped';
    END IF;

    -- Criterion 5 is asked twice and worded once. Two copies of the sentence is
    -- how the second one comes to say something the first does not.
    SELECT count(*) INTO n FROM pg_proc
     WHERE pronamespace = 'public'::regnamespace
       AND prosrc LIKE '%and no grant admits it%';
    IF n <> 1 THEN
        RAISE EXCEPTION '% functions word the refusal of a forbidden impact class', n;
    END IF;

    SELECT string_agg(problem || ' ' || detail, '; ' ORDER BY problem, detail)
      INTO v FROM check_impact_authorization();
    IF v IS NOT NULL THEN
        RAISE EXCEPTION 'ticket 38 is not satisfied at apply time: %', v;
    END IF;
END $$;
