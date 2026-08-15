-- ---------------------------------------------------------------------------
-- 20260815T180000Z__a_blind_validator_answers_from_the_packet.sql  (ticket 37)
-- ---------------------------------------------------------------------------
--   036 made the first Finding and left it a candidate: a claim one run held,
--   written up by the hunter that pursued it. 011 built the three tables this
--   file finally fills -- `validation_queue`, `verdicts` and a view called
--   `v_validation_packet` -- and the roster has held a `validator` role with a
--   `validate.judge` group and no runtime serving it since 018. Nothing has
--   ever queued a Finding, served a packet or written a verdict.
--
--   The whole point of the role is what it is not shown. A hunter that decides
--   its own work is sound is a hunter marking its own homework, and the shape
--   of the mistake is not dishonesty -- it is that the reasoning which produced
--   the claim is the reasoning that would have to notice the claim is wrong. So
--   the validator is a session that never met the hunter: a different top-level
--   session, started by the runtime, holding one document and one closed answer.
--
--   Three decisions run through this file.
--
--   The packet is a positive selection and the selection is checkable. Not "a
--   view that happens to name some columns" -- a table of exactly which column
--   of which relation may be read, and a section 10 assertion that the function
--   building the packet depends on those columns and on no others. PostgreSQL
--   records the column dependencies of a `BEGIN ATOMIC` SQL function in
--   `pg_depend`, so the allowlist is enforced against the parse tree rather
--   than against a text match or a promise. A column added to `findings`
--   tomorrow is invisible to the validator, and a later file that adds one to
--   the packet fails to apply until it says so in the allowlist.
--
--   The packet carries no free text. Every field in it is a word from a closed
--   vocabulary, a structured document a shape rule already validates, an
--   identifier, a digest, a number or a timestamp. The two prose fields a
--   hunter writes -- `findings.title` and `hypotheses.statement` -- are
--   deliberately absent, and so are the `detail` strings on a Test's
--   preconditions, the `reason` and `notes` on a Receipt, and every `rationale`
--   on every transition. What is left of the Test is its actions and its
--   assertions, both of which the 035 shape rules close. The residual channel
--   is the request itself: a URL is free-ish text and it is in the packet,
--   because a validator that cannot see what was asked cannot judge what came
--   back. That one is stated rather than closed.
--
--   The verdict is input, not authority. `submit_verdict` writes a row saying
--   what the validator concluded; what the Finding becomes is decided here, by
--   a trigger that reads the verdict and the run beside it. A `confirmed`
--   verdict on a Finding whose reproducing replay did not hold moves nothing,
--   and the reason it moves nothing is a constraint rather than a policy in
--   Python: 015 already pinned `validated_by_test_run_id` to a run whose
--   outcome is `holds` through a MATCH FULL composite key, and this file adds
--   the rest -- that the run is a replay of this Finding's own Test, that it is
--   not the run the Finding was born from, and that a verdict was actually
--   given by a session that was actually served the packet it answered.
--
--   What is deliberately not here: severity. A confirmed Finding is still
--   `info` on an `undetermined` basis, because 038 is the ticket that separates
--   demonstrated impact from inference and doing it here would mean deriving an
--   impact number from a judgement about reproduction.
-- ---------------------------------------------------------------------------


-- ---------------------------------------------------------------------------
-- 1. Which column of which relation the packet may read
-- ---------------------------------------------------------------------------
-- Criterion 1, as data rather than as a view definition. A view would state the
-- same selection and state it once, and nothing would notice when a later file
-- replaced it with a wider one -- `CREATE OR REPLACE VIEW` is how a column
-- arrives quietly. So the allowlist is a table, the packet is a function, and
-- section 10 asserts that the function reads exactly what the table permits.
--
-- Two purposes, because a column is read for two different reasons and only one
-- of them is a leak. A `field` column becomes a key of the packet and the
-- validator sees its value. A `reached` column is how the row was found -- a
-- primary key, a foreign key, the Program it belongs to -- and its value never
-- crosses. Splitting them is what makes the allowlist readable as the answer to
-- "what does the validator see": the `field` rows are that answer, and the
-- `reached` rows are the joins that got there.
--
-- `packet_keys` is an array because one column can fill more than one key:
-- `tests.spec` is read twice, once for the actions and once for the assertions,
-- and it is the only column in the corpus that this is true of. The alternative
-- was a row per key with a nullable column name, which would have made the
-- primary key of an allowlist nullable.

CREATE TABLE validation_packet_columns (
    relation    text NOT NULL,
    column_name text NOT NULL,
    purpose     text NOT NULL CHECK (purpose IN ('field', 'reached')),
    packet_keys text[] NOT NULL DEFAULT '{}',
    note        text NOT NULL,
    PRIMARY KEY (relation, column_name),
    -- The two halves of the split, as a constraint: a field states where it
    -- lands and a reached column states nothing, so a row cannot be half of
    -- each. An allowlist whose entries are ambiguous about whether a value
    -- crosses is not an allowlist.
    CHECK ((purpose = 'field') = (cardinality(packet_keys) > 0))
);

COMMENT ON TABLE validation_packet_columns IS
    'Criterion 1. Every column `rk2_validation_packet` may read, and whether '
    'its value reaches the validator or only the join that found the row. '
    'Section 10 of ticket 37 asserts the function''s `pg_depend` column set is '
    'exactly this table, so a column added to a source relation is invisible '
    'until a migration says otherwise.';

COMMENT ON COLUMN validation_packet_columns.purpose IS
    '`field` means the value becomes a key of the packet; `reached` means it '
    'was read to find the row and never crosses.';

INSERT INTO program_global_tables (table_name, reason) VALUES
    ('validation_packet_columns',
     'the shape of the blind packet, which is the same for every Program: a Program-specific allowlist would be a Program that can be validated less blindly than another');

INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('validation_packet_columns', 'reference',
     'the compiled shape of the validation packet; rows are written by migrations and read by the packet function', '37');

INSERT INTO validation_packet_columns (relation, column_name, purpose, packet_keys, note) VALUES
    -- The Finding. Not `title`: it is the one free-text field a hunter writes
    -- onto a Finding and no rule reads it, which makes it exactly the field a
    -- hunter would use to talk to the validator. Not `severity` either -- a
    -- candidate is `info` on an `undetermined` basis by construction, so
    -- publishing it would be publishing a constant.
    ('findings', 'id',                    'reached', '{}',                     'the row asked for'),
    ('findings', 'program_id',            'reached', '{}',                     'every join below is scoped to it'),
    ('findings', 'opened_by_test_run_id', 'reached', '{}',                     'the run the candidate was born from'),
    ('findings', 'label',                 'field',   '{finding.label}',        'what the verdict will name'),
    ('findings', 'class_id',              'field',   '{finding.class}',        'the vulnerability class claimed, from 018''s vocabulary'),
    ('findings', 'property_class',        'field',   '{finding.property_class}', 'what was tested, from 007''s vocabulary'),
    ('findings', 'demonstrated',          'field',   '{finding.demonstrated}', '036''s reading of the holding run, shape-checked'),
    ('findings', 'created_at',            'field',   '{finding.opened_at}',    'how old the claim is'),

    -- The claim, by reference. Criterion "a Finding references its Hypotheses"
    -- is met by the label; `statement` is the hunter''s own sentence and stays
    -- out for the reason `title` does.
    ('finding_hypotheses', 'finding_id',    'reached', '{}', 'the edge from the Finding'),
    ('finding_hypotheses', 'hypothesis_id', 'reached', '{}', 'to the claim'),
    ('finding_hypotheses', 'program_id',    'reached', '{}', 'scoped'),
    ('hypotheses', 'id',             'reached', '{}',                        'the claim'),
    ('hypotheses', 'program_id',     'reached', '{}',                        'scoped'),
    ('hypotheses', 'label',          'field',   '{hypothesis.label}',        'the reference, without the prose'),
    ('hypotheses', 'property_class', 'field',   '{hypothesis.property_class}', 'what the claim is about'),
    ('hypotheses', 'status',         'field',   '{hypothesis.status}',       'so a claim that stopped being supported is visible'),

    -- The Test. `spec` is read for two of its five parts. The other three --
    -- preconditions, setup, cleanup -- carry `detail` strings a hunter writes,
    -- and the actions and assertions are what the run was actually evaluated
    -- against. The digest names the whole document, so the validator can be
    -- told the projection is a projection.
    ('tests', 'id',            'reached', '{}',                 'the Test the runs are of'),
    ('tests', 'program_id',    'reached', '{}',                 'scoped'),
    ('tests', 'label',         'field',   '{test.label}',       'the reference'),
    ('tests', 'spec_sha256',   'field',   '{test.spec_sha256}', 'names the whole specification, projection and all'),
    ('tests', 'spec',          'field',   '{test.actions,test.assertions}', 'the two parts 035''s shape rules close entirely'),

    -- The two runs: the one the Finding was born from and the one being offered
    -- as a reproduction. Same shape for both, so a validator comparing them is
    -- comparing like with like.
    ('test_runs', 'id',                'reached', '{}',                       'each of the two'),
    ('test_runs', 'program_id',        'reached', '{}',                       'scoped'),
    ('test_runs', 'test_id',           'reached', '{}',                       'and both of one Test'),
    ('test_runs', 'outcome',           'field',   '{runs.outcome}',           'holds, refutes or inconclusive'),
    ('test_runs', 'lane',              'field',   '{runs.lane}',              'so a reproduction on the wrong Lane is visible'),
    ('test_runs', 'assertion_results', 'field',   '{runs.assertion_results}', 'every assertion with its verdict, and the ones that failed'),
    ('test_runs', 'started_at',        'field',   '{runs.started_at}',        'when'),
    ('test_runs', 'finished_at',       'field',   '{runs.finished_at}',       'and for how long'),

    -- The Receipts of each run, in the order they were made. `reason` and
    -- `notes` are prose the door and the runtime write and stay out; the rest
    -- is the exchange as facts.
    ('test_run_receipts', 'test_run_id', 'reached', '{}',                 'the run'),
    ('test_run_receipts', 'receipt_id',  'reached', '{}',                 'the exchange'),
    ('test_run_receipts', 'program_id',  'reached', '{}',                 'scoped'),
    ('test_run_receipts', 'ordinal',     'field',   '{receipts.ordinal}', 'the order they were made in'),
    ('test_run_receipts', 'role',        'field',   '{receipts.role}',    'baseline, variant or control'),
    ('receipts', 'id',                 'reached', '{}',                       'the exchange'),
    ('receipts', 'program_id',         'reached', '{}',                       'scoped'),
    ('receipts', 'label',              'field',   '{receipts.label}',         'the stable reference §6 allows to travel'),
    ('receipts', 'lane',               'field',   '{receipts.lane}',          'so a Receipt from the wrong Lane is visible'),
    ('receipts', 'method',             'field',   '{receipts.method}',        'what was asked'),
    ('receipts', 'scheme',             'field',   '{receipts.scheme}',        'of what'),
    ('receipts', 'host',               'field',   '{receipts.host}',          'of whom'),
    ('receipts', 'port',               'field',   '{receipts.port}',          'on which port'),
    ('receipts', 'path',               'field',   '{receipts.path}',          'at which path'),
    ('receipts', 'query_sha256',       'field',   '{receipts.query_sha256}',  'a digest, so two requests differing only in query are distinguishable'),
    ('receipts', 'status_code',        'field',   '{receipts.status_code}',   'what came back'),
    ('receipts', 'ts_arrival',         'field',   '{receipts.at}',            'when'),
    ('receipts', 'request_agent_sha',  'field',   '{receipts.request}',       'the agent-visible request bytes, by hash'),
    ('receipts', 'response_agent_sha', 'field',   '{receipts.response}',      'and the response, by hash'),

    -- The Artifacts, by hash and size and nothing else. The validator holds no
    -- tool that reads bytes -- that is criterion 3 -- so what it gets is what a
    -- hash and a length can tell it: whether two bodies are the same body.
    ('artifacts', 'sha256',       'field', '{artifacts.sha256}',       'the content address'),
    ('artifacts', 'byte_size',    'field', '{artifacts.byte_size}',    'how much of it there was'),
    ('artifacts', 'content_type', 'field', '{artifacts.content_type}', 'and what it claimed to be');

GRANT SELECT ON validation_packet_columns TO rk2_runtime, rk2_human;


-- ---------------------------------------------------------------------------
-- 2. The packet
-- ---------------------------------------------------------------------------
-- `BEGIN ATOMIC` rather than a quoted body, and that is the load-bearing
-- decision of this file. A quoted body is a string the server parses when it
-- runs; an atomic one is parsed at definition and its column references are
-- recorded in `pg_depend`. So the allowlist above can be checked against what
-- the function actually reads rather than against what a comment says it reads,
-- and the check is not a text match that a rename or a `SELECT *` would slip
-- past.
--
-- It also fixes the search path at definition time, which is the same property
-- from the other side: a caller cannot put a table of its own in front of
-- `findings` and have the packet read that instead.
--
-- Every join carries the Program. `rk2_runtime`'s policy on these tables is
-- `USING (true)` -- it is the role that reads across Programs to schedule them
-- -- so the isolation here is written out rather than inherited, and a Receipt
-- from another Program cannot arrive by naming a run that does not belong to
-- this Finding.

CREATE FUNCTION rk2_validation_packet(p_program uuid, p_finding uuid, p_replay uuid)
RETURNS jsonb LANGUAGE sql STABLE
BEGIN ATOMIC
    SELECT jsonb_build_object(
        'finding', jsonb_build_object(
            'label',          f.label,
            'class',          f.class_id,
            'property_class', f.property_class,
            'demonstrated',   f.demonstrated,
            'opened_at',      f.created_at),

        'hypothesis', (
            SELECT jsonb_build_object(
                       'label',          h.label,
                       'property_class', h.property_class,
                       'status',         h.status)
              FROM finding_hypotheses fh
              JOIN hypotheses h ON h.id = fh.hypothesis_id
                               AND h.program_id = fh.program_id
             WHERE fh.finding_id = f.id AND fh.program_id = f.program_id
             ORDER BY h.label
             LIMIT 1),

        'test', (
            SELECT jsonb_build_object(
                       'label',       t.label,
                       'spec_sha256', t.spec_sha256,
                       'actions',     t.spec -> 'actions',
                       'assertions',  t.spec -> 'assertions')
              FROM test_runs run
              JOIN tests t ON t.id = run.test_id AND t.program_id = run.program_id
             WHERE run.id = f.opened_by_test_run_id AND run.program_id = f.program_id),

        -- Both runs through one writing. Which one a row is, is read off the
        -- Finding rather than passed in beside it: a caller that could name the
        -- opening run would be a caller that could relabel the reproduction as
        -- the birth and hide that there was only ever one run.
        'runs', (
            SELECT jsonb_object_agg(
                       CASE WHEN run.id = f.opened_by_test_run_id
                            THEN 'opened' ELSE 'replay' END,
                       jsonb_build_object(
                           'outcome',           run.outcome,
                           'lane',              run.lane,
                           'assertion_results', run.assertion_results,
                           'started_at',        run.started_at,
                           'finished_at',       run.finished_at,
                           'receipts', (
                               SELECT coalesce(jsonb_agg(jsonb_build_object(
                                          'ordinal',      trr.ordinal,
                                          'role',         trr.role,
                                          'label',        r.label,
                                          'lane',         r.lane,
                                          'method',       r.method,
                                          'scheme',       r.scheme,
                                          'host',         r.host,
                                          'port',         r.port,
                                          'path',         r.path,
                                          'query_sha256', r.query_sha256,
                                          'status_code',  r.status_code,
                                          'at',           r.ts_arrival,
                                          'request',      r.request_agent_sha,
                                          'response',     r.response_agent_sha)
                                          ORDER BY trr.ordinal), '[]'::jsonb)
                                 FROM test_run_receipts trr
                                 JOIN receipts r ON r.id = trr.receipt_id
                                                AND r.program_id = trr.program_id
                                WHERE trr.test_run_id = run.id
                                  AND trr.program_id = run.program_id)))
              FROM test_runs run
             WHERE run.program_id = f.program_id
               AND run.id IN (f.opened_by_test_run_id, p_replay)),

        'artifacts', (
            SELECT coalesce(jsonb_agg(jsonb_build_object(
                       'sha256',       a.sha256,
                       'byte_size',    a.byte_size,
                       'content_type', a.content_type)
                       ORDER BY a.sha256), '[]'::jsonb)
              FROM artifacts a
             WHERE a.sha256 IN (
                SELECT sha.value
                  FROM test_run_receipts trr
                  JOIN receipts r ON r.id = trr.receipt_id
                                 AND r.program_id = trr.program_id
                  CROSS JOIN LATERAL (VALUES (r.request_agent_sha),
                                             (r.response_agent_sha)) AS sha(value)
                 WHERE trr.program_id = f.program_id
                   AND trr.test_run_id IN (f.opened_by_test_run_id, p_replay)
                   AND sha.value IS NOT NULL)))
      FROM findings f
     WHERE f.id = p_finding AND f.program_id = p_program;
END;

COMMENT ON FUNCTION rk2_validation_packet(uuid, uuid, uuid) IS
    'Criteria 1 and 2. The whole world one validator session is given, built '
    'from an empty object upward out of the columns `validation_packet_columns` '
    'permits and no others. Carries no field a hunter writes prose into.';

REVOKE ALL ON FUNCTION rk2_validation_packet(uuid, uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rk2_validation_packet(uuid, uuid, uuid) TO rk2_runtime;

-- What a session was served, as one comparable value. `jsonb::text` is
-- canonical -- keys sorted, duplicates gone, whitespace fixed -- so two packets
-- that say the same thing digest the same, and one that would now say something
-- different does not. That is the whole mechanism behind criterion 6's
-- "changed Artifact": the runtime does not have to enumerate what could have
-- moved between serving and answering, because anything that moved changes this
-- number.
CREATE FUNCTION rk2_validation_digest(p_packet jsonb) RETURNS text
LANGUAGE sql IMMUTABLE AS $fn$
    SELECT encode(sha256(convert_to(p_packet::text, 'utf8')), 'hex')
$fn$;

COMMENT ON FUNCTION rk2_validation_digest(jsonb) IS
    'The packet as one comparable value. A verdict is about the document the '
    'session was served, and a document that would now read differently is a '
    'different document.';

REVOKE ALL ON FUNCTION rk2_validation_digest(jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rk2_validation_digest(jsonb) TO rk2_runtime, rk2_human;


-- ---------------------------------------------------------------------------
-- 3. What may not be validated, and why
-- ---------------------------------------------------------------------------
-- 036's shape: a sentence rather than an exception, so the caller can file what
-- it heard. The same reasoning applies and one more reason on top -- a refused
-- validation is the case criterion 6 is entirely about, so the refusal is the
-- evidence that the fail-closed happened rather than a stack trace in a log.
--
-- The arms are ordered the way a caller can act on them: the Finding, then the
-- request, then the run offered as a reproduction, then the evidence behind it.

CREATE FUNCTION rk2_validation_refusal(p_program uuid, p_finding uuid, p_replay uuid)
RETURNS text LANGUAGE plpgsql STABLE AS $fn$
DECLARE
    v_finding findings%ROWTYPE;
    v_run     test_runs%ROWTYPE;
    v_state   text;
    v_missing text;
BEGIN
    SELECT * INTO v_finding FROM findings
     WHERE id = p_finding AND program_id = p_program;
    IF NOT FOUND THEN
        RETURN 'no Finding ' || p_finding::text || ' in this Program';
    END IF;

    IF v_finding.status <> 'candidate' THEN
        RETURN 'the Finding ' || v_finding.label || ' is ' || v_finding.status
               || '; a validation begins on a candidate';
    END IF;

    -- 036 makes this unreachable through `open_finding` and reachable by
    -- anyone holding INSERT, which is why it is an arm rather than an
    -- assumption: a Finding with no birth run has no Test, so there is nothing
    -- for a reproduction to be a reproduction of.
    IF v_finding.opened_by_test_run_id IS NULL THEN
        RETURN 'the Finding ' || v_finding.label
               || ' names no holding run and cannot be reproduced';
    END IF;

    SELECT state INTO v_state FROM validation_queue
     WHERE finding_id = p_finding AND program_id = p_program;
    IF NOT FOUND THEN
        RETURN 'nothing asked for the Finding ' || v_finding.label
               || ' to be validated';
    END IF;
    IF v_state <> 'queued' THEN
        RETURN 'the validation of ' || v_finding.label || ' is already ' || v_state;
    END IF;

    SELECT * INTO v_run FROM test_runs
     WHERE id = p_replay AND program_id = p_program;
    IF NOT FOUND THEN
        RETURN 'no Test run ' || p_replay::text || ' in this Program';
    END IF;

    -- The reproduction is a second run, not the first one offered again. A
    -- Finding that validated on its own birth run would be a Finding that
    -- validated on nothing: the run is the reason the candidate exists.
    IF v_run.id = v_finding.opened_by_test_run_id THEN
        RETURN 'the run offered is the run ' || v_finding.label
               || ' was opened from; a reproduction is a second run';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM test_runs opened
         WHERE opened.id = v_finding.opened_by_test_run_id
           AND opened.program_id = p_program
           AND opened.test_id = v_run.test_id) THEN
        RETURN 'the run offered is a run of another Test than the one '
               || v_finding.label || ' rests on';
    END IF;

    IF v_run.lane <> 'replay' THEN
        RETURN 'the run offered is on the ' || v_run.lane
               || ' Lane; a reproduction is performed through the replay Lane';
    END IF;

    IF v_run.finished_at IS NULL THEN
        RETURN 'the run offered has not finished';
    END IF;

    -- Criterion 6's missing holding replay, in the form it actually arrives in:
    -- the reproduction ran and the target no longer does what it did. Refused
    -- here rather than left to the composite key `record_verdict` writes into,
    -- because that key only refuses a `confirmed` verdict and refuses it as a
    -- foreign key violation -- after a session was opened, a packet was served
    -- and an opus session was spent judging a document whose own reproduction
    -- says it did not reproduce.
    IF v_run.outcome <> 'holds' THEN
        RETURN 'the reproduction of ' || v_finding.label || ' concluded '
               || v_run.outcome || '; there is no holding replay to judge';
    END IF;

    -- Criterion 6's foreign Receipt. Both runs' Receipts are read into the
    -- packet, so a Receipt belonging to another Program -- or to no Program's
    -- agent traffic at all -- is a fact the validator would be shown as this
    -- Finding's evidence. `proxy_internal` is the door's own housekeeping and
    -- was never anybody's evidence; 036 widened the citation rules to the agent
    -- and replay pair for the same reason.
    SELECT r.label INTO v_missing
      FROM test_run_receipts trr
      JOIN receipts r ON r.id = trr.receipt_id
     WHERE trr.test_run_id IN (v_finding.opened_by_test_run_id, p_replay)
       AND (r.program_id <> p_program OR r.lane NOT IN ('agent', 'replay'))
     LIMIT 1;
    IF v_missing IS NOT NULL THEN
        RETURN 'a run cites the Receipt ' || v_missing
               || ', which is not this Program''s evidence';
    END IF;

    -- Criterion 6's changed Artifact, in the one form SQL can see: the bytes
    -- are on a filesystem no statement here reaches, so what this can check is
    -- that the row is still there and has not been purged. Whether the bytes
    -- still hash to their name is `rk artifact audit`'s question and the
    -- runtime asks it before it starts a session.
    SELECT sha.value INTO v_missing
      FROM test_run_receipts trr
      JOIN receipts r ON r.id = trr.receipt_id AND r.program_id = trr.program_id
      CROSS JOIN LATERAL (VALUES (r.request_agent_sha),
                                 (r.response_agent_sha)) AS sha(value)
     WHERE trr.test_run_id IN (v_finding.opened_by_test_run_id, p_replay)
       AND trr.program_id = p_program
       AND sha.value IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM artifacts a
                        WHERE a.sha256 = sha.value AND a.purged_at IS NULL)
     LIMIT 1;
    IF v_missing IS NOT NULL THEN
        RETURN 'the Artifact ' || v_missing
               || ' a Receipt names is no longer held';
    END IF;

    RETURN NULL;
END $fn$;

COMMENT ON FUNCTION rk2_validation_refusal(uuid, uuid, uuid) IS
    'Criterion 6, as a sentence or null. Everything that makes a validation '
    'fail closed before a session is started: no request, a Finding that is '
    'not a candidate, a reproduction that is the birth run, of another Test, '
    'on another Lane, unfinished or no longer holding, a foreign Receipt, an '
    'Artifact no longer held.';

REVOKE ALL ON FUNCTION rk2_validation_refusal(uuid, uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rk2_validation_refusal(uuid, uuid, uuid) TO rk2_runtime, rk2_human;


-- ---------------------------------------------------------------------------
-- 4. One attempt, one document, one answer
-- ---------------------------------------------------------------------------
-- 011 built `validation_queue` as the request and `verdicts` as the answer, and
-- left nothing in the middle. What is missing is the thing criterion 5 turns
-- on: which document a verdict is an answer to. Without it a verdict is a word
-- about a Finding, and a Finding is a moving target -- its Receipts can be
-- purged, its claim can be reopened, a second run can arrive. With it a verdict
-- is an answer to one digest, and an answer to a document that no longer exists
-- is not an answer at all.
--
-- The row is also the record of a refusal. `finding_proposals` is 036's
-- precedent and the argument is the same: an operator reading a Program with no
-- validated Findings cannot tell "nothing was submitted" from "everything was
-- refused", and the sentence that refused it is the only thing that tells them
-- apart.

-- 011 gave `verdicts` no composite key to be referenced by, because nothing
-- referenced it. 017's rule is that an edge between two Program-scoped rows
-- carries the Program on both sides, and the attempt below is the first such
-- edge.
ALTER TABLE verdicts ADD CONSTRAINT verdicts_id_program_key UNIQUE (id, program_id);

CREATE TABLE validation_attempts (
    id           uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id   uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    finding_id   uuid NOT NULL,
    replay_test_run_id uuid,
    agent_run_id uuid,
    packet_sha256 text CHECK (packet_sha256 ~ '^[0-9a-f]{64}$'),
    outcome      text NOT NULL DEFAULT 'open'
                 CHECK (outcome IN ('open', 'answered', 'stale', 'refused',
                                    'unanswered')),
    refusal      text,
    verdict_id   uuid,
    opened_at    timestamptz NOT NULL DEFAULT now(),
    closed_at    timestamptz,
    FOREIGN KEY (finding_id, program_id) REFERENCES findings (id, program_id)
        ON DELETE CASCADE,
    FOREIGN KEY (replay_test_run_id, program_id) REFERENCES test_runs (id, program_id)
        ON DELETE CASCADE,
    FOREIGN KEY (agent_run_id, program_id) REFERENCES agent_runs (id, program_id)
        ON DELETE CASCADE,
    FOREIGN KEY (verdict_id, program_id) REFERENCES verdicts (id, program_id)
        ON DELETE CASCADE,
    -- A refusal is a sentence and an outcome at once, per 036. Three outcomes
    -- carry one: `refused` is the packet that was never served, `unanswered`
    -- the session that was served one and said nothing about it, and `stale`
    -- the session that answered about a document that had moved. The last of
    -- those keeps the word it said, because this row is the record of that one
    -- reading and `verdicts` is the table of answers about a Finding.
    CHECK ((outcome IN ('refused', 'unanswered', 'stale')) = (refusal IS NOT NULL)),
    -- A refused attempt served no document and named no run: it is the record
    -- that nothing happened. Everything else did both, `unanswered` included --
    -- which is the point of telling the two apart. A session that was given the
    -- packet and produced no verdict cost a reproduction and an opus run, and an
    -- attempt that recorded neither would make that look like nothing happening.
    CHECK ((outcome = 'refused')
           = (packet_sha256 IS NULL AND replay_test_run_id IS NULL)),
    -- Only an answered attempt names a verdict, and an answered one always
    -- does. `stale` is the interesting one: the session answered, and what it
    -- answered about had changed underneath it.
    CHECK ((outcome = 'answered') = (verdict_id IS NOT NULL)),
    CHECK ((outcome = 'open') = (closed_at IS NULL))
);

COMMENT ON TABLE validation_attempts IS
    'One row per attempt to validate a Finding: which reproduction was offered, '
    'the digest of the packet the session was served, and what came of it. The '
    'refused ones are criterion 6''s evidence that a validation failed closed.';

COMMENT ON COLUMN validation_attempts.packet_sha256 IS
    'Criterion 6. The document the session was actually given. A verdict is '
    'checked against a freshly built packet and refused as `stale` when the two '
    'disagree, which is how a changed Artifact, a purged Receipt or a reopened '
    'claim invalidates a judgement that was made before it moved.';

CREATE INDEX validation_attempts_open_idx
    ON validation_attempts (program_id, finding_id)
 WHERE outcome = 'open';

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('validation_attempts', 'program_id',         'program-scoped: the purge root'),
    ('validation_attempts', 'finding_id',         'ON DELETE CASCADE to findings: the Finding the attempt was about'),
    ('validation_attempts', 'replay_test_run_id', 'ON DELETE CASCADE to test_runs: the reproduction offered'),
    ('validation_attempts', 'agent_run_id',       'ON DELETE CASCADE to agent_runs: the session that was served the packet'),
    ('validation_attempts', 'verdict_id',         'ON DELETE CASCADE to verdicts: the answer it produced');

INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('validation_attempts', 'audit',
     'the append-only record of what was served and what came back; a refused or stale attempt writes no canonical row for an Event to be about, and an answered one is covered by the verdict and the transition it caused', '37');

SELECT attach_event_triggers();

GRANT SELECT, INSERT ON validation_attempts TO rk2_runtime;
GRANT SELECT ON validation_attempts TO rk2_human;

-- Closing an attempt is an UPDATE and the only one, so the immutability rule is
-- written as "the columns that were true when it opened stay true" rather than
-- as a blanket refusal. What a later reader needs is that nobody moved the
-- digest after the answer came in.
CREATE FUNCTION reject_validation_attempt_rewrite() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    IF TG_OP = 'DELETE' THEN
        -- 016's escape hatch and the only one: a purge is the single thing that
        -- removes an audit row, and it announces itself on the connection.
        IF coalesce(current_setting('app.purging', true), 'off') = 'on' THEN
            RETURN OLD;
        END IF;
        RAISE EXCEPTION 'a validation attempt is not deleted';
    END IF;
    -- `agent_run_id` is in the list because it is half of what was served: the
    -- digest says which document and this says which session read it, and a
    -- close that could rewrite it could file one session's answer against
    -- another session's reading.
    IF NEW.program_id IS DISTINCT FROM OLD.program_id
       OR NEW.finding_id IS DISTINCT FROM OLD.finding_id
       OR NEW.replay_test_run_id IS DISTINCT FROM OLD.replay_test_run_id
       OR NEW.agent_run_id IS DISTINCT FROM OLD.agent_run_id
       OR NEW.packet_sha256 IS DISTINCT FROM OLD.packet_sha256
       OR NEW.opened_at IS DISTINCT FROM OLD.opened_at THEN
        RAISE EXCEPTION 'a validation attempt states what it was served once';
    END IF;
    IF OLD.outcome <> 'open' THEN
        RAISE EXCEPTION 'the validation attempt % is already %', OLD.id, OLD.outcome;
    END IF;
    RETURN NEW;
END $fn$;

COMMENT ON FUNCTION reject_validation_attempt_rewrite() IS
    'An attempt is closed once and states what it was served once. Everything '
    'true when it opened stays true, and only a purge removes the row.';

CREATE TRIGGER validation_attempts_state_once
    BEFORE UPDATE OR DELETE ON validation_attempts
    FOR EACH ROW EXECUTE FUNCTION reject_validation_attempt_rewrite();

GRANT UPDATE ON validation_attempts TO rk2_runtime;


-- ---------------------------------------------------------------------------
-- 5. Asking, and being served
-- ---------------------------------------------------------------------------
-- Two verbs and a deliberate gap between them. `request_validation` is the
-- orchestrator's step -- 011 built the queue for exactly that and described it
-- as "one label, nothing else" -- and `open_validation` is the runtime's. The
-- gap is where the reproduction happens: something has to replay the Test
-- before there is a second run to offer, and that is 035's verb, run by the
-- runtime, between the request and the session.

CREATE FUNCTION request_validation(p_program uuid, p_finding uuid) RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    v_label text;
    v_state text;
BEGIN
    SELECT label INTO v_label FROM findings
     WHERE id = p_finding AND program_id = p_program;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('outcome', 'refused',
                                  'refusal', 'no Finding ' || p_finding::text
                                             || ' in this Program');
    END IF;

    -- Re-queueing a Finding whose last validation is done is how a second
    -- reproduction is asked for: 011 made the row unique per Finding, so the
    -- queue is a state and not a log, and the log is `validation_attempts`.
    INSERT INTO validation_queue (program_id, finding_id, state)
         VALUES (p_program, p_finding, 'queued')
    ON CONFLICT (program_id, finding_id) DO UPDATE
            SET state = 'queued', requested_at = now()
          WHERE validation_queue.state = 'done'
      RETURNING state INTO v_state;

    IF v_state IS NULL THEN
        SELECT state INTO v_state FROM validation_queue
         WHERE finding_id = p_finding AND program_id = p_program;
        RETURN jsonb_build_object('outcome', 'refused', 'finding', v_label,
                                  'refusal', 'a validation of ' || v_label
                                             || ' is already ' || v_state);
    END IF;
    RETURN jsonb_build_object('outcome', 'queued', 'finding', v_label);
END $fn$;

COMMENT ON FUNCTION request_validation(uuid, uuid) IS
    'Ask for one Finding to be validated. The whole of the request is the '
    'label: 011 built the queue with no column for a reason, and a reason is '
    'the thing the validator may not be told.';

REVOKE ALL ON FUNCTION request_validation(uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION request_validation(uuid, uuid) TO rk2_runtime;

CREATE FUNCTION open_validation(
    p_program   uuid,
    p_finding   uuid,
    p_replay    uuid,
    p_agent_run uuid DEFAULT NULL
) RETURNS jsonb LANGUAGE plpgsql AS $fn$
DECLARE
    v_refusal text;
    v_label   text;
    v_packet  jsonb;
    v_digest  text;
    v_attempt uuid;
BEGIN
    -- One validation of one Finding at a time, and the lock is on the Finding
    -- for 023's reason: the check below is "no attempt is open", which two
    -- transactions can both pass while neither has inserted yet. `FOR UPDATE`
    -- on `validation_attempts` locks what is there and locks nothing when there
    -- is nothing, which is exactly the case that must not race.
    PERFORM pg_advisory_xact_lock(hashtextextended(p_finding::text, 0));

    SELECT label INTO v_label FROM findings
     WHERE id = p_finding AND program_id = p_program;

    -- Asked before `rk2_validation_refusal` rather than after it, because the
    -- Finding under judgement is what this arm is about: opening a validation
    -- moves the Finding to `validating` in the same transaction, so the general
    -- refusal always gets there first with "a validation begins on a candidate"
    -- -- true, and silent about the session that is holding it.
    IF EXISTS (SELECT 1 FROM validation_attempts
                WHERE finding_id = p_finding AND program_id = p_program
                  AND outcome = 'open') THEN
        v_refusal := 'a validation of ' || coalesce(v_label, p_finding::text)
                     || ' is already in flight';
    ELSE
        v_refusal := rk2_validation_refusal(p_program, p_finding, p_replay);
    END IF;

    IF v_refusal IS NOT NULL THEN
        INSERT INTO validation_attempts (program_id, finding_id, agent_run_id,
                                         outcome, refusal, closed_at)
             VALUES (p_program, p_finding, p_agent_run, 'refused', v_refusal, now())
          RETURNING id INTO v_attempt;
        RETURN jsonb_build_object('outcome', 'refused', 'attempt', v_attempt,
                                  'finding', v_label, 'refusal', v_refusal);
    END IF;

    v_packet := rk2_validation_packet(p_program, p_finding, p_replay);
    v_digest := rk2_validation_digest(v_packet);

    INSERT INTO validation_attempts (program_id, finding_id, replay_test_run_id,
                                     agent_run_id, packet_sha256)
         VALUES (p_program, p_finding, p_replay, p_agent_run, v_digest)
      RETURNING id INTO v_attempt;

    UPDATE validation_queue SET state = 'running'
     WHERE finding_id = p_finding AND program_id = p_program;

    -- The Finding says it is under judgement before the session starts, so an
    -- operator reading the table while a validator is thinking sees a state
    -- rather than a gap, and a second `open_finding` merge onto the cell cannot
    -- quietly change what is being judged.
    INSERT INTO finding_transitions (program_id, finding_id, from_status,
                                     to_status, actor_kind, agent_run_id, rationale)
         VALUES (p_program, p_finding, 'candidate', 'validating', 'runtime',
                 p_agent_run, 'served to a blind validator');

    RETURN jsonb_build_object('outcome', 'opened', 'attempt', v_attempt,
                              'finding', v_label, 'packet_sha256', v_digest,
                              'packet', v_packet);
END $fn$;

COMMENT ON FUNCTION open_validation(uuid, uuid, uuid, uuid) IS
    'Serve one validation packet, or refuse and file why. Takes the Finding to '
    'validating, records the digest of what was served, and returns the packet '
    'the runtime hands to a session that has nothing else.';

REVOKE ALL ON FUNCTION open_validation(uuid, uuid, uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION open_validation(uuid, uuid, uuid, uuid) TO rk2_runtime;

-- The gap, made passable. 035 admits a replay only against a `testable` claim,
-- and the run that opened the Finding is the run that settled the claim to
-- `supported` -- so at the moment a validation is asked for, the one verb that
-- can produce a second run of the Test refuses to run it. That refusal is right
-- for what it was written about: a claim that has been settled is not re-tested
-- on a whim, and a second run started by nobody in particular is a second
-- answer to a question that already has one.
--
-- What makes this different is that somebody asked. The claim goes back to
-- `testable` through 007's own `supported -> testable` arm -- runtime, no
-- Receipt, already in `transition_rules` since 007 -- and the replay that
-- follows settles it again exactly as the first one did. Nothing here weakens
-- 035: the reproduction is a full replay, through the door, under the Lane, and
-- if it does not hold this time the claim does not come back to `supported` and
-- the packet is refused. That is criterion 6's missing holding replay, and it
-- is the same sentence whether the run refuted the claim or never happened.
--
-- The window between this verb and the replay's close is a Finding on a claim
-- that is not `supported`, which 036's `finding_claim_not_supported` reports and
-- is meant to: "034 can reopen a claim, and a Finding on a reopened claim is
-- exactly what an operator should be looking at". It is not narrowed here. The
-- runtime holds the window inside one command, and an operator who sees it has
-- seen something true.
CREATE FUNCTION reopen_for_reproduction(p_program uuid, p_finding uuid) RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    v_finding    findings%ROWTYPE;
    v_hypothesis hypotheses%ROWTYPE;
    v_test       tests%ROWTYPE;
    v_state      text;
BEGIN
    SELECT * INTO v_finding FROM findings
     WHERE id = p_finding AND program_id = p_program;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('outcome', 'refused',
                                  'refusal', 'no Finding ' || p_finding::text
                                             || ' in this Program');
    END IF;
    IF v_finding.status <> 'candidate' THEN
        RETURN jsonb_build_object('outcome', 'refused', 'finding', v_finding.label,
                                  'refusal', v_finding.label || ' is '
                                             || v_finding.status
                                             || ' and only a candidate is reproduced');
    END IF;

    SELECT state INTO v_state FROM validation_queue
     WHERE finding_id = p_finding AND program_id = p_program;
    IF v_state IS DISTINCT FROM 'queued' THEN
        RETURN jsonb_build_object(
            'outcome', 'refused', 'finding', v_finding.label,
            'refusal', 'nothing asked for ' || v_finding.label
                       || ' to be validated');
    END IF;

    -- `ORDER BY h.label LIMIT 1` and not "the one claim", because 036 merges a
    -- second claim onto an occupied cell and `finding_hypotheses` is many to
    -- many from that day. It is the same claim `rk2_validation_packet` shows,
    -- chosen by the same rule: reopening one claim and serving another would be
    -- a reproduction of a Test nobody was shown.
    SELECT h.* INTO v_hypothesis FROM hypotheses h
      JOIN finding_hypotheses fh ON fh.hypothesis_id = h.id
                               AND fh.program_id = h.program_id
     WHERE fh.finding_id = p_finding AND h.program_id = p_program
     ORDER BY h.label
     LIMIT 1
       FOR UPDATE OF h;
    SELECT t.* INTO v_test FROM tests t
      JOIN test_runs tr ON tr.test_id = t.id AND tr.program_id = t.program_id
     WHERE tr.id = v_finding.opened_by_test_run_id AND t.program_id = p_program;

    -- Already testable, or already being tested: the reproduction the caller
    -- wanted is either about to happen or happening, and moving the claim again
    -- would be a second answer to that. Reported rather than refused, because
    -- what the caller asked for is true.
    IF v_hypothesis.status IN ('testable', 'testing') THEN
        RETURN jsonb_build_object('outcome', 'reopened', 'finding', v_finding.label,
                                  'hypothesis', v_hypothesis.label,
                                  'hypothesis_status', v_hypothesis.status,
                                  'test', v_test.label, 'test_id', v_test.id);
    END IF;
    IF v_hypothesis.status <> 'supported' THEN
        RETURN jsonb_build_object(
            'outcome', 'refused', 'finding', v_finding.label,
            'refusal', v_hypothesis.label || ' is ' || v_hypothesis.status
                       || ' and a Finding is reproduced from a supported claim');
    END IF;

    INSERT INTO hypothesis_transitions
        (program_id, hypothesis_id, from_status, to_status, actor_kind, rationale)
    VALUES (p_program, v_hypothesis.id, 'supported', 'testable', 'runtime',
            'reopened to reproduce ' || v_finding.label || ' for validation');

    RETURN jsonb_build_object('outcome', 'reopened', 'finding', v_finding.label,
                              'hypothesis', v_hypothesis.label,
                              'hypothesis_status', 'testable',
                              'test', v_test.label, 'test_id', v_test.id);
END $fn$;

COMMENT ON FUNCTION reopen_for_reproduction(uuid, uuid) IS
    'Put a candidate Finding''s claim back where 035 can replay it, so the '
    'validator is offered a second run rather than the one the Finding was '
    'born from. Refuses unless a validation was asked for.';

REVOKE ALL ON FUNCTION reopen_for_reproduction(uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reopen_for_reproduction(uuid, uuid) TO rk2_runtime;

-- The session the packet is served to, and why it is opened here rather than
-- claimed. 018 gives the validator `task_kinds = {validate}`, and 019 derives
-- `roles.executes_tasks` from that: an `agent_runs` row for a validator without
-- a `task_id` fails `agent_runs_executes_tasks_fk`. So a Task there must be.
--
-- It is not the scheduler's Task. `claim_task` picks off a slate against
-- `claimable_for`, which asks for a ranked cost, a lane with headroom and a
-- role the hunting loop can start -- and the loop that consumes a claim is
-- 018's execution slice, which refuses any role holding no `net.request`. A
-- `validate` Task on the queue would therefore be offered, claimed, refused and
-- returned, spending an attempt each pass. The validation of one Finding is not
-- work the ranking chooses between; it is what the runtime does next about a
-- Finding somebody already asked to have validated, so the request lives in
-- `validation_queue` where 011 put it and this verb is what acts on it.
--
-- What is kept from `claim_task`, because those parts are not the scheduler's
-- taste but the Program's arithmetic: the attempt is counted, the lease is the
-- weights row's, and the worst case is reserved out of `program_capacity`
-- before a token is spent.
CREATE FUNCTION open_validation_session(
    p_program uuid,
    p_finding uuid,
    p_replay  uuid
) RETURNS jsonb LANGUAGE plpgsql AS $fn$
DECLARE
    w        scheduler_weights%ROWTYPE;
    v_task   tasks%ROWTYPE;
    v_label  text;
    v_cap    smallint;
    v_model  text;
    v_effort text;
    v_reason text;
    v_run    uuid;
    v_run_label text;
    v_tokens bigint;
    v_opened jsonb;
BEGIN
    SELECT * INTO w FROM scheduler_weights WHERE active;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'no active scheduler_weights row' USING ERRCODE = 'check_violation';
    END IF;

    -- Two locks, in this order everywhere. The Program's is `claim_task`'s own
    -- key and is what the count below needs: a cap read under a per-Finding
    -- lock is a cap two validations of two Findings both pass. The Finding's is
    -- the one `open_validation` takes, taken here so the pre-flight and the
    -- open it guards are one decision -- `pg_advisory_xact_lock` is re-entrant
    -- within a transaction, so the nested take costs nothing. Program before
    -- Finding because nothing in this schema takes them the other way round.
    PERFORM pg_advisory_xact_lock(hashtextextended(p_program::text, 0));
    PERFORM pg_advisory_xact_lock(hashtextextended(p_finding::text, 0));

    SELECT label INTO v_label FROM findings
     WHERE id = p_finding AND program_id = p_program;

    -- Asked before anything is opened, in `open_validation`'s own words rather
    -- than in a second copy of them: a packet that cannot be served is not worth
    -- a Task, a lease and an opus session, and the refusal still has to be filed
    -- exactly once. Handing it back with no agent run is what files it.
    IF rk2_validation_refusal(p_program, p_finding, p_replay) IS NOT NULL
       OR EXISTS (SELECT 1 FROM validation_attempts
                   WHERE finding_id = p_finding AND program_id = p_program
                     AND outcome = 'open') THEN
        RETURN open_validation(p_program, p_finding, p_replay, NULL);
    END IF;

    SELECT r.model, r.effort, r.max_concurrent INTO v_model, v_effort, v_cap
      FROM roles r WHERE r.role = 'validator';

    -- 018's `max_concurrent` for the role, asked where the run is opened because
    -- this path never passes `claimable_for`, and asked under the Program lock
    -- taken above because a count is only a cap while nothing else is counting.
    IF (SELECT count(*) FROM agent_runs ar
         WHERE ar.program_id = p_program AND ar.role = 'validator'
           AND ar.finished_at IS NULL) >= v_cap THEN
        RETURN jsonb_build_object(
            'outcome', 'refused', 'finding', v_label,
            'refusal', 'the roster runs ' || v_cap || ' validator session(s) at '
                       || 'a time and that many are open');
    END IF;

    -- One live `validate` Task per Finding is `tasks_live_dedup_idx`'s own rule,
    -- and re-using the row it would have refused to duplicate is how a second
    -- attempt at the same Finding spends an attempt rather than inventing a
    -- second Task the index would then reject.
    SELECT * INTO v_task FROM tasks
     WHERE program_id = p_program AND kind = 'validate' AND finding_id = p_finding
       AND status IN ('pending','claimed','running','parked')
     FOR UPDATE;
    IF NOT FOUND THEN
        INSERT INTO tasks (program_id, kind, finding_id, status)
             VALUES (p_program, 'validate', p_finding, 'pending')
          RETURNING * INTO v_task;
    ELSIF v_task.status <> 'pending' THEN
        RETURN jsonb_build_object(
            'outcome', 'refused', 'finding', v_label,
            'refusal', 'the validation task ' || v_task.label || ' is '
                       || v_task.status);
    END IF;

    IF v_task.attempts >= w.max_attempts THEN
        UPDATE tasks SET status = 'abandoned', abandoned_reason = 'attempts_exhausted',
                         finished_at = now(), priority = NULL
         WHERE id = v_task.id;
        RETURN jsonb_build_object(
            'outcome', 'refused', 'finding', v_label,
            'refusal', v_task.label || ' has spent its ' || w.max_attempts
                       || ' attempt(s)');
    END IF;

    -- 023's promise, asked of this Task the way it is asked of every other one.
    v_reason := budget_refusal_for(v_task);
    IF v_reason IS NOT NULL THEN
        RETURN jsonb_build_object('outcome', 'refused', 'finding', v_label,
                                  'refusal', 'validating ' || v_label || ' is '
                                             || v_reason);
    END IF;

    UPDATE tasks
       SET status = 'claimed', attempts = attempts + 1, claimed_at = now(),
           lease_expires_at = now() + w.lease_ttl
     WHERE id = v_task.id;

    INSERT INTO agent_runs (program_id, task_id, role, model, effort, mission_packet)
         VALUES (p_program, v_task.id, 'validator', v_model, v_effort, '{}')
      RETURNING id, label INTO v_run, v_run_label;

    INSERT INTO budget_reservations (program_id, agent_run_id, task_id, kind,
                                     tokens, requests)
    SELECT p_program, v_run, v_task.id, v_task.kind, c.run_tokens, c.run_requests
      FROM program_capacity c WHERE c.program_id = p_program
    RETURNING tokens INTO v_tokens;

    v_opened := open_validation(p_program, p_finding, p_replay, v_run);
    -- The ceiling handed back is the number that was just reserved and not a
    -- second reading of the Program's capacity: 026 reserves the worst case
    -- before a token is spent, and a launcher started under a different figure
    -- would be a session whose reservation does not bound it. Null where the
    -- Program is unbudgeted, which is `_launch`'s "no ceiling".
    RETURN v_opened || jsonb_build_object('task', v_task.label,
                                          'agent_run', v_run_label,
                                          'agent_run_id', v_run,
                                          'token_cap', v_tokens);
END $fn$;

COMMENT ON FUNCTION open_validation_session(uuid, uuid, uuid) IS
    'Open the Task and the top-level validator run one packet is served to, and '
    'serve it. The session exists because 019 will not let a validator run '
    'without a Task; it is not on a slate because the ranking does not choose '
    'whether a Finding somebody asked about gets looked at.';

REVOKE ALL ON FUNCTION open_validation_session(uuid, uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION open_validation_session(uuid, uuid, uuid) TO rk2_runtime;

-- 012 asks one question of a Task before it may close as done -- "did the
-- runtime accept a structured result of it" -- and answers it in two places
-- with the same `EXISTS` over promoted proposals: the trigger that refuses the
-- write and the verb that makes it. A validator produces no proposal. Its
-- structured result is the verdict `record_verdict` filed against the attempt
-- its run opened, so the question grows a second arm and stops being asked
-- twice, because a rule spelled in two functions is a rule the next arm is
-- added to only one of.
--
-- `refused` is not an arm: a packet that could not be served is a Task that did
-- not happen, and it goes back to the queue with its attempt spent like any
-- other failure. `stale` is one: the validator answered, the runtime declined
-- to act on an answer about a packet that had changed, and asking the same
-- session the same question again would serve the same changed packet.
CREATE FUNCTION task_result_accepted(p_task uuid) RETURNS boolean
LANGUAGE sql STABLE AS $fn$
    SELECT EXISTS (SELECT 1 FROM proposals pr
                    WHERE pr.task_id = p_task AND pr.status = 'promoted')
        OR EXISTS (SELECT 1 FROM validation_attempts va
                     JOIN agent_runs ar ON ar.id = va.agent_run_id
                    WHERE ar.task_id = p_task
                      AND va.outcome IN ('answered', 'stale'))
$fn$;

COMMENT ON FUNCTION task_result_accepted(uuid) IS
    'Whether the runtime has accepted a structured result of this Task: a '
    'promoted proposal, or an answered validation. The one place 012''s '
    'completion question is asked.';

REVOKE ALL ON FUNCTION task_result_accepted(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION task_result_accepted(uuid) TO rk2_runtime;

CREATE OR REPLACE FUNCTION enforce_task_completion() RETURNS trigger
LANGUAGE plpgsql AS $fn$
BEGIN
    IF NEW.status = 'done' AND OLD.status IS DISTINCT FROM 'done'
       AND NOT task_result_accepted(NEW.id) THEN
        RAISE EXCEPTION
            'task % cannot be closed as done: no result of it has been accepted',
            NEW.label
          USING DETAIL = 'an agent''s completion claim is staging data; the runtime '
                         'accepting a structured result is what closes a task',
                ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END $fn$;

-- And the third place, which is the reason the question was worth naming: 020's
-- standing check asks it too, of every `done` Task at once. Left as it was it
-- would report every validation this ticket closes as a leak -- a check that
-- cries about the rule the trigger beside it permits, which is worse than no
-- check, because the operator learns to read past it.
CREATE OR REPLACE FUNCTION check_execution_closure()
RETURNS TABLE (problem text, subject text, detail text)
LANGUAGE sql STABLE AS $fn$
    SELECT 'task_done_without_promotion', t.label,
           'closed as done and no result of it has been accepted'
      FROM tasks t
     WHERE t.status = 'done' AND NOT task_result_accepted(t.id)

  UNION ALL
    SELECT 'live_capability_after_close', tr.label,
           'status=' || tr.status || ' and a capability digest is still installed'
      FROM tool_runs tr
     WHERE tr.status <> 'running' AND tr.egress_token_sha256 IS NOT NULL

  UNION ALL
    SELECT 'open_tool_run_of_closed_agent_run', tr.label,
           'still running inside agent run ' || ar.label || ', which finished'
      FROM tool_runs tr JOIN agent_runs ar ON ar.id = tr.agent_run_id
     WHERE tr.status = 'running' AND ar.finished_at IS NOT NULL

  UNION ALL
    SELECT 'unreleased_lease_of_closed_agent_run', l.identity_entity_id::text,
           'held by agent run ' || ar.label || ', which finished'
      FROM identity_leases l JOIN agent_runs ar ON ar.id = l.holder_agent_run_id
     WHERE l.released_at IS NULL AND ar.finished_at IS NOT NULL

  UNION ALL
    SELECT 'open_agent_run_on_settled_task', ar.label,
           'unfinished on task ' || t.label || ', which is ' || t.status
      FROM agent_runs ar JOIN tasks t ON t.id = ar.task_id
     WHERE ar.finished_at IS NULL AND t.status IN ('done','failed','abandoned')

  UNION ALL
    SELECT 'completion_guard_detached', 'tasks',
           'tasks_completion_needs_promotion is missing or not ENABLE ALWAYS'
     WHERE NOT EXISTS (
        SELECT 1 FROM pg_trigger
         WHERE tgrelid = 'tasks'::regclass
           AND tgname = 'tasks_completion_needs_promotion'
           AND tgenabled = 'A')

  UNION ALL
    SELECT 'promotion_writes_no_event', 'observations',
           'observations is not a row-event table, so a promoted Observation '
           'could commit without the Event that records it'
     WHERE NOT EXISTS (
        SELECT 1 FROM event_table_config
         WHERE table_name = 'observations' AND created_type = 'observation.recorded')
$fn$;

COMMENT ON FUNCTION check_execution_closure() IS
    'The five leaks a Task attempt can spring, as rows, plus the two structures '
    'that keep the first of them empty by construction. The first leak is asked '
    'through task_result_accepted, so it permits exactly what the trigger does.';

UPDATE standing_checks
   SET note = 'a finished attempt leaves no live capability, no open Tool run, '
              'no open Agent run and no held Lease, and a Task is done only '
              'where the runtime accepted a result of it'
 WHERE name = 'execution_closure';

CREATE OR REPLACE FUNCTION finish_task_attempt(
    p_agent_run     uuid,
    p_stop_reason   text DEFAULT 'completed',
    p_input_tokens  bigint DEFAULT NULL,
    p_output_tokens bigint DEFAULT NULL
) RETURNS jsonb LANGUAGE plpgsql AS $fn$
DECLARE
    p         uuid := rk2_program_required();
    w         scheduler_weights%ROWTYPE;
    v_run     agent_runs%ROWTYPE;
    v_task    tasks%ROWTYPE;
    v_accepted boolean;
    v_status  text;
    n_tool    bigint := 0;
    n_lease   bigint := 0;
    n_run     bigint := 0;
BEGIN
    SELECT * INTO w FROM scheduler_weights WHERE active;
    IF NOT FOUND THEN RAISE EXCEPTION 'no active scheduler_weights row'; END IF;

    SELECT * INTO v_run FROM agent_runs
     WHERE id = p_agent_run AND program_id = p FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'agent run % is not this Program''s', p_agent_run
            USING ERRCODE = 'check_violation';
    END IF;

    PERFORM set_actor('runtime', 'rk run');
    PERFORM set_cause(v_run.id, v_run.task_id);

    UPDATE tool_runs SET status = 'error', finished_at = now()
     WHERE program_id = p AND agent_run_id = v_run.id AND status = 'running';
    GET DIAGNOSTICS n_tool = ROW_COUNT;

    UPDATE agent_runs
       SET finished_at   = now(),
           stop_reason   = p_stop_reason,
           input_tokens  = coalesce(p_input_tokens,  input_tokens),
           output_tokens = coalesce(p_output_tokens, output_tokens)
     WHERE id = v_run.id AND finished_at IS NULL;
    GET DIAGNOSTICS n_run = ROW_COUNT;

    n_lease := (release_leases(v_run.id) ->> 'identity_leases')::bigint;

    IF v_run.task_id IS NULL THEN
        RETURN jsonb_build_object('agent_run', v_run.label, 'task', NULL,
                                  'task_status', NULL, 'runs_closed', n_run,
                                  'tool_runs_closed', n_tool, 'leases_released', n_lease);
    END IF;

    SELECT * INTO v_task FROM tasks WHERE id = v_run.task_id FOR UPDATE;
    v_accepted := task_result_accepted(v_task.id);

    IF v_task.status IN ('done','failed','abandoned') THEN
        -- Already settled. Not re-settled and not re-counted: a second call is
        -- a repeat of one attempt, not a second attempt.
        v_status := v_task.status;
    ELSIF v_accepted THEN
        v_status := 'done';
        UPDATE tasks SET status = 'done', finished_at = now(), priority = NULL
         WHERE id = v_task.id;
    ELSIF v_task.attempts >= w.max_attempts THEN
        v_status := 'abandoned';
        UPDATE tasks SET status = 'abandoned', abandoned_reason = 'attempts_exhausted',
                         finished_at = now(), priority = NULL
         WHERE id = v_task.id;
    ELSE
        -- Back to the queue with the attempt spent. The attempt is spent
        -- because it happened: `claim_task` counted it, a child ran, and a
        -- runtime that gave it back would loop on a task that fails the same
        -- way every time.
        v_status := 'pending';
        UPDATE tasks SET status = 'pending', claimed_at = NULL, priority = NULL
         WHERE id = v_task.id;
    END IF;

    RETURN jsonb_build_object('agent_run', v_run.label, 'task', v_task.label,
                              'task_status', v_status, 'accepted', v_accepted,
                              'runs_closed', n_run, 'tool_runs_closed', n_tool,
                              'leases_released', n_lease);
END $fn$;


-- ---------------------------------------------------------------------------
-- 6. The verdict as input
-- ---------------------------------------------------------------------------
-- Criterion 5's first half. A verdict row is what a session said, and saying it
-- is all it does: the row names no status, sets no column on the Finding and
-- has no way to. What it is checked for here is that it is an answer to a
-- question that was asked -- an attempt open, a Finding under judgement -- and
-- that the assertions it names are assertions the Test states. An identifier
-- the Test does not have is criterion 6's smuggled field in its one remaining
-- form: the roster closes the argument's shape, and this closes its vocabulary.

-- Asked in two places and written once, because the two places answer it
-- differently and both answers are needed. `record_verdict` asks it to refuse a
-- session's answer with a sentence, which is the only way a validator that
-- named an assertion nobody stated can be told so; the trigger asks it to
-- refuse a row, which is what still holds when the next writer is not
-- `record_verdict`.
CREATE FUNCTION rk2_unstated_assertion(p_program uuid, p_finding uuid, p_named text[])
RETURNS text LANGUAGE sql STABLE AS $fn$
    SELECT named
      FROM unnest(p_named) AS named
     WHERE NOT EXISTS (
        SELECT 1
          FROM findings f
          JOIN test_runs run ON run.id = f.opened_by_test_run_id
                            AND run.program_id = f.program_id
          JOIN tests t ON t.id = run.test_id AND t.program_id = run.program_id
          CROSS JOIN LATERAL jsonb_array_elements(t.spec -> 'assertions') a
         WHERE f.id = p_finding AND f.program_id = p_program
           AND a ->> 'id' = named)
     ORDER BY named
     LIMIT 1
$fn$;

COMMENT ON FUNCTION rk2_unstated_assertion(uuid, uuid, text[]) IS
    'The first assertion identifier in the list that this Finding''s Test does '
    'not state, or null. Criterion 6''s smuggled field in its last form: the '
    'roster closes the argument''s shape and this closes its vocabulary.';

REVOKE ALL ON FUNCTION rk2_unstated_assertion(uuid, uuid, text[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rk2_unstated_assertion(uuid, uuid, text[]) TO rk2_runtime;

CREATE FUNCTION enforce_verdict_input() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE
    v_status  text;
    v_unknown text;
BEGIN
    SELECT status INTO v_status FROM findings
     WHERE id = NEW.finding_id AND program_id = NEW.program_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'no Finding % in this Program', NEW.finding_id;
    END IF;
    IF v_status <> 'validating' THEN
        RAISE EXCEPTION 'a verdict answers a Finding under judgement; % is %',
            NEW.finding_id, v_status;
    END IF;

    PERFORM 1 FROM validation_attempts
     WHERE finding_id = NEW.finding_id AND program_id = NEW.program_id
       AND outcome = 'open';
    IF NOT FOUND THEN
        RAISE EXCEPTION 'no validation of % was opened for a verdict to answer',
            NEW.finding_id;
    END IF;

    v_unknown := rk2_unstated_assertion(NEW.program_id, NEW.finding_id,
                                        NEW.failed_assertion_ids);
    IF v_unknown IS NOT NULL THEN
        RAISE EXCEPTION 'the assertion % is not one this Finding''s Test states',
            v_unknown;
    END IF;

    -- A confirmation that names failures is two answers. The validator has a
    -- word for "it reproduced but not entirely" and the word is `insufficient`.
    IF NEW.verdict = 'confirmed' AND cardinality(NEW.failed_assertion_ids) > 0 THEN
        RAISE EXCEPTION 'a confirmed verdict names no failed assertion';
    END IF;

    RETURN NEW;
END $fn$;

COMMENT ON FUNCTION enforce_verdict_input() IS
    'What a verdict row has to be an answer to: a Finding under judgement, an '
    'attempt that was opened, assertions the Test states, and -- for a '
    'confirmation -- no failure at all.';

CREATE TRIGGER verdicts_answer_a_question
    BEFORE INSERT ON verdicts
    FOR EACH ROW EXECUTE FUNCTION enforce_verdict_input();

-- 011 granted nothing on this table. A verdict is written by the runtime on the
-- session's behalf -- the child has no database, so `submit_verdict` latches an
-- answer in the launcher and the runtime files it here.
GRANT SELECT, INSERT ON verdicts TO rk2_runtime;
GRANT SELECT ON verdicts TO rk2_human;

CREATE TRIGGER verdicts_immutable
    BEFORE UPDATE OR DELETE ON verdicts
    FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_purging();


-- ---------------------------------------------------------------------------
-- 7. And the transition the database decides
-- ---------------------------------------------------------------------------
-- Criterion 5's second half, and the reason the two halves are in different
-- sections: nothing above this comment can move a Finding, and nothing below it
-- reads what a model said except as a row that was already checked.
--
-- 007 gave the machine four arms and 011 left one missing. `insufficient` is a
-- verdict that destroys nothing -- the spec asks for exactly that, "failed
-- assertions and insufficient evidence recorded without destroying the
-- candidate" -- and with no arm back to `candidate` the only two ways out of
-- `validating` would have been validated and rejected. So a session that
-- honestly says it cannot tell would have had to be read as one of the two
-- things it did not say.

INSERT INTO transition_rules
    (machine, from_status, to_status, required_actor_kind,
     requires_receipt, min_supporting_evidence, min_control_evidence)
VALUES ('finding', 'validating', 'candidate', 'runtime', false, 0, 0);

COMMENT ON TABLE transition_rules IS
    'The state machines of a Hypothesis and of a Finding, as rows. A transition '
    'with no row here is illegal by absence rather than by a list of refusals.';

-- The map from what a session said to what the Finding becomes, in one place
-- for the reason `task_result_accepted` is in one place: `record_verdict` reads
-- it to write the transition and `enforce_finding_validation` reads it to
-- refuse any other, and a fourth verdict added to a map spelled twice is a
-- fourth verdict the guard does not know about.
CREATE FUNCTION rk2_verdict_status(p_verdict text) RETURNS text
LANGUAGE sql IMMUTABLE AS $fn$
    SELECT CASE p_verdict WHEN 'confirmed'    THEN 'validated'
                          WHEN 'refuted'      THEN 'rejected'
                          WHEN 'insufficient' THEN 'candidate' END
$fn$;

COMMENT ON FUNCTION rk2_verdict_status(text) IS
    'What one of 011''s three words makes a Finding. The whole of criterion '
    '5''s arithmetic, and the only copy of it.';

REVOKE ALL ON FUNCTION rk2_verdict_status(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rk2_verdict_status(text) TO rk2_runtime, rk2_human;

CREATE FUNCTION enforce_finding_validation() RETURNS trigger
LANGUAGE plpgsql AS $fn$
DECLARE
    v_finding findings%ROWTYPE;
    v_attempt validation_attempts%ROWTYPE;
    v_verdict text;
    v_wanted  text;
BEGIN
    IF NEW.from_status <> 'validating' THEN
        RETURN NEW;
    END IF;

    SELECT * INTO v_finding FROM findings
     WHERE id = NEW.finding_id AND program_id = NEW.program_id;
    -- The latest attempt whatever became of it, not the open one, because two
    -- of the three ways out of judgement are that the attempt stopped being
    -- open: a packet that no longer reads the same way is closed `stale` first,
    -- and a session that said nothing is closed `unanswered`. Both leave the
    -- Finding a candidate again with nothing having been decided about it.
    SELECT * INTO v_attempt FROM validation_attempts
     WHERE finding_id = NEW.finding_id AND program_id = v_finding.program_id
       AND outcome <> 'refused'
     ORDER BY opened_at DESC, id DESC
     LIMIT 1;
    IF NOT FOUND THEN
        RAISE EXCEPTION
            'the Finding % leaves judgement through a validation that was opened',
            v_finding.label;
    END IF;

    IF v_attempt.outcome IN ('stale', 'unanswered') THEN
        IF NEW.to_status <> 'candidate' THEN
            RAISE EXCEPTION
                'the validation of % ended %; it goes back to candidate, not to %',
                v_finding.label, v_attempt.outcome, NEW.to_status;
        END IF;
        RETURN NEW;
    END IF;

    SELECT verdict INTO v_verdict FROM verdicts
     WHERE finding_id = NEW.finding_id AND program_id = v_finding.program_id
       AND created_at >= v_attempt.opened_at
     ORDER BY created_at DESC, id DESC
     LIMIT 1;
    IF v_verdict IS NULL THEN
        RAISE EXCEPTION 'no verdict was given on the Finding %', v_finding.label;
    END IF;

    v_wanted := rk2_verdict_status(v_verdict);
    IF NEW.to_status <> v_wanted THEN
        RAISE EXCEPTION 'the verdict on % is %, which makes it %, not %',
            v_finding.label, v_verdict, v_wanted, NEW.to_status;
    END IF;

    IF NEW.to_status <> 'validated' THEN
        RETURN NEW;
    END IF;

    -- The rest is what `validated` means beyond the word. 015's MATCH FULL key
    -- already pins the run to one whose outcome is `holds`; what it cannot say
    -- is which run, and a Finding pointed at some other holding run of some
    -- other claim would satisfy it. So: the run this validation was opened
    -- against, and nothing else.
    IF v_finding.validated_by_test_run_id IS DISTINCT FROM v_attempt.replay_test_run_id THEN
        RAISE EXCEPTION
            'the Finding % is validated by the run its validation was opened '
            'against, not by %',
            v_finding.label, coalesce(v_finding.validated_by_test_run_id::text, 'nothing');
    END IF;
    RETURN NEW;
END $fn$;

COMMENT ON FUNCTION enforce_finding_validation() IS
    'Criterion 5. What a Finding leaving judgement has to be able to point at: '
    'an open validation, a verdict given after it was served, the status that '
    'verdict implies and no other, and for `validated` the exact reproduction '
    'the validation was opened against.';

-- Fires before `finding_transition_guard`, which is what the alphabet gives us
-- and what is wanted either way: the guard is the one that writes the new
-- status onto `findings`, and every question here is about the row as it stands
-- now. Named to say so rather than relying on a reader noticing the ordering.
CREATE TRIGGER a_finding_leaves_judgement_on_a_verdict
    BEFORE INSERT ON finding_transitions
    FOR EACH ROW EXECUTE FUNCTION enforce_finding_validation();

CREATE FUNCTION record_verdict(
    p_program uuid,
    p_finding uuid,
    p_verdict text,
    p_failed  text[] DEFAULT '{}'
) RETURNS jsonb LANGUAGE plpgsql AS $fn$
DECLARE
    v_attempt  validation_attempts%ROWTYPE;
    v_finding  findings%ROWTYPE;
    v_digest   text;
    v_id       uuid;
    v_to       text;
    v_receipt  uuid;
    v_unstated text;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_finding::text, 0));

    SELECT * INTO v_finding FROM findings
     WHERE id = p_finding AND program_id = p_program FOR UPDATE;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('outcome', 'refused',
                                  'refusal', 'no Finding ' || p_finding::text
                                             || ' in this Program');
    END IF;

    SELECT * INTO v_attempt FROM validation_attempts
     WHERE finding_id = p_finding AND program_id = p_program AND outcome = 'open'
       FOR UPDATE;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('outcome', 'refused', 'finding', v_finding.label,
                                  'refusal', 'no validation of ' || v_finding.label
                                             || ' is in flight');
    END IF;

    -- A word outside the three, refused before anything is written. 011's CHECK
    -- would refuse it too, by raising -- and this verb's whole shape is that a
    -- bad answer closes the attempt instead of taking it down with it.
    IF rk2_verdict_status(p_verdict) IS NULL THEN
        RETURN jsonb_build_object('outcome', 'refused', 'finding', v_finding.label,
                                  'verdict', p_verdict,
                                  'refusal', p_verdict || ' is not one of '
                                             || 'confirmed, refuted or insufficient');
    END IF;

    -- Criterion 6, and the one arm that catches everything the arms above
    -- cannot enumerate. The session judged a document; if the document would
    -- now read differently -- an Artifact purged, a Receipt gone, the claim
    -- reopened, a second run arrived -- then what it judged is not what is
    -- there, and the honest thing to do with the answer is to keep it and not
    -- act on it.
    --
    -- Kept on the attempt and not in `verdicts`, which is the difference
    -- between recording what a session said and asserting a judgement about
    -- this Finding. The row in `verdicts` would be an answer about a document
    -- that no longer exists: `check_validations` would read its assertion
    -- identifiers against a Test that has moved, and an operator counting
    -- verdicts would count one nothing was decided by. The attempt is where
    -- "what became of this reading" belongs, and it names the word.
    v_digest := rk2_validation_digest(
        rk2_validation_packet(p_program, p_finding, v_attempt.replay_test_run_id));
    IF v_digest IS DISTINCT FROM v_attempt.packet_sha256 THEN
        UPDATE validation_attempts
           SET outcome = 'stale', closed_at = now(),
               refusal = 'answered ' || p_verdict || ' on a packet that had '
                         || 'changed since it was served'
         WHERE id = v_attempt.id;
        UPDATE validation_queue SET state = 'done'
         WHERE finding_id = p_finding AND program_id = p_program;
        INSERT INTO finding_transitions (program_id, finding_id, from_status,
                                         to_status, actor_kind, rationale)
             VALUES (p_program, p_finding, 'validating', 'candidate', 'runtime',
                     'the evidence moved while it was being judged');
        RETURN jsonb_build_object('outcome', 'stale', 'finding', v_finding.label,
                                  'attempt', v_attempt.id, 'verdict', p_verdict,
                                  'served', v_attempt.packet_sha256,
                                  'now', v_digest);
    END IF;

    -- Asked here as well as by the trigger, because the two of them fail
    -- differently and only one of those failures is survivable. A child chooses
    -- the identifiers it names and the roster only closes their shape, so an
    -- invented one is an ordinary answer arriving through the front door -- and
    -- a raised exception here takes down the transaction that would have closed
    -- the attempt, leaving a Finding under judgement by a session that has
    -- already stopped and that `open_validation` will refuse to replace. The
    -- trigger stays: it is what still holds when the writer is not this verb.
    v_unstated := rk2_unstated_assertion(p_program, p_finding, coalesce(p_failed, '{}'));
    IF v_unstated IS NOT NULL THEN
        RETURN jsonb_build_object('outcome', 'refused', 'finding', v_finding.label,
                                  'verdict', p_verdict,
                                  'refusal', 'the assertion ' || v_unstated
                                             || ' is not one ' || v_finding.label
                                             || '''s Test states');
    END IF;
    IF p_verdict = 'confirmed' AND cardinality(coalesce(p_failed, '{}')) > 0 THEN
        RETURN jsonb_build_object('outcome', 'refused', 'finding', v_finding.label,
                                  'verdict', p_verdict,
                                  'refusal', 'a confirmed verdict names no '
                                             || 'failed assertion');
    END IF;

    INSERT INTO verdicts (program_id, finding_id, verdict, failed_assertion_ids)
         VALUES (p_program, p_finding, p_verdict, coalesce(p_failed, '{}'))
      RETURNING id INTO v_id;

    v_to := rk2_verdict_status(p_verdict);

    -- Written before the transition and not after it, because the transition is
    -- what reads it: `enforce_finding_validation` asks whether the Finding
    -- points at the run this validation was opened against, and the MATCH FULL
    -- key refuses the pair outright if that run did not hold. A `confirmed`
    -- verdict on a reproduction that failed stops here, with the verdict on
    -- file and the Finding unmoved.
    IF v_to = 'validated' THEN
        UPDATE findings
           SET validated_by_test_run_id = v_attempt.replay_test_run_id,
               validated_run_outcome    = 'holds'
         WHERE id = p_finding AND program_id = p_program;

        -- 007 wants the transition to cite a Receipt the reproducing run
        -- produced, and the run's first exchange is the one that is always
        -- there: 035 will not conclude a run that made none. Which of them it
        -- is does not change what the citation says, so it is chosen the one
        -- way that is the same on every re-run.
        SELECT trr.receipt_id INTO v_receipt
          FROM test_run_receipts trr
         WHERE trr.test_run_id = v_attempt.replay_test_run_id
           AND trr.program_id = p_program
         ORDER BY trr.ordinal
         LIMIT 1;
    END IF;

    INSERT INTO finding_transitions (program_id, finding_id, from_status,
                                     to_status, actor_kind, agent_run_id,
                                     receipt_id, rationale)
         VALUES (p_program, p_finding, 'validating', v_to, 'runtime',
                 v_attempt.agent_run_id, v_receipt,
                 'a blind validator answered ' || p_verdict);

    UPDATE validation_attempts
       SET outcome = 'answered', verdict_id = v_id, closed_at = now()
     WHERE id = v_attempt.id;

    UPDATE validation_queue SET state = 'done'
     WHERE finding_id = p_finding AND program_id = p_program;

    RETURN jsonb_build_object('outcome', 'answered', 'finding', v_finding.label,
                              'attempt', v_attempt.id, 'verdict', p_verdict,
                              'status', v_to, 'failed', coalesce(p_failed, '{}'));
END $fn$;

COMMENT ON FUNCTION record_verdict(uuid, uuid, text, text[]) IS
    'File what one blind validator answered and let the rules decide what the '
    'Finding becomes. Refuses to act on a verdict about a packet that would no '
    'longer read the same way, which is criterion 6''s changed Artifact in the '
    'general case.';

REVOKE ALL ON FUNCTION record_verdict(uuid, uuid, text, text[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION record_verdict(uuid, uuid, text, text[]) TO rk2_runtime;

-- The third way out, and the one nobody chooses. A session can end without
-- answering -- it runs out of turns, it is refused at startup, the supervisor
-- dies -- and the Finding is left saying it is under judgement by a session
-- that no longer exists. Left there it is worse than a wrong verdict: the open
-- attempt makes `open_validation` refuse the next one, so a Finding whose
-- validator crashed can never be validated again.
--
-- The attempt keeps its packet digest and its run. That is the difference from
-- `refused` and the reason for a fifth word: a reproduction was performed and
-- an opus session was spent, and an outcome that said "nothing happened" would
-- make that invisible to the only table that records it.
CREATE FUNCTION abandon_validation(p_program uuid, p_finding uuid, p_reason text)
RETURNS jsonb LANGUAGE plpgsql AS $fn$
DECLARE
    v_finding findings%ROWTYPE;
    v_attempt validation_attempts%ROWTYPE;
BEGIN
    PERFORM pg_advisory_xact_lock(hashtextextended(p_finding::text, 0));

    SELECT * INTO v_finding FROM findings
     WHERE id = p_finding AND program_id = p_program FOR UPDATE;
    IF NOT FOUND THEN
        RETURN jsonb_build_object('outcome', 'refused',
                                  'refusal', 'no Finding ' || p_finding::text
                                             || ' in this Program');
    END IF;

    SELECT * INTO v_attempt FROM validation_attempts
     WHERE finding_id = p_finding AND program_id = p_program AND outcome = 'open'
       FOR UPDATE;
    IF NOT FOUND THEN
        -- Not a refusal worth raising. The runtime calls this on every path out
        -- of a validation it started, and the path where the verdict was filed
        -- is the one that leaves nothing open.
        RETURN jsonb_build_object('outcome', 'nothing_open',
                                  'finding', v_finding.label);
    END IF;

    UPDATE validation_attempts
       SET outcome = 'unanswered', refusal = p_reason, closed_at = now()
     WHERE id = v_attempt.id;

    UPDATE validation_queue SET state = 'done'
     WHERE finding_id = p_finding AND program_id = p_program;

    IF v_finding.status = 'validating' THEN
        INSERT INTO finding_transitions (program_id, finding_id, from_status,
                                         to_status, actor_kind, agent_run_id,
                                         rationale)
             VALUES (p_program, p_finding, 'validating', 'candidate', 'runtime',
                     v_attempt.agent_run_id, p_reason);
    END IF;

    RETURN jsonb_build_object('outcome', 'unanswered', 'finding', v_finding.label,
                              'attempt', v_attempt.id, 'refusal', p_reason);
END $fn$;

COMMENT ON FUNCTION abandon_validation(uuid, uuid, text) IS
    'Close a validation nobody answered and give the Finding back to the '
    'candidates. The runtime calls it on every path out of a session it opened, '
    'so a crashed validator does not leave a Finding permanently under judgement.';

REVOKE ALL ON FUNCTION abandon_validation(uuid, uuid, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION abandon_validation(uuid, uuid, text) TO rk2_runtime;


-- ---------------------------------------------------------------------------
-- 8. What the model may read
-- ---------------------------------------------------------------------------
-- Nothing. There is no `state_read_surface` row in this file and that is the
-- design: the validator holds no state read at all -- the roster gives it
-- `validate.judge` and no `state.read` -- and every other role is on the wrong
-- side of the blindness. A hunter that could read `verdicts` would learn which
-- of its Findings a validator doubted, which is the feedback loop this whole
-- ticket exists to cut.
--
-- 011's `v_validation_packet` view is dropped rather than repaired. It was the
-- shape of this packet before there was a packet function: it joined the
-- validating run, which is null on every candidate, so it would have shown a
-- validator the reproduction of the validation it is being asked to perform.
-- Leaving it would leave two answers to what a validation packet is.

DROP VIEW v_validation_packet;


-- ---------------------------------------------------------------------------
-- 9. The check
-- ---------------------------------------------------------------------------

CREATE FUNCTION check_validations()
RETURNS TABLE (problem text, subject text, detail text)
LANGUAGE sql STABLE AS $fn$
    -- A validated Finding nobody judged. Every rule above is a trigger, and a
    -- later migration that disables one to backfill something leaves no other
    -- trace.
    SELECT 'validated_without_a_verdict', f.label,
           'status ' || f.status || ' and no confirmed verdict on file'
      FROM findings f
     WHERE f.status IN ('validated', 'reported')
       AND NOT EXISTS (SELECT 1 FROM verdicts v
                        WHERE v.finding_id = f.id AND v.program_id = f.program_id
                          AND v.verdict = 'confirmed')

    UNION ALL
    -- A validated Finding resting on its own birth. The refusal makes it
    -- unreachable through `open_validation`; what it looks like afterwards is a
    -- Finding that reproduced itself.
    SELECT 'validated_by_the_run_it_was_opened_from', f.label,
           'the reproduction is the run the candidate was born from'
      FROM findings f
     WHERE f.validated_by_test_run_id IS NOT NULL
       AND f.validated_by_test_run_id = f.opened_by_test_run_id

    UNION ALL
    -- A validated Finding whose reproduction is a run of another Test. The
    -- composite key pins the Program and the outcome; neither pins the Test.
    SELECT 'validated_by_another_test', f.label,
           'the reproduction is a run of a different Test'
      FROM findings f
      JOIN test_runs shown  ON shown.id  = f.validated_by_test_run_id
                            AND shown.program_id  = f.program_id
      JOIN test_runs opened ON opened.id = f.opened_by_test_run_id
                            AND opened.program_id = f.program_id
     WHERE shown.test_id <> opened.test_id

    UNION ALL
    -- A verdict naming an assertion its Test does not state. The trigger
    -- refuses it; a spec is immutable so the vocabulary cannot move under a
    -- verdict, but a Finding repointed at another run can.
    SELECT 'verdict_names_an_unknown_assertion', f.label,
           'names ' || named
      FROM verdicts v
      JOIN findings f  ON f.id = v.finding_id AND f.program_id = v.program_id
      JOIN test_runs r ON r.id = f.opened_by_test_run_id
                      AND r.program_id = f.program_id
      JOIN tests t     ON t.id = r.test_id AND t.program_id = r.program_id
      CROSS JOIN LATERAL unnest(v.failed_assertion_ids) AS named
     WHERE NOT EXISTS (
        SELECT 1 FROM jsonb_array_elements(t.spec -> 'assertions') a
         WHERE a ->> 'id' = named)

    UNION ALL
    -- An attempt still open on a Finding that is no longer being judged. The
    -- session was served a packet and the Finding moved without it: a validator
    -- that answers now answers about a decision already taken.
    SELECT 'attempt_open_on_a_settled_finding', f.label,
           'served ' || va.opened_at::date::text || ' and the Finding is ' || f.status
      FROM validation_attempts va
      JOIN findings f ON f.id = va.finding_id AND f.program_id = va.program_id
     WHERE va.outcome = 'open' AND f.status <> 'validating'

    UNION ALL
    -- And the other way: a Finding under judgement nobody is judging.
    SELECT 'finding_judged_by_nobody', f.label,
           'validating with no open attempt'
      FROM findings f
     WHERE f.status = 'validating'
       AND NOT EXISTS (SELECT 1 FROM validation_attempts va
                        WHERE va.finding_id = f.id AND va.program_id = f.program_id
                          AND va.outcome = 'open')

    UNION ALL
    -- The digest, asserted rather than commented. A later edit that served the
    -- packet without recording what it served would leave every verdict
    -- unanchored, and nothing about the rows would look wrong until an Artifact
    -- moved.
    SELECT 'record_verdict_does_not_check_the_digest', 'record_verdict',
           'a verdict is acted on without checking what was served'
      FROM pg_proc pr
     WHERE pr.pronamespace = 'public'::regnamespace AND pr.proname = 'record_verdict'
       AND pr.prosrc !~ 'rk2_validation_digest'
$fn$;

COMMENT ON FUNCTION check_validations() IS
    'What a validated Finding looks like when it was not validated through '
    '`open_validation` and `record_verdict`: no verdict, a reproduction that is '
    'its own birth run or another Test''s, a verdict naming an assertion '
    'nothing states, and a judgement nobody is on either side of.';

REVOKE ALL ON FUNCTION check_validations() FROM PUBLIC, rk2_state, rk2_proxy;
GRANT EXECUTE ON FUNCTION check_validations() TO rk2_runtime, rk2_human;

INSERT INTO standing_checks(name, query, owner_ticket, note) VALUES
    ('validations', 'SELECT * FROM check_validations()', '37',
     'every validated Finding rests on a verdict a blind session gave and on a reproduction of its own Test that is not the run it was born from, and every judgement in flight has a Finding and a session on either side of it');


-- ---------------------------------------------------------------------------
-- 10. The invariants this file must not have broken
-- ---------------------------------------------------------------------------

SELECT enforce_always_triggers();
SELECT apply_state_rls();

-- Criterion 1, enforced against the parse tree. `pg_depend` records one row per
-- column a `BEGIN ATOMIC` function reads, so this is the allowlist checked
-- rather than described: a later file that adds a column to the packet fails to
-- apply until it adds the row that permits it, and one that adds a column to
-- `findings` changes nothing here because the packet does not read it.
DO $$
DECLARE
    v_extra   text;
    v_missing text;
BEGIN
    CREATE TEMP TABLE reads_now ON COMMIT DROP AS
    SELECT c.relname AS relation, a.attname AS column_name
      FROM pg_depend d
      JOIN pg_class c     ON c.oid = d.refobjid
      JOIN pg_attribute a ON a.attrelid = d.refobjid AND a.attnum = d.refobjsubid
     WHERE d.classid = 'pg_proc'::regclass
       AND d.objid = 'rk2_validation_packet(uuid,uuid,uuid)'::regprocedure
       AND d.refclassid = 'pg_class'::regclass;

    SELECT string_agg(r.relation || '.' || r.column_name, ', ' ORDER BY 1)
      INTO v_extra
      FROM reads_now r
     WHERE NOT EXISTS (SELECT 1 FROM validation_packet_columns v
                        WHERE v.relation = r.relation
                          AND v.column_name = r.column_name);
    IF v_extra IS NOT NULL THEN
        RAISE EXCEPTION 'the validation packet reads %, which no allowlist row permits',
            v_extra;
    END IF;

    SELECT string_agg(v.relation || '.' || v.column_name, ', ' ORDER BY 1)
      INTO v_missing
      FROM validation_packet_columns v
     WHERE NOT EXISTS (SELECT 1 FROM reads_now r
                        WHERE r.relation = v.relation
                          AND r.column_name = v.column_name);
    IF v_missing IS NOT NULL THEN
        RAISE EXCEPTION 'the allowlist permits %, which the validation packet does not read',
            v_missing;
    END IF;
END $$;

-- And the same statement from the blindness side. The relations named here are
-- where a hunter's prose lives -- the proposal it made and the sentence that
-- refused it, the reasoning that settled a claim, the sessions it ran in and
-- what they carried, the questions a human was parked on -- and none of them
-- may be reachable from the packet at all. The check above would already refuse
-- a column of any of them; this one says why, so the migration that tries it
-- reads the reason rather than a list difference.
--
-- Each name is resolved before it is used. A list of relation names is a list
-- that goes quietly dead when a table is renamed or was never called that:
-- `relname IN (...)` matches nothing either way, and an arm that can only pass
-- is an arm that says nothing.
DO $$
DECLARE
    v_prose   text[] := ARRAY['proposals', 'proposal_drops', 'finding_proposals',
                              'agent_runs', 'agent_sessions',
                              'orchestrator_sessions', 'hypothesis_transitions',
                              'pending_decisions'];
    v_unknown text;
    v_leak    text;
BEGIN
    SELECT string_agg(named, ', ' ORDER BY named) INTO v_unknown
      FROM unnest(v_prose) AS named
     WHERE to_regclass(named) IS NULL;
    IF v_unknown IS NOT NULL THEN
        RAISE EXCEPTION 'the blindness check names %, which is not a relation',
            v_unknown;
    END IF;

    SELECT string_agg(DISTINCT c.relname, ', ' ORDER BY c.relname) INTO v_leak
      FROM pg_depend d
      JOIN pg_class c ON c.oid = d.refobjid
     WHERE d.classid = 'pg_proc'::regclass
       AND d.objid = 'rk2_validation_packet(uuid,uuid,uuid)'::regprocedure
       AND d.refclassid = 'pg_class'::regclass
       AND c.relname = ANY (v_prose);
    IF v_leak IS NOT NULL THEN
        RAISE EXCEPTION 'the validation packet reaches %, which is where the hunter''s reasoning is',
            v_leak;
    END IF;
END $$;
