-- ===========================================================================
-- Production harness 104 -- let the model ask to be parked for a human
-- ===========================================================================
-- The asymmetry this closes is one sentence long. The door can already park a
-- Tool run: `park_for_human(uuid, interval)` is granted to `rk2_runtime` at
-- `0038_receipt_capabilities.sql:261` and called from `src/redkraken/proxy.py`
-- as `PARK_TOOL_RUN`. So a run that walks into a scope ambiguity gets parked by
-- the network, and a run that recognises one first has a declared question code
-- for exactly that -- `roster.py`'s `mcp__rk2__park_for_human`, five closed
-- values -- and no way to use it.
--
-- Three things had to be decided before a verb could exist.
--
-- **What the question is about.** `pending_decisions` admitted two subjects: a
-- Tool run in flight (011) and a Test specification (038). A model-side park has
-- neither. It is about the Task, which is the thing that waits, so the
-- constraint gains a third shape rather than a nullable fourth column.
--
-- **Who writes the words the operator reads.** 026 is explicit: "if the agent
-- supplied this string it would be authoring the prompt the human answers,
-- which is the whole attack the control surface exists to stop", and
-- `assert_question_is_rendered` enforces it on every row. That rule is kept
-- exactly. The model's sentence goes into the digest as a *claim*, under its own
-- key, stripped of anything that could forge structure and bounded; the prompt
-- stays a projection `render_decision_question` derives, and the arm added below
-- prints the claim attributed and in quotes rather than as the question.
--
-- **What parking costs.** Nothing. Ticket 08's rule -- "attempts NOT
-- incremented: parking is not a failed attempt" -- is why the parked shape lives
-- in one function now instead of two copies: 026's park and this one write the
-- same seven statements about a run that is one statement from over, and two
-- copies of that is one migration away from a park that releases the Lease and
-- a park that does not.

-- ---------------------------------------------------------------------------
-- 1. The third subject
-- ---------------------------------------------------------------------------
-- 038's version reads `num_nonnulls(tool_run_id, test_id) = 1 AND
-- (tool_run_id IS NOT NULL) = (agent_run_id IS NOT NULL)`, which is the two
-- shapes it knew stated as arithmetic. Three shapes are past what arithmetic
-- says clearly, so this is a CASE: a reader can see which subject each arm is
-- about, and the third arm is the only one that is new.

ALTER TABLE pending_decisions
    DROP CONSTRAINT pending_decisions_names_one_subject;

ALTER TABLE pending_decisions
    ADD CONSTRAINT pending_decisions_names_one_subject CHECK (
        CASE
            -- 011: a call in flight, asked about by the run that made it.
            WHEN tool_run_id IS NOT NULL
                THEN test_id IS NULL AND agent_run_id IS NOT NULL
            -- 038: a specification, which has not run and may run more than
            -- once, so it names the Task and no run at all.
            WHEN test_id IS NOT NULL
                THEN agent_run_id IS NULL AND task_id IS NOT NULL
            -- 104: the run's own ask. Nothing is in flight and nothing is
            -- authored; what waits is the Task, and the run that asked is
            -- named because the claim in the digest is that run's.
            ELSE agent_run_id IS NOT NULL AND task_id IS NOT NULL
        END);

COMMENT ON CONSTRAINT pending_decisions_names_one_subject ON pending_decisions IS
    'Ticket 104: the three subjects a question can have. A Tool run the door '
    'stopped, a Test an operator has not authorized, or the Task an Agent run '
    'asked to be parked on. Exactly one, and each names the rows that shape '
    'needs rather than a union of all of them.';

-- 038's deferred trigger asked its question of the impact shape alone. The
-- agent-ask shape needs it for the same reason and more sharply: a question the
-- model filed with nothing stopped behind it would be a run that asked to wait
-- and kept going.
CREATE OR REPLACE FUNCTION assert_impact_question_parks_its_task() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE v tasks%ROWTYPE;
BEGIN
    IF NEW.status <> 'pending' OR NEW.tool_run_id IS NOT NULL THEN
        RETURN NEW;
    END IF;
    SELECT * INTO v FROM tasks WHERE id = NEW.task_id;
    IF v.status <> 'parked' OR v.pending_decision_id IS DISTINCT FROM NEW.id THEN
        RAISE EXCEPTION 'decision % asks about work and task % is % on %',
            NEW.label, v.label, v.status,
            coalesce(v.pending_decision_id::text, 'nothing')
            USING ERRCODE = '23514',
                  HINT = 'a question about work that is not waiting is a request nobody stopped';
    END IF;
    RETURN NEW;
END $fn$;

COMMENT ON FUNCTION assert_impact_question_parks_its_task() IS
    'Tickets 38 and 104: a question whose subject is work rather than a call in '
    'flight is only filed with that work stopped. Deferred, because the question '
    'and the park are two statements of one transaction.';

-- ---------------------------------------------------------------------------
-- 2. The model's words, made safe to store and impossible to mistake
-- ---------------------------------------------------------------------------
-- Not sanitised prose -- a bounded, single-line quotation. What is removed is
-- what could make the rendering look like something other than a quotation:
-- control characters (a newline would let the claim start what reads as a new
-- field), and length past 500 characters (the operator reads a queue, and a
-- question that fills a screen is a question that hides the next one).
--
-- Empty is legal and means the run named a code and no words. The code is the
-- part the schema guarantees; the words are the part it quotes.

CREATE FUNCTION rk2_quoted_claim(p_text text) RETURNS text
LANGUAGE sql IMMUTABLE AS $fn$
    SELECT left(btrim(regexp_replace(coalesce(p_text, ''),
                                     '[[:cntrl:]]+', ' ', 'g')), 500);
$fn$;

COMMENT ON FUNCTION rk2_quoted_claim(text) IS
    'Ticket 104: one line a model wrote, bounded and stripped of control '
    'characters, so that storing it cannot forge structure in anything that '
    'renders it. It is quoted, never obeyed: nothing in this corpus reads a '
    'value that went through here as an instruction.';

CREATE FUNCTION rk2_agent_ask_digest(p_task uuid, p_agent_run uuid,
                                     p_code text, p_question text)
RETURNS jsonb LANGUAGE sql STABLE AS $fn$
    SELECT jsonb_build_object(
        'kind',          'agent_ask',
        'task',          (SELECT label FROM tasks WHERE id = p_task),
        'agent_run',     (SELECT label FROM agent_runs WHERE id = p_agent_run),
        'role',          (SELECT role FROM agent_runs WHERE id = p_agent_run),
        'question_code', p_code,
        -- The one field a model contributes, under a key that says whose it is.
        'claim',         rk2_quoted_claim(p_question));
$fn$;

COMMENT ON FUNCTION rk2_agent_ask_digest(uuid, uuid, text, text) IS
    'Ticket 104: the request half of a question an Agent run asked about its own '
    'Task. Every field but `claim` is a row this runtime wrote; `claim` is the '
    'run''s own sentence, bounded and quoted. Two runs asking the same thing in '
    'the same words digest alike, which is what makes one open question enough.';

-- 026's renderer, third arm. The shape of the sentence is the point: the risk
-- class, what is waiting, the code the runtime classified it under, and only
-- then the run's own words, introduced by a phrase that says they are the run's.
-- An operator reading this can tell what the harness established from what the
-- model asserted without knowing anything about this file.
CREATE OR REPLACE FUNCTION render_decision_question(p_digest jsonb, p_risk text, p_rule text)
RETURNS text
LANGUAGE sql IMMUTABLE AS $fn$
    SELECT CASE
           WHEN p_digest ->> 'kind' = 'agent_ask' THEN
                format('[%s] %s asked to stop on %s (%s) -- %s | the run''s own words: "%s"',
                       p_risk,
                       coalesce(p_digest ->> 'agent_run', ''),
                       coalesce(p_digest ->> 'task', ''),
                       coalesce(p_digest ->> 'question_code', ''),
                       p_rule,
                       coalesce(p_digest ->> 'claim', ''))
           WHEN p_digest ->> 'kind' = 'impact' THEN
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

COMMENT ON FUNCTION render_decision_question(jsonb, text, text) IS
    'The sentence an operator answers, projected from the digest and never sent '
    'by a caller. Three arms: a call in flight (011), a Test awaiting a grant '
    '(038), and an Agent run asking to stop (104), whose own sentence is quoted '
    'inside the projection and is not the projection.';

-- ---------------------------------------------------------------------------
-- 3. The parked shape, in one place
-- ---------------------------------------------------------------------------
-- Lifted verbatim out of `park_authorized_tool_run`, which keeps only what is
-- about the receipt it is parking. Everything here is about the *run*: it is one
-- statement from over, and what it was holding goes back.
--
-- `p_except_tool_run` is the receipt the caller has already closed itself. A
-- caller with none -- the model-side park opens no Tool run -- passes NULL and
-- every open receipt of the run is abandoned, which is the same rule with
-- nothing exempted from it.

CREATE FUNCTION rk2_park_the_work(p_task uuid, p_agent_run_id uuid,
                                  p_decision uuid, p_decision_label text,
                                  p_except_tool_run uuid DEFAULT NULL)
RETURNS void LANGUAGE plpgsql AS $fn$
BEGIN
    PERFORM set_actor('runtime');

    -- Every receipt the run had open. A capability that outlived its holder is
    -- the fault this prevents rather than one to discover later at the door.
    UPDATE tool_runs
       SET status = 'abandoned', finished_at = now(), egress_token_sha256 = NULL,
           hook_error = coalesce(hook_error,
               'the run was parked for human decision ' || p_decision_label
               || ' while this receipt was open; whether the tool ran is unknown')
     WHERE agent_run_id = p_agent_run_id AND status = 'running'
       AND id IS DISTINCT FROM p_except_tool_run;

    -- Both halves of the Lease, on one reading of the clock.
    PERFORM release_leases(p_agent_run_id);

    -- The run ends, the lane slot frees.
    UPDATE agent_runs SET finished_at = now(), stop_reason = 'parked', result = NULL
     WHERE id = p_agent_run_id AND finished_at IS NULL;

    UPDATE agent_sessions s SET unbound_at = now()
     WHERE s.agent_run_id = p_agent_run_id AND s.unbound_at IS NULL;

    -- `testing` means a live run is testing it, and after this there is no live
    -- run. Same transition `sweep_expired_leases()` makes, for the same reason.
    INSERT INTO hypothesis_transitions
        (program_id, hypothesis_id, from_status, to_status, actor_kind, rationale)
    SELECT t.program_id, h.id, 'testing', 'testable', 'runtime',
           'parked for human decision ' || p_decision_label
      FROM hypotheses h
      JOIN tasks t ON t.hypothesis_id = h.id
     WHERE t.id = p_task AND h.status = 'testing';

    -- attempts NOT incremented: parking is not a failed attempt (ticket 08).
    -- `lease_expires_at` is not cleared here either, and that is the point of
    -- `release_leases` above: one verb ends the hold, and this records the
    -- state the Task is left in.
    UPDATE tasks SET status = 'parked', pending_decision_id = p_decision,
                     claimed_at = NULL, priority = NULL
     WHERE id = p_task;
END $fn$;

COMMENT ON FUNCTION rk2_park_the_work(uuid, uuid, uuid, text, uuid) IS
    'Ticket 104: everything a parked run gives back, in one statement list -- '
    'every receipt it had open, both halves of the Lease, the Agent run, its '
    'session binding, the hypothesis it was testing and the Task. No attempt is '
    'charged. Shared by 026''s park and 104''s so the two cannot come to mean '
    'different things.';

-- 026's park, now only the part that is about the receipt it is parking.
CREATE OR REPLACE FUNCTION park_authorized_tool_run(
    p_tool_run_id uuid,
    p_ttl interval DEFAULT interval '4 hours'
) RETURNS text LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, public
AS $fn$
DECLARE
    tr tool_runs%ROWTYPE;
    g  jsonb;
    d  pending_decisions%ROWTYPE;
BEGIN
    PERFORM set_actor('runtime');
    SELECT * INTO tr FROM tool_runs WHERE id = p_tool_run_id;
    g := gate_tool_call(p_tool_run_id);

    IF g ->> 'decision' <> 'ask' THEN
        RAISE EXCEPTION 'tool_run % resolves to %/%, not to a human decision',
            tr.label, g ->> 'risk_class', g ->> 'decision'
            USING ERRCODE = '23514',
                  HINT = 'forbidden refuses and autonomous/constrained run; neither parks';
    END IF;

    INSERT INTO pending_decisions
        (program_id, task_id, agent_run_id, tool_run_id, tool, risk_class, risk_rule,
         question_code, request_digest, equivalence_key, question, deadline_at)
    VALUES (tr.program_id, tr.task_id, tr.agent_run_id, tr.id, tr.tool,
            g ->> 'risk_class', g ->> 'rule', g ->> 'question_code', g -> 'digest',
            equivalence_key(g -> 'digest'),
            render_decision_question(g -> 'digest', g ->> 'risk_class', g ->> 'rule'),
            now() + p_ttl)
    RETURNING * INTO d;

    -- the receipt: parked, terminal, and it never resumes -- the session that
    -- opened it is about to end
    UPDATE tool_runs SET status = 'parked', decision = 'deny',
                         decision_reason = 'parked for human decision ' || d.label,
                         pending_decision_id = d.id, closed_by = 'PreToolUse',
                         finished_at = now(), egress_token_sha256 = NULL,
                         risk_class = g ->> 'risk_class'
     WHERE id = tr.id;

    PERFORM rk2_park_the_work(tr.task_id, tr.agent_run_id, d.id, d.label, tr.id);
    RETURN d.label;
END $fn$;

-- ---------------------------------------------------------------------------
-- 4. Filing the run's own question
-- ---------------------------------------------------------------------------
-- Definer for `rk2_ask_about_impact`'s reason, stated there: 029's rule is that
-- the runtime writes a question and never reads one, so `rk2_runtime` holds
-- INSERT on `pending_decisions` and no SELECT at all -- and `RETURNING *` is a
-- read. It hands back the three fields the caller needs to park and answer with,
-- and nothing else.
--
-- A question already waiting is answered rather than asked again, which here
-- means something slightly stronger than it does for impact: two runs that hit
-- the same ambiguity on the same Task in the same words file one question, and
-- the second is told which one.

CREATE FUNCTION rk2_ask_for_the_run(p_task uuid, p_agent_run_id uuid,
                                    p_code text, p_digest jsonb, p_ttl interval)
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
        (program_id, task_id, agent_run_id, tool, risk_class, risk_rule,
         question_code, request_digest, equivalence_key, question, deadline_at)
    VALUES (p, p_task, p_agent_run_id, 'mcp__rk2__park_for_human',
            'approval_required', 'agent_ask:' || p_code,
            p_code, p_digest, equivalence_key(p_digest),
            render_decision_question(p_digest, 'approval_required',
                                     'agent_ask:' || p_code),
            now() + p_ttl)
    RETURNING id, label, question INTO r_id, r_label, r_question;
    RETURN NEXT;
END $fn$;

COMMENT ON FUNCTION rk2_ask_for_the_run(uuid, uuid, text, jsonb, interval) IS
    'Ticket 104: file the question an Agent run asked about its own Task and '
    'hand back its id, label and words, or hand back the open question that '
    'already asks it. Definer because the runtime may write a question and may '
    'not read one.';

-- ---------------------------------------------------------------------------
-- 5. The verb
-- ---------------------------------------------------------------------------
-- Refusals are returned, not raised. The whole point of the tool is that a run
-- which has recognised a problem gets to say so; ending its turn with an
-- exception because it named the wrong Task would spend the recognition on a
-- traceback. What is raised is the database being unreachable, which is not a
-- verdict on the ask.
--
-- The Task is resolved to the run rather than taken on the model's word.
-- `roster.py` declares `task_label`, so a model names a Task -- and a run that
-- named a Task other than its own would park work it is not doing.

CREATE FUNCTION park_task_for_human(p_agent_run_id uuid, p_task uuid,
                                    p_question_code text,
                                    p_question text DEFAULT NULL,
                                    p_ttl interval DEFAULT interval '4 hours')
RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p        uuid := rk2_program_required();
    v_run    agent_runs%ROWTYPE;
    v_task   tasks%ROWTYPE;
    v_digest jsonb;
    v_dec    record;
BEGIN
    SELECT * INTO v_run FROM agent_runs
     WHERE id = p_agent_run_id AND program_id = p FOR UPDATE;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('parked', NULL,
          'refusal', 'no Agent run of this Program is recorded under that id');
    END IF;
    IF v_run.finished_at IS NOT NULL THEN
        RETURN jsonb_build_object('parked', NULL,
          'refusal', 'agent run ' || v_run.label || ' is already '
                     || coalesce(v_run.stop_reason, 'finished')
                     || ', so there is nothing left to stop');
    END IF;
    IF v_run.task_id IS NULL THEN
        RETURN jsonb_build_object('parked', NULL,
          'refusal', 'agent run ' || v_run.label || ' holds no Task, and what '
                     || 'parks is the work rather than the run');
    END IF;

    SELECT * INTO v_task FROM tasks
     WHERE id = v_run.task_id AND program_id = p FOR UPDATE;

    -- Criterion 4. The label came from a model; the Task came from the run.
    IF p_task IS DISTINCT FROM v_task.id THEN
        RETURN jsonb_build_object('parked', NULL,
          'refusal', 'this run holds ' || v_task.label
                     || ' and a run parks the Task it is running');
    END IF;
    IF v_task.status NOT IN ('claimed', 'running') THEN
        RETURN jsonb_build_object('parked', NULL,
          'refusal', 'task ' || v_task.label || ' is ' || v_task.status
                     || ', which is not work in flight');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM decision_question_codes
                    WHERE question_code = p_question_code) THEN
        RETURN jsonb_build_object('parked', NULL,
          'refusal', coalesce(p_question_code, 'nothing')
                     || ' is not a question code this harness files under',
          'question_codes', (SELECT jsonb_agg(question_code ORDER BY question_code)
                               FROM decision_question_codes));
    END IF;

    v_digest := rk2_agent_ask_digest(v_task.id, v_run.id, p_question_code, p_question);

    PERFORM set_actor('runtime');
    SELECT * INTO v_dec
      FROM rk2_ask_for_the_run(v_task.id, v_run.id, p_question_code, v_digest, p_ttl);

    PERFORM rk2_park_the_work(v_task.id, v_run.id, v_dec.r_id, v_dec.r_label);

    RETURN jsonb_build_object(
        'parked', v_dec.r_label, 'refusal', NULL,
        'question', v_dec.r_question,
        'task', v_task.label, 'agent_run', v_run.label,
        'question_code', p_question_code,
        -- Said in the answer because it is the property the tool is for: a run
        -- that asks to stop has not failed, and the Task it stops is as ready
        -- as it was.
        'attempt_charged', false);
END $fn$;

COMMENT ON FUNCTION park_task_for_human(uuid, uuid, text, text, interval) IS
    'Ticket 104: an Agent run asks for its own Task to wait for a human. The '
    'question is filed under one of the codes the registry holds, with the '
    'run''s own sentence quoted inside a projection it did not write; the Task '
    'parks, the Leases go back, no attempt is charged, and only an operator '
    'releases it. Refuses a Task that is not this run''s.';

-- ---------------------------------------------------------------------------
-- 6. What an operator's approval is revalidated against
-- ---------------------------------------------------------------------------
-- Third arm, and it is short because nothing under this question can move. The
-- digest is the run's own claim about a Task, and the Task-still-parked check
-- above is the whole of what could have changed. What the arm exists for is to
-- stop the call shape's `current_request_digest(NULL)` from answering
-- `request_reclassified` about a question that has no request in it.

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
    IF d.task_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM tasks t
                        WHERE t.id = d.task_id AND t.status = 'parked'
                          AND t.pending_decision_id = d.id) THEN
        RETURN 'task_no_longer_parked';
    END IF;

    IF d.test_id IS NOT NULL THEN
        SELECT t.finding_id INTO v_find FROM tasks t WHERE t.id = d.task_id;
        IF v_find IS NULL THEN RETURN 'task_no_longer_parked'; END IF;
        IF NOT EXISTS (SELECT 1 FROM findings f
                        WHERE f.id = v_find AND f.status = 'validated') THEN
            RETURN 'request_reclassified';
        END IF;
        now_d := rk2_impact_digest(d.program_id, v_find, d.test_id,
                                   d.request_digest ->> 'identity_slot');
        IF equivalence_key(now_d) IS DISTINCT FROM d.equivalence_key THEN
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

    -- Ticket 104. No request, no specification: the subject is the Task, and
    -- the clause above has just established it is still waiting.
    IF d.tool_run_id IS NULL THEN
        RETURN NULL;
    END IF;

    now_d := current_request_digest(d.tool_run_id);
    IF equivalence_key(now_d) IS DISTINCT FROM d.equivalence_key THEN
        RETURN 'request_reclassified';
    END IF;

    v := assess_call_risk(d.tool, now_d);
    IF v ->> 'risk_class' = 'forbidden' THEN RETURN 'now_forbidden'; END IF;
    IF v ->> 'rule' IS DISTINCT FROM d.risk_rule THEN RETURN 'policy_changed'; END IF;
    RETURN NULL;
END $fn$;

-- ---------------------------------------------------------------------------
-- 7. Grants
-- ---------------------------------------------------------------------------

REVOKE ALL ON FUNCTION rk2_quoted_claim(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION rk2_agent_ask_digest(uuid, uuid, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION rk2_park_the_work(uuid, uuid, uuid, text, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION rk2_ask_for_the_run(uuid, uuid, text, jsonb, interval) FROM PUBLIC;
REVOKE ALL ON FUNCTION park_task_for_human(uuid, uuid, text, text, interval) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION rk2_quoted_claim(text) TO rk2_runtime, rk2_human;
GRANT EXECUTE ON FUNCTION rk2_agent_ask_digest(uuid, uuid, text, text) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION rk2_park_the_work(uuid, uuid, uuid, text, uuid) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION rk2_ask_for_the_run(uuid, uuid, text, jsonb, interval) TO rk2_runtime;
GRANT EXECUTE ON FUNCTION park_task_for_human(uuid, uuid, text, text, interval) TO rk2_runtime;

-- 066's registry, which is what makes each grant above a declaration rather
-- than a fact somebody would have to measure. `check_runtime_privileges`
-- refuses a verb the runtime can execute that no row here names.
INSERT INTO runtime_verb_surface (verb, added_by, note) VALUES
    ('rk2_quoted_claim(text)',
     '104',
     'bounds and strips one line a model wrote so that storing it cannot forge structure in anything that renders it'),
    ('rk2_agent_ask_digest(uuid, uuid, text, text)',
     '104',
     'the request half of a question an Agent run asked about its own Task: rows this runtime wrote, plus the run''s own sentence under a key that says whose it is'),
    ('rk2_park_the_work(uuid, uuid, uuid, text, uuid)',
     '104',
     'the parked shape shared by 026''s park and 104''s -- open receipts, both halves of the Lease, the Agent run, its session, the hypothesis and the Task, with no attempt charged'),
    ('rk2_ask_for_the_run(uuid, uuid, text, jsonb, interval)',
     '104',
     'files the run''s question and hands back its id, label and words, or the open question that already asks it; definer because the runtime writes a question and never reads one'),
    ('park_task_for_human(uuid, uuid, text, text, interval)',
     '104',
     'the model-side park: the verb behind mcp__rk2__park_for_human, which refuses a Task that is not the asking run''s'),
    ('check_agent_asks()',
     '104',
     'the standing check that every agent ask named its work, ended its run, released its Leases and reads as its own rendering');

SELECT apply_state_rls();
SELECT apply_state_grants();
SELECT enforce_always_triggers();

-- ---------------------------------------------------------------------------
-- 8. The standing check
-- ---------------------------------------------------------------------------
-- What has to stay true of the rows rather than of one call. A park that
-- released nothing is the defect this ticket is most able to introduce: the
-- statements are in one function now, and the check is what would notice if a
-- later migration took one of them back out.

CREATE FUNCTION check_agent_asks() RETURNS TABLE (problem text, detail text)
LANGUAGE sql STABLE AS $fn$
    -- (a) every agent ask names a Task and the run that asked
    SELECT 'agent_ask_names_no_work', d.label
      FROM pending_decisions d
     WHERE d.request_digest ->> 'kind' = 'agent_ask'
       AND (d.task_id IS NULL OR d.agent_run_id IS NULL)
    UNION ALL
    -- (b) the run that asked is over, because asking ends it
    SELECT 'agent_ask_left_its_run_open', d.label || ' / ' || r.label
      FROM pending_decisions d
      JOIN agent_runs r ON r.id = d.agent_run_id
     WHERE d.request_digest ->> 'kind' = 'agent_ask'
       AND r.finished_at IS NULL
    UNION ALL
    -- (c) and it is holding no Lease. Ticket 24's verb released both halves.
    SELECT 'agent_ask_left_a_lease_held', d.label || ' / ' || r.label
      FROM pending_decisions d
      JOIN agent_runs r ON r.id = d.agent_run_id
      JOIN identity_leases l ON l.holder_agent_run_id = r.id
     WHERE d.request_digest ->> 'kind' = 'agent_ask'
       AND l.released_at IS NULL
    UNION ALL
    -- (d) the words in the question are the words in the digest. The rendering
    -- trigger says so for every row; this says it for the arm that quotes a
    -- model, which is the one where being wrong would matter most.
    SELECT 'agent_ask_question_is_not_its_own_rendering', d.label
      FROM pending_decisions d
     WHERE d.request_digest ->> 'kind' = 'agent_ask'
       AND d.question IS DISTINCT FROM
           render_decision_question(d.request_digest, d.risk_class, d.risk_rule);
$fn$;

COMMENT ON FUNCTION check_agent_asks() IS
    'Ticket 104: every question an Agent run asked about its own Task named the '
    'work and the run, ended that run, released its Leases, and reads as the '
    'projection of its own digest.';

REVOKE ALL ON FUNCTION check_agent_asks() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION check_agent_asks() TO rk2_runtime, rk2_human;

INSERT INTO standing_checks (name, query, owner_ticket, note) VALUES
    ('agent_asks',
     'SELECT * FROM check_agent_asks()',
     '104',
     'A model asks to be parked and the work waits: every agent ask names its Task and its run, ends that run, holds no Lease afterwards, and reads as the rendering of its own digest.');
