-- ===========================================================================
-- Ticket 59 -- a person reports a Finding, and lifts a review gate to do it
-- ===========================================================================
-- 019 built the whole apparatus of reporting and stopped one step short of the
-- step a person takes. `report_renderings` holds the exact bytes an approval
-- may name, `enforce_report_approval` refuses a transition that names none,
-- `transition_rules` reserves `validated -> reported` for `actor_kind='human'`
-- -- and nothing in the corpus inserts that row. `findings.reported_at` has
-- been read by 023's ranking since the day it was added and has never been
-- written. An operator's only route to the last step of the whole harness was
-- `psql`, which is what ticket 59 exists to end.
--
-- Two verbs, and the ticket's own word for why they are two is "distinct":
--
--   `report_finding`      moves one Finding from `validated` to `reported`,
--                         naming the rendering the person read and the digest
--                         of the bytes in it. Every gate 019 built stays where
--                         it is; this adds none and lifts none. The Event is
--                         006's `finding.transitioned`, which the row emits by
--                         trigger.
--
--   `clear_review_gate`   lifts one review gate on one Finding, and does
--                         nothing else. It reports nothing, approves nothing
--                         and touches no status. The Event is its own.
--
-- One verb doing both would be the operator asked one question -- "send this?"
-- -- where the design needs two answers, because the second question is not
-- about this Finding at all. It is "the program said do not send this class,
-- and I say this instance is not that", which is a judgement about somebody
-- else's queue that outlives the Finding it was made on.
--
-- WHICH GATES CAN BE LIFTED, AND WHY ONLY THOSE. `report_blockers` raises eight
-- hard codes and one soft one. Six of the eight are facts about the record: it
-- is not validated, it has no witnessed effect, it has no chain, its stored
-- vector is not what its effects compute to, nobody has stated its severity on
-- a basis, an effect cites an observation the Finding does not. A person
-- "clearing" one of those would be a person overruling arithmetic or waving
-- through a sentence nobody has taken responsibility for, and the whole harness
-- is built so that nobody can. Two are judgements:
--
--   known_issue   the program published a do-not-send list and this class is
--                 on it. Whether this instance is the thing they meant is a
--                 reading of their words.
--   duplicate     another Finding of this Program carries the same signature.
--                 The signature is deliberately coarser than a Hypothesis
--                 dedup key (019 says so), so two Findings can collide on it
--                 and still be two reports.
--
-- `review_gates` holds exactly those two, and section 5 fails if a later
-- migration adds a factual code to it.
--
-- WHAT A CLEARANCE IS NOT. It is not a standing permission. `clear_review_gate`
-- refuses a gate that is not raised on that Finding right now, so a clearance
-- is always an answer to a question the database was asking, and the sentence
-- the gate was raising is copied onto the row. An operator reading the audit a
-- month later sees what the person was told, not only what they decided.
--
-- AND WHO MAY READ THE REASON. Ticket 29 found that an operator's free text is
-- reachable three ways -- the column, a view over it, and the event payload --
-- and closed all three on `pending_decisions.answer`, because `events` is read
-- by the runtime and quoted into what it compiles. The reason on a clearance is
-- the same kind of sentence: an argument for sending a report that a program
-- said it did not want. Section 6 closes the same three doors, and section 5
-- asks about all three as rows.
-- ---------------------------------------------------------------------------


-- ---------------------------------------------------------------------------
-- 1. The two gates a person may lift
-- ---------------------------------------------------------------------------

CREATE TABLE review_gates (
    code        text PRIMARY KEY,
    description text NOT NULL
);

COMMENT ON TABLE review_gates IS
    'Ticket 59: the `report_blockers` codes that are a judgement rather than a '
    'fact, and are therefore the only ones an operator may lift. A code here '
    'that names something the database computed would make review a way to '
    'overrule arithmetic; check_finding_reporting() refuses that.';

INSERT INTO review_gates (code, description) VALUES
    ('known_issue',
     'the program published a do-not-send list and this Finding''s class is on '
     'it; whether this instance is the thing they meant is a reading of their words'),
    ('duplicate',
     'another Finding of this Program carries the same report signature, which '
     'is coarser than a Hypothesis dedup key and can collide on two real reports');


-- ---------------------------------------------------------------------------
-- 2. One person, one gate, one Finding, once
-- ---------------------------------------------------------------------------

CREATE TABLE finding_gate_clearances (
    id          uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id  uuid NOT NULL,
    finding_id  uuid NOT NULL,
    code        text NOT NULL REFERENCES review_gates(code),
    -- What the gate was saying at the moment it was lifted. Stored rather than
    -- recomputed: `report_blockers` answers about the database as it is now,
    -- and the question an audit asks is what the person was told then. A
    -- `duplicate` detail naming a Finding that has since been purged is exactly
    -- the case where recomputing would quietly rewrite the record.
    detail      text NOT NULL,
    reason      text NOT NULL,
    actor_kind  text NOT NULL DEFAULT 'human' CHECK (actor_kind = 'human'),
    cleared_by  text NOT NULL,
    cleared_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, program_id),
    UNIQUE (finding_id, code),
    FOREIGN KEY (finding_id, program_id) REFERENCES findings (id, program_id) ON DELETE CASCADE,
    CHECK (btrim(reason) <> ''),
    CHECK (btrim(detail) <> '')
);

COMMENT ON TABLE finding_gate_clearances IS
    'Ticket 59 criterion 5: one operator lifted one review gate on one Finding, '
    'what the gate was saying at the time, and why they lifted it anyway. '
    'Unique per (Finding, gate) because a second clearance of a gate already '
    'lifted is not a decision, and immutable because a decision that can be '
    'edited is not a record of one.';

CREATE TRIGGER finding_gate_clearances_immutable
    BEFORE UPDATE OR DELETE ON finding_gate_clearances
    FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_purging();
ALTER TABLE finding_gate_clearances ENABLE ALWAYS TRIGGER finding_gate_clearances_immutable;


-- ---------------------------------------------------------------------------
-- 3. The two arms of `report_blockers` that a clearance answers
-- ---------------------------------------------------------------------------
-- 038's body, with one NOT EXISTS on each of the two judgement arms and not a
-- character changed anywhere else. Replaced rather than wrapped: a second
-- function that subtracted rows from this one would be a second opinion about
-- what blocks a report, and `record_rendering`, `rk2_chain_unsoundness` and
-- `enforce_report_approval` each ask this one by name.

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
       AND NOT EXISTS (SELECT 1 FROM finding_gate_clearances c
                        WHERE c.finding_id = f.id AND c.code = 'known_issue')
    UNION ALL
    -- already told them, or about to tell them twice
    SELECT 'hard', 'duplicate', 'same signature as ' || o.label || ' (' || o.status || ')'
      FROM findings f JOIN findings o
        ON o.program_id = f.program_id AND o.id <> f.id
       AND finding_signature(o.id) = finding_signature(f.id)
       AND o.status IN ('validated','reported')
     WHERE f.id = p_finding AND f.duplicate_of_finding_id IS NULL
       AND NOT EXISTS (SELECT 1 FROM finding_gate_clearances c
                        WHERE c.finding_id = f.id AND c.code = 'duplicate')
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

COMMENT ON FUNCTION report_blockers(uuid) IS
    'Ticket 19''s emission gate as ticket 38 left it, with ticket 59''s two '
    'lifts. The factual codes cannot be lifted by anybody; the two in '
    '`review_gates` are silenced for one Finding by a '
    '`finding_gate_clearances` row, which only clear_review_gate() can write '
    'and only an operator can call.';


-- ---------------------------------------------------------------------------
-- 4. The two operator verbs
-- ---------------------------------------------------------------------------
-- SECURITY DEFINER for the reason 026 and 032 used it: `rk2_human` holds no
-- table write privilege anywhere, so an operator console bug can call a verb
-- and cannot hand-write a row. The definer rights do not launder the claim,
-- because the actor-kind trigger reads `session_user`.

-- Which review gate, in the words the operator will read it in. One call
-- because `clear_review_gate` has two questions and this is one answer to both:
-- a NULL is "not raised, so there is nothing to lift", and anything else is the
-- sentence that goes on the record beside the operator's reason. Asking twice
-- would be asking `report_blockers` twice about a Finding another session may
-- have moved in between, and lifting a gate against the sentence the first
-- answer gave.
CREATE FUNCTION rk2_raised_gate(p_finding uuid, p_code text) RETURNS text
LANGUAGE sql STABLE AS $fn$
    SELECT b.detail FROM report_blockers(p_finding) b
     WHERE b.severity = 'hard' AND b.code = p_code
     LIMIT 1
$fn$;

COMMENT ON FUNCTION rk2_raised_gate(uuid, text) IS
    'Ticket 59: what one review gate is saying about one Finding right now, or '
    'NULL if it is not raised.';

-- Nobody calls this but `clear_review_gate`, which is SECURITY DEFINER and
-- reaches it as the owner. Said anyway, because 029's default privileges put
-- every role on a new function's ACL as it is created and the two verbs below
-- take the same two lines: a helper whose only caller is a definer function is
-- one nobody else should be able to name, whatever it happens to answer today.
REVOKE ALL ON FUNCTION rk2_raised_gate(uuid, text) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION rk2_raised_gate(uuid, text) FROM rk2_runtime;

CREATE FUNCTION clear_review_gate(p_label text, p_code text, p_reason text)
RETURNS jsonb SECURITY DEFINER LANGUAGE plpgsql AS $fn$
DECLARE
    p        uuid := rk2_program_required();
    v_find   findings%ROWTYPE;
    v_detail text;
    v_id     uuid;
BEGIN
    PERFORM set_actor('human', session_user);

    IF nullif(btrim(p_reason), '') IS NULL THEN
        RAISE EXCEPTION 'a clearance is the operator''s reason for overruling a gate, and there is none'
            USING ERRCODE = 'check_violation';
    END IF;

    -- Named before the Finding is looked up, because a code that is not a
    -- review gate is a mistake about what may be lifted at all, and answering
    -- it with "no such Finding" would send the operator to the wrong question.
    IF NOT EXISTS (SELECT 1 FROM review_gates g WHERE g.code = p_code) THEN
        RAISE EXCEPTION '% is not a review gate; an operator may lift %', p_code,
            (SELECT string_agg(g.code, ' or ' ORDER BY g.code) FROM review_gates g)
            USING ERRCODE = 'check_violation',
                  HINT = 'every other blocker is something the database computed, and is cleared by fixing what it computed from';
    END IF;

    SELECT * INTO v_find FROM findings
     WHERE program_id = p AND label = p_label FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'no Finding of this Program is labelled %', p_label
            USING ERRCODE = 'no_data_found';
    END IF;

    IF EXISTS (SELECT 1 FROM finding_gate_clearances c
                WHERE c.finding_id = v_find.id AND c.code = p_code) THEN
        RAISE EXCEPTION 'the % gate on % was already lifted', p_code, p_label
            USING ERRCODE = 'unique_violation';
    END IF;

    -- The refusal that makes a clearance an answer rather than a standing
    -- permission. A gate lifted before it was raised would be an operator
    -- deciding in advance about a Finding that does not yet collide with
    -- anything, and the decision would be invisible on the day it mattered.
    v_detail := rk2_raised_gate(v_find.id, p_code);
    IF v_detail IS NULL THEN
        RAISE EXCEPTION 'the % gate is not raised on %; there is nothing to lift', p_code, p_label
            USING ERRCODE = 'check_violation',
                  HINT = 'a gate is lifted when it is raised, so that what was overruled is on the record';
    END IF;

    INSERT INTO finding_gate_clearances
        (program_id, finding_id, code, detail, reason, cleared_by)
    VALUES (p, v_find.id, p_code, v_detail, btrim(p_reason), session_user)
    RETURNING id INTO v_id;

    RETURN jsonb_build_object(
        'clearance', v_id, 'finding', v_find.label, 'code', p_code,
        'was_saying', v_detail, 'cleared_by', session_user,
        'still_blocked_by', (SELECT coalesce(jsonb_agg(b.code ORDER BY b.code), '[]'::jsonb)
                               FROM report_blockers(v_find.id) b WHERE b.severity = 'hard'));
END $fn$;

COMMENT ON FUNCTION clear_review_gate(text, text, text) IS
    'Ticket 59 criterion 5: one operator lifts one raised review gate on one '
    'Finding and nothing else happens. It approves nothing, reports nothing and '
    'moves no status -- the answer names what is still blocking, so that lifting '
    'a gate never reads as permission to send.';

CREATE FUNCTION report_finding(
    p_label text, p_rendering uuid, p_content_sha256 text, p_reason text
) RETURNS jsonb SECURITY DEFINER LANGUAGE plpgsql AS $fn$
DECLARE
    p       uuid := rk2_program_required();
    v_find  findings%ROWTYPE;
    v_rend  report_renderings%ROWTYPE;
BEGIN
    PERFORM set_actor('human', session_user);

    IF nullif(btrim(p_reason), '') IS NULL THEN
        RAISE EXCEPTION 'reporting a Finding is an act somebody takes responsibility for, and there is no reason on it'
            USING ERRCODE = 'check_violation';
    END IF;

    SELECT * INTO v_find FROM findings
     WHERE program_id = p AND label = p_label FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'no Finding of this Program is labelled %', p_label
            USING ERRCODE = 'no_data_found';
    END IF;

    -- Said here as well as in the trigger, and deliberately. 019's
    -- `enforce_finding_transition` would refuse this as a stale transition,
    -- which is the right sentence for a caller that raced and the wrong one for
    -- an operator who reported the same Finding twice this morning.
    IF v_find.status = 'reported' THEN
        RAISE EXCEPTION '% was already reported', p_label
            USING ERRCODE = 'check_violation';
    ELSIF v_find.status <> 'validated' THEN
        RAISE EXCEPTION '% is %, and only a validated Finding can be reported',
            p_label, v_find.status
            USING ERRCODE = 'check_violation';
    END IF;

    SELECT * INTO v_rend FROM report_renderings
     WHERE id = p_rendering AND program_id = p;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'no rendering of this Program is recorded under %', p_rendering
            USING ERRCODE = 'no_data_found',
                  HINT = 'render it with `rk report finding --record`, which prints the id an approval may name';
    END IF;

    -- Criterion 3, on the one verb with no step after it. Every other check
    -- here asks whether the database is in a state that permits the report;
    -- this asks whether the person read it. An id can be pasted out of a script
    -- that filed a rendering nobody opened, and the whole of what `reported`
    -- means is that somebody read those bytes and stands behind them -- so the
    -- approval carries the digest of what they read, and the two have to be the
    -- same document. It is 42's own `content_sha256`, printed beside the id it
    -- is filed under, so confirming is a copy rather than an arithmetic.
    IF v_rend.content_sha256 <> lower(btrim(coalesce(p_content_sha256, ''))) THEN
        RAISE EXCEPTION 'the rendering under % is %, and this approval names %',
            p_rendering, v_rend.content_sha256,
            coalesce(nullif(lower(btrim(coalesce(p_content_sha256, ''))), ''), '<nothing>')
            USING ERRCODE = 'check_violation',
                  HINT = 'approve the bytes that were read: `rk report finding --record` prints the digest beside the rendering id';
    END IF;

    -- Every check that decides whether these bytes may be sent is 019's and is
    -- left to fire from the trigger: the rendering is of this Finding, its
    -- source digest is still what the Finding computes to, and no hard blocker
    -- stands. Restating any of them here would be a second gate to keep in step
    -- with the first.
    INSERT INTO finding_transitions
        (program_id, finding_id, from_status, to_status, actor_kind,
         rationale, approved_rendering_id)
    VALUES (p, v_find.id, 'validated', 'reported', 'human',
            btrim(p_reason), p_rendering);

    -- 023 has ranked on this column since it was added and nothing has ever
    -- written it. It is a fact about the report rather than about the Finding's
    -- state machine, which is why the transition row does not carry it and why
    -- `status_changed_at` is not it.
    UPDATE findings SET reported_at = now() WHERE id = v_find.id
    RETURNING * INTO v_find;

    RETURN jsonb_build_object(
        'finding', v_find.label, 'status', v_find.status,
        'reported_at', v_find.reported_at, 'reported_by', session_user,
        'rendering', v_rend.id, 'content_sha256', v_rend.content_sha256,
        'template', v_rend.template_id,
        'gates_lifted', (SELECT coalesce(jsonb_agg(c.code ORDER BY c.code), '[]'::jsonb)
                           FROM finding_gate_clearances c WHERE c.finding_id = v_find.id));
END $fn$;

COMMENT ON FUNCTION report_finding(text, uuid, text, text) IS
    'Ticket 59 criterion 5: one operator moves one validated Finding to '
    'reported, naming the exact rendering they read and the digest of the bytes '
    'they read in it. Every gate is 019''s and fires from the trigger; what this '
    'adds is the row nothing in the corpus was inserting, the `reported_at` 023 '
    'has been ranking on, and the operator''s own sentence about why.';


-- ---------------------------------------------------------------------------
-- 5. What reporting must never have become
-- ---------------------------------------------------------------------------

CREATE FUNCTION check_finding_reporting() RETURNS TABLE(problem text, detail text)
LANGUAGE sql STABLE AS $fn$
    -- 1. The set of liftable gates stays the set of judgements. A factual code
    -- in `review_gates` is how review would become a way to report a Finding
    -- that is not validated, has no witnessed effect, or carries a severity
    -- nobody stated on any basis.
    --
    -- Asked of `report_blockers` rather than against a list of the seven
    -- factual codes, for the reason `clear_review_gate` takes no `choices`: a
    -- list here would be a second spelling of a closed set, and a code invented
    -- by a later migration would be in neither list and pass. What makes a gate
    -- liftable is that an arm of `report_blockers` consults a clearance for it,
    -- and that is a fact about the function body -- so this reads the body. A
    -- rewrite that spells the lookup differently fails this until somebody says
    -- so here, which is the failure worth having.
    SELECT 'a review gate the blocker function does not consult', g.code
      FROM review_gates g
     WHERE NOT EXISTS (
           SELECT 1 FROM pg_proc p
            WHERE p.proname = 'report_blockers'
              AND p.pronamespace = 'public'::regnamespace
              AND p.prosrc LIKE '%c.code = ' || quote_literal(g.code) || '%')
    UNION ALL
    -- 2. Every clearance is a person's. The actor-kind trigger says so on the
    -- way in; this says so about the rows that are there, which is the half a
    -- later migration relaxing the CHECK would not trip.
    SELECT 'a review gate was lifted by something other than a person',
           c.id::text || ' is actor_kind ' || c.actor_kind
      FROM finding_gate_clearances c
     WHERE c.actor_kind <> 'human'
    UNION ALL
    -- 3. Nothing reaches `reported` except through the transition an operator
    -- makes. A Finding carrying the status and no human transition row is the
    -- shape a direct UPDATE leaves behind.
    SELECT 'a Finding is reported with no operator transition behind it', f.label
      FROM findings f
     WHERE f.status = 'reported'
       AND NOT EXISTS (SELECT 1 FROM finding_transitions t
                        WHERE t.finding_id = f.id AND t.to_status = 'reported'
                          AND t.actor_kind = 'human')
    UNION ALL
    -- 4. And the other direction: the timestamp 023 ranks on says the same
    -- thing the status does. Either alone would make "reported and not yet
    -- reported" a state the ranking can see.
    SELECT 'a Finding''s reported status and its reported_at disagree',
           f.label || ' is ' || f.status || ' and reported_at is ' ||
           coalesce(f.reported_at::text, 'null')
      FROM findings f
     WHERE (f.status = 'reported') <> (f.reported_at IS NOT NULL)
    UNION ALL
    -- 5. A clearance names the Finding's own Program. The composite foreign key
    -- gives this; it is asked anyway because the row is what an audit of a
    -- cross-Program leak would read, and a check that only restates a
    -- constraint is the cheapest one in the file.
    SELECT 'a clearance is filed under another Program', c.id::text
      FROM finding_gate_clearances c
      JOIN findings f ON f.id = c.finding_id
     WHERE f.program_id <> c.program_id
    UNION ALL
    -- 6, 7 and 8 are ticket 29's three, asked about this file's free text. The
    -- reason an operator gives for overruling a gate is written for the person
    -- who reads the audit, and `events` is read by the runtime and quoted into
    -- what it compiles -- so a model that can read a clearance can read an
    -- argument for sending a report and learn to make it. 29 closed the same
    -- three doors on `pending_decisions.answer`; the shape is copied because
    -- the doors are the same three, and a fourth table's free text will want it
    -- again.
    --
    -- First the column itself.
    SELECT 'a clearance''s reason is readable by something that compiles a model''s context',
           c.grantee || ' reads ' || c.column_name
      FROM information_schema.column_privileges c
     WHERE c.table_name = 'finding_gate_clearances' AND c.column_name = 'reason'
       AND c.privilege_type = 'SELECT'
       AND c.grantee NOT IN ('rk2_human','rk2_owner','rk2_migrate','rk2_restore')
    UNION ALL
    -- Then the same text through a view, which runs as its owner and would hand
    -- back what the column grant refuses. Found through the dependency graph:
    -- a view that selects the column depends on it, whatever it calls it.
    SELECT 'a clearance''s reason is readable through a view',
           v.relname || ' read by ' || tp.grantee
      FROM pg_depend dep
      JOIN pg_rewrite rw ON rw.oid = dep.objid AND rw.rulename = '_RETURN'
      JOIN pg_class v ON v.oid = rw.ev_class AND v.relkind = 'v'
      JOIN information_schema.table_privileges tp
        ON tp.table_name = v.relname AND tp.table_schema = 'public'
       AND tp.privilege_type = 'SELECT'
     WHERE dep.classid = 'pg_rewrite'::regclass
       AND dep.refobjid = 'finding_gate_clearances'::regclass
       AND dep.refobjsubid = (SELECT a.attnum FROM pg_attribute a
                               WHERE a.attrelid = 'finding_gate_clearances'::regclass
                                 AND a.attname = 'reason')
       AND tp.grantee NOT IN ('rk2_human','rk2_owner','rk2_migrate','rk2_restore')
    UNION ALL
    -- And the log, which is the one that would have been missed: the row is
    -- kept whole and the payload is what the redaction list decides.
    SELECT 'a clearance''s reason is published to the event log', c.table_name
      FROM event_table_config c
     WHERE c.table_name = 'finding_gate_clearances'
       AND NOT ('reason' = ANY (c.redacted_columns))
$fn$;

REVOKE ALL ON FUNCTION check_finding_reporting() FROM PUBLIC;

COMMENT ON FUNCTION check_finding_reporting() IS
    'What the last step of the harness can get wrong, as rows: a review gate '
    '`report_blockers` does not consult, a gate lifted by something that is not '
    'a person, a Finding that reached `reported` without an operator '
    'transition, a reported_at that disagrees with the status 023 ranks beside '
    'it, and the operator''s own sentence reaching the runtime through a grant, '
    'a view or the event log.';

INSERT INTO standing_checks (name, query, owner_ticket, note) VALUES
    ('finding_reporting', 'SELECT * FROM check_finding_reporting()', '59',
     'the two review gates stay the two judgements, every clearance is a person''s and its reason stays out of what a model is handed, and no Finding is reported except by an operator transition that also wrote the reported_at 023 ranks on');


-- ---------------------------------------------------------------------------
-- 6. Registries
-- ---------------------------------------------------------------------------

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('finding_gate_clearances', 'program_id', 'program-scoped: the purge root'),
    ('finding_gate_clearances', 'finding_id',
     'ON DELETE CASCADE to findings: a clearance is a judgement about one Finding and says nothing without it');

INSERT INTO event_types (id, family, subject_table, description) VALUES
    ('finding.gate_cleared', 'row', 'finding_gate_clearances',
     'an operator lifted one review gate on one Finding, having been told what it was saying (ticket 59)');

-- `reason` is redacted for 29's reason and `detail` is not, and the difference
-- is who wrote them. `detail` is `report_blockers`'s own sentence, which the
-- runtime computed and can compute again; redacting it would hide the machine's
-- words from the machine. `reason` is the operator's, written for the audit and
-- for nobody else -- the event still says the column changed, which is what an
-- integrity check needs, and says "[redacted]" where the sentence was.
INSERT INTO event_table_config
    (table_name, created_type, updated_type, ignored_columns, redacted_columns)
VALUES ('finding_gate_clearances', 'finding.gate_cleared', NULL, '{}', '{reason}');

INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('review_gates', 'reference',
     'the two blocker codes that are a judgement rather than a fact; changed only by migration', '59');

INSERT INTO program_global_tables (table_name, reason) VALUES
    ('review_gates', 'which blockers are a judgement is a fact about the harness, not about one Program');

SELECT attach_event_triggers();
-- 026 finds every table carrying `actor_kind` by catalogue rather than by list,
-- so the clearance table's guard is attached by re-running it. Without this the
-- CHECK would be the only thing saying the row is a person's, and a CHECK reads
-- a column somebody wrote rather than the identity that wrote it.
SELECT attach_actor_kind_guards();

-- The revoke is the sentence and not the grant, which is 41's finding about its
-- own reference table: 029 set `ALTER DEFAULT PRIVILEGES FOR ROLE rk2_owner ...
-- GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO rk2_runtime`, so both
-- tables above arrived readable and writable by the runtime and a `GRANT
-- SELECT` here would say nothing at all.
--
-- Two verbs revoked and not three, for 41's reason: 29's
-- `readwrite_on_every_managed_table` asserts the runtime holds INSERT on every
-- managed table, and a table it cannot INSERT into fails the gate the whole
-- harness opens on. Neither retained INSERT is a way in. A row in
-- `review_gates` makes no gate liftable by itself -- the lift is a clearance,
-- and section 5 fails on a gate `report_blockers` never consults. A clearance
-- the runtime tried to write claims `actor_kind = 'human'` by CHECK, and 026's
-- guard reads `session_user` rather than the column: an insert by the runtime
-- is refused for claiming to be a person.
GRANT SELECT ON review_gates TO rk2_runtime, rk2_human;
REVOKE UPDATE, DELETE ON review_gates FROM rk2_runtime;
GRANT SELECT ON finding_gate_clearances TO rk2_human;
REVOKE UPDATE, DELETE ON finding_gate_clearances FROM rk2_runtime;
-- And the operator's sentence, by column, in 29's shape and for 29's reasons.
-- Column privileges cannot subtract from a table-level grant, so the table
-- grant goes and every column except the reason comes back -- generated rather
-- than listed, because the list is the table's and a copy here would be one
-- migration away from being wrong.
--
-- `xmin` is named because the table grant it used to ride on is gone.
-- `check_event_log_integrity` reads `r.xmin` on every table in
-- `event_table_config` to find a row whose last write emitted no event, and
-- this table is in it. Without that column the revoke would not hide the reason
-- from the integrity gate, it would stop the gate running at all -- and a check
-- that cannot run is reported as a violation, so every `program.run` would end
-- in a permission error rather than a verdict.
--
-- The rest of the row stays readable because the runtime has to see it.
-- `report_blockers` runs as its caller, `record_rendering` asks it before it
-- keeps any bytes, and 42 will not file a rendering for a Finding whose gates
-- are still up: a runtime that cannot see that a gate was lifted is a harness
-- where lifting one changes nothing.
DO $$
DECLARE cols text;
BEGIN
    SELECT string_agg(quote_ident(a.attname), ', ' ORDER BY a.attnum) INTO cols
      FROM pg_attribute a
     WHERE a.attrelid = 'finding_gate_clearances'::regclass
       AND (a.attnum > 0 OR a.attname = 'xmin')
       AND NOT a.attisdropped AND a.attname <> 'reason';
    EXECUTE 'REVOKE SELECT ON finding_gate_clearances FROM rk2_runtime';
    EXECUTE format('GRANT SELECT (%s) ON finding_gate_clearances TO rk2_runtime', cols);
END $$;
REVOKE ALL ON review_gates, finding_gate_clearances FROM rk2_state, rk2_proxy;

COMMENT ON COLUMN finding_gate_clearances.reason IS
    'Why one operator overruled one gate, in their own words. Read by the '
    'operator and by nobody else: `rk2_runtime` holds SELECT on every other '
    'column of this table and not on this one, because the runtime is what '
    'compiles the documents a model is handed and an argument for sending a '
    'report is not one of them. Redacted from the event payload for the same '
    'reason.';

REVOKE ALL ON FUNCTION clear_review_gate(text, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION report_finding(text, uuid, text, text) FROM PUBLIC;
-- 029's default privileges grant EXECUTE on every new function to the runtime
-- as it is created, and revoking from PUBLIC does not touch a direct grant.
-- 032 found this hole on `answer_decision` and left it; here it is closed,
-- because these two are the verbs that decide what leaves for a bounty program.
REVOKE EXECUTE ON FUNCTION clear_review_gate(text, text, text) FROM rk2_runtime;
REVOKE EXECUTE ON FUNCTION report_finding(text, uuid, text, text) FROM rk2_runtime;
GRANT EXECUTE ON FUNCTION clear_review_gate(text, text, text) TO rk2_human;
GRANT EXECUTE ON FUNCTION report_finding(text, uuid, text, text) TO rk2_human;


-- ---------------------------------------------------------------------------
-- 7. The invariants this file must not have broken
-- ---------------------------------------------------------------------------

SELECT enforce_always_triggers();
SELECT enforce_fk_fire_order();
SELECT apply_state_rls();
SELECT apply_state_grants();

-- `apply_state_rls` turns row security on for every program-scoped table and
-- writes the two policies the two machine connections need. Nothing writes one
-- for a person, and row security with no policy returns no rows -- so without
-- this line the SELECT granted to `rk2_human` above is a grant that reads an
-- empty table, and the audit trail this ticket exists to leave is unreadable by
-- the only role allowed to read it. 026 hit the same wall on `pending_decisions`
-- and answered it the same way.
--
-- `FOR SELECT` and not `FOR ALL`, because SELECT is all the operator holds here:
-- a clearance is written by `clear_review_gate`, which is SECURITY DEFINER and
-- runs as the table's owner. A policy for verbs the role cannot use would read
-- as permission it does not have.
--
-- `USING (true)` rather than a scope by Program, because the operator is a
-- person at a console rather than a session bound to one Program, and every
-- command they run already names the Program it is about.
CREATE POLICY finding_gate_clearances_rk2_human ON finding_gate_clearances
    AS PERMISSIVE FOR SELECT TO rk2_human USING (true);
