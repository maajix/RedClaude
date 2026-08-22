-- ===========================================================================
-- 20261010T000000Z__a_hunt_files_the_test_that_would_settle_its_claim.sql
--                                                                  (ticket 141)
--
-- `tests` has two `INSERT` statements in this corpus and neither is reachable
-- from a hunt. 20260816T000000Z's `open_impact_task` takes a Finding, which is
-- downstream of the thing a Test exists to reach; 20260927T000000Z's is a
-- standing-check fixture. `open_test_replay` takes a Test that already exists,
-- so `rk test` cannot author one either, and the nineteen Contracts the roster
-- served before this file wrote no `tests` row between them.
--
-- What that costs is the whole of the epistemic loop. `testing -> supported`
-- requires a Test run; `rk2_finding_refusal` arm two refuses a claim that is not
-- `supported`; so a Program with a perfectly good testable claim cannot reach a
-- Finding by any route, and tickets 36 through 43 all rest on a row nothing
-- could write. The wiring gate does not see it: W6 asks whether a table has a
-- producer and this table has two. Whether either producer is reachable from a
-- run is a different question and no gate asks it.
--
--
-- WHY A PROPOSAL AND NOT A WRITE
-- ---------------------------------------------------------------------------
-- `tests` is in `roster.CANONICAL`, so `_check_contracts` refuses any Contract
-- naming it in `writes`, and that refusal is what decides the shape here rather
-- than something the shape has to work around. It is the same rule that decided
-- `propose_finding`: the child says which claim it believes it can settle and
-- what it would do to settle it, and the runtime -- on the `rk2_runtime`
-- connection, out of rows the runtime itself wrote -- decides whether a Test
-- comes of it and answers what it decided.
--
-- A Test specification is a program this harness will execute against somebody
-- else's system. "The agent wrote it" and "this installation stored it" have to
-- be two events with a decision between them, and `test_proposals` is where the
-- ones that did not become a Test are on the record.
--
--
-- WHY THE MODEL AND NOT THE RUNTIME
-- ---------------------------------------------------------------------------
-- Ticket 141 named a second candidate: the runtime derives a specification from
-- the Playbook the Task was selected under. That one is not available. No
-- Playbook has ever been selected in this tree (ticket 101), so a
-- derivation-only answer would ship a producer nothing exercises -- which is the
-- defect this file exists to remove, reached by a different road.
--
-- The two are not exclusive and this file is deliberately the half that both
-- would share. A derivation added later writes its rows through `propose_test`
-- like any other caller, because what decides whether a `tests` row exists is
-- this verb and not who called it.
--
--
-- ONE FUNCTION AND NOT TWO
-- ---------------------------------------------------------------------------
-- `propose_finding` is a label resolver in front of `open_finding` because
-- `open_finding` was already there, holding the corpus's only `INSERT INTO
-- findings`, with no caller. Nothing is already here. A uuid-taking half would
-- be an entry point with exactly one caller, written on the chance that
-- something later wants to author a Test without a label to name the claim by --
-- and every party that could is holding a label already.
-- ===========================================================================


-- ===========================================================================
-- 1. The record of what was proposed, beside the Tests rather than inside them
-- ===========================================================================
-- 036's `finding_proposals`, one layer earlier and for its reasons. A hunter
-- whose specification was refused learns nothing from silence, an operator
-- reading a Program with no Tests cannot tell "nothing was proposed" from
-- "everything was refused", and a table holding only the refusals is one whose
-- rate nobody can read -- so an accepted proposal writes a row too.
--
-- Beside `tests` and not inside it: nothing joins from here into a replay,
-- `test_id` is the only edge, and it is null exactly when nothing canonical came
-- of the proposal.
--
-- `spec` is stored whole, including a refused one. It is the proposal, the way
-- the class and the title are the proposal on a `finding_proposals` row, and a
-- refusal sentence about a specification nobody kept is a sentence about
-- nothing. `tests` never receives it, so no CHECK on that table has any opinion
-- about what is stored here, which is the point: this column holds the thing
-- that was refused.
CREATE TABLE test_proposals (
    id            uuid PRIMARY KEY DEFAULT uuidv7(),
    program_id    uuid NOT NULL REFERENCES programs(id) ON DELETE CASCADE,
    hypothesis_id uuid,
    agent_run_id  uuid,
    spec          jsonb NOT NULL,
    outcome       text NOT NULL CHECK (outcome IN ('created', 'existing', 'refused')),
    refusal       text,
    test_id       uuid,
    at            timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (hypothesis_id, program_id) REFERENCES hypotheses (id, program_id)
        ON DELETE CASCADE,
    FOREIGN KEY (agent_run_id, program_id)  REFERENCES agent_runs (id, program_id)
        ON DELETE CASCADE,
    FOREIGN KEY (test_id, program_id)       REFERENCES tests      (id, program_id)
        ON DELETE CASCADE,
    -- A refusal is a sentence and an outcome at once and the two may not
    -- disagree: an accepted proposal carrying a refusal would read as refused to
    -- anybody counting, and a refused one carrying none would say nothing.
    CHECK ((outcome = 'refused') = (refusal IS NOT NULL)),
    -- One direction only. A refused proposal names no Test; an accepted one
    -- always names the Test it reached, because unlike a Finding there is no
    -- later importer that could write a `tests` row this verb did not open.
    CHECK ((outcome = 'refused') = (test_id IS NULL))
);

COMMENT ON TABLE test_proposals IS
    'Ticket 141. One row per attempt to author a Test specification, accepted or '
    'not, with the specification as it was sent and the sentence that refused '
    'it. Auditable beside the canonical Tests and reachable from none of them: '
    'the edge runs the other way.';

COMMENT ON COLUMN test_proposals.spec IS
    'What was proposed, stored whether or not it became a Test. A refused '
    'specification is the only place the refusal sentence has a subject, and a '
    'stored one is what lets an operator see that four runs sent the same '
    'malformed plan rather than four different ones.';

COMMENT ON COLUMN test_proposals.test_id IS
    'The Test this proposal reached: the new row for `created`, the row this '
    'Hypothesis already held for `existing`, null when it was refused. Nothing '
    'outside a purge deletes a Test, so in practice the cascade fires once, when '
    'the Program goes and takes the proposal with it.';

COMMENT ON COLUMN test_proposals.hypothesis_id IS
    'Null when the proposal named a label this Program does not hold. The record '
    'of the attempt is filed in that case too, which is why this column takes a '
    'null: an early refusal that skipped the row would be the one refusal an '
    'operator cannot count.';

CREATE INDEX test_proposals_program_idx
    ON test_proposals (program_id, at DESC);

INSERT INTO purge_cascade_edges (table_name, column_name, rationale) VALUES
    ('test_proposals', 'program_id',    'program-scoped: the purge root'),
    ('test_proposals', 'hypothesis_id', 'ON DELETE CASCADE to hypotheses: the claim the specification would settle'),
    ('test_proposals', 'agent_run_id',  'ON DELETE CASCADE to agent_runs: the run that proposed'),
    ('test_proposals', 'test_id',       'ON DELETE CASCADE to tests: the Test the proposal reached');

-- `audit` and not `covered`, per ADR 0001 and for 036's reason: a `covered` row
-- is written in the same transaction as an emitting row that names it, and two
-- of the three outcomes here have no emitting row at all. A refusal writes the
-- proposal and returns; an `existing` outcome writes the proposal and nothing
-- else, because the Test it names was emitted when it was created. Only
-- `created` has an Event, and it is `tests`'s own.
INSERT INTO event_table_exempt (table_name, exempt_kind, reason, owner_ticket) VALUES
    ('test_proposals', 'audit',
     'the append-only record of what specification was proposed and what was answered; only the created outcome has an Event of its own, and a refused or existing proposal writes no canonical row for one to be about', '141');

SELECT attach_event_triggers();

GRANT SELECT, INSERT ON test_proposals TO rk2_runtime;
GRANT SELECT ON test_proposals TO rk2_human;

-- And the same registry the verb below is declared in. 066's standing check
-- refuses a table privilege the runtime holds that no row explains, and it
-- refuses it for the same reason it refuses an undeclared verb: a GRANT is the
-- one part of a migration that widens what a compromised runtime connection can
-- reach, so it is written twice on purpose and the second half is the one a
-- reader of the surface finds.
INSERT INTO runtime_table_surface (table_name, privilege, added_by) VALUES
    ('test_proposals', 'SELECT', '141'),
    ('test_proposals', 'INSERT', '141');

-- No UPDATE and no DELETE below the owner, for `finding_proposals`' reason:
-- what was proposed and what was answered is settled when it is written, and a
-- row that could be edited afterwards is an audit trail that agrees with
-- whatever is convenient now.
CREATE TRIGGER test_proposals_immutable
    BEFORE UPDATE OR DELETE ON test_proposals
    FOR EACH ROW EXECUTE FUNCTION reject_mutation_unless_purging();


-- ===========================================================================
-- 2. The verb the runtime carries a proposal to
-- ===========================================================================
-- Three refusals and each one is a sentence rather than an exception, because
-- the caller has to file what it hears. 035 made `rk2_test_spec_problem` a
-- function and not a CHECK expression for exactly this: a child told only
-- "violates tests_spec_shape_check" has to guess which of thirty rules it broke,
-- and the whole value of answering while the run is still going is that it can
-- correct the one it actually got wrong and send again.
--
-- The first two are this file's own and neither is about the specification:
--
--   the label names no claim   -- `propose_finding`'s arm, for its reason. A
--                                 uuid-taking refusal handed NULL would answer
--                                 "<NULL> is not a Hypothesis", which tells the
--                                 child nothing about the word it said.
--   the claim is not testable  -- `open_test_replay` refuses a Test whose claim
--                                 is any other status, so a specification
--                                 authored against one is a row nothing could
--                                 ever run. Said here, once, in the words that
--                                 verb uses.
--
-- WHAT THIS DOES NOT ASK, AND WHY. `open_test_replay` classes every url in the
-- actions, the setup and the cleanup against the scope version in force when the
-- replay opens, and this verb deliberately does not class them again. The scope
-- is versioned and a Test is immutable: an answer taken here is an answer about
-- a scope that may not be the one the replay binds to, and two answers to one
-- question is what 035 refused when it kept preconditions prose rather than
-- predicates. The same goes for the Halt and the budget. What is asked here is
-- what will still be true whenever the replay happens -- is this a claim, is it
-- waiting for a Test, is this a specification -- and everything that is a fact
-- about a moment is asked at the moment it binds.
--
-- INVOKER rather than SECURITY DEFINER, for `propose_finding`'s reason: the
-- caller is `rk2_runtime`, which already holds INSERT on `tests` and on the
-- table above, so a definer wrapper would hand the runtime a privilege it does
-- not need to do what it can already do.

CREATE FUNCTION propose_test(
        p_label     text,
        p_spec      jsonb,
        p_agent_run uuid DEFAULT NULL)
RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p            uuid := rk2_program_required();
    v_said       text := btrim(coalesce(p_label, ''));
    v_spec       jsonb := coalesce(p_spec, 'null'::jsonb);
    v_hypothesis uuid;
    v_status     text;
    v_agent_run  uuid;
    v_refusal    text;
    v_digest     text;
    v_id         uuid;
    v_label      text;
    v_outcome    text;
BEGIN
    PERFORM set_actor('runtime');

    -- Provenance, and only this Program's. An Agent run belonging to somebody
    -- else is not provenance for a row here, and the composite foreign key
    -- would raise on it -- taking the record of the attempt down with the
    -- mistake.
    SELECT ar.id INTO v_agent_run
      FROM agent_runs ar WHERE ar.id = p_agent_run AND ar.program_id = p;

    SELECT h.id, h.status INTO v_hypothesis, v_status
      FROM hypotheses h WHERE h.program_id = p AND h.label = v_said;

    IF v_hypothesis IS NULL THEN
        v_refusal := format('%s is not a Hypothesis of this Program',
                            coalesce(nullif(v_said, ''), '(none)'));
    ELSIF v_status <> 'testable' THEN
        v_refusal := format(
            'hypothesis %s is %s, and a Test may only be authored for a testable claim',
            v_said, v_status);
    ELSE
        v_refusal := rk2_test_spec_problem(v_spec);
    END IF;

    IF v_refusal IS NOT NULL THEN
        INSERT INTO test_proposals
            (program_id, hypothesis_id, agent_run_id, spec, outcome, refusal)
        VALUES (p, v_hypothesis, v_agent_run, v_spec, 'refused', v_refusal);
        RETURN jsonb_build_object('outcome', 'refused', 'refusal', v_refusal);
    END IF;

    v_digest := rk2_test_spec_digest(v_spec);

    -- `ON CONFLICT` rather than a look-then-insert, and rather than the advisory
    -- lock `open_finding` takes on its cell. A Finding's cell is a functional
    -- expression with no unique index behind it, so that one has to hold a lock;
    -- this one is `tests_hypothesis_id_spec_sha256_key`, a real unique
    -- constraint, so the database decides the race and the loser reads the row
    -- the winner wrote. What that avoids is the failure mode 036 names: a unique
    -- violation aborts the transaction and takes the record of the attempt down
    -- with it, so the one proposal an operator most wants to see is the one that
    -- would leave no row.
    INSERT INTO tests (program_id, hypothesis_id, spec, spec_sha256, created_by_run_id)
    VALUES (p, v_hypothesis, v_spec, v_digest, v_agent_run)
    ON CONFLICT (hypothesis_id, spec_sha256) DO NOTHING
    RETURNING id, label INTO v_id, v_label;

    IF v_id IS NULL THEN
        -- One Hypothesis holds one copy of a specification -- performing it
        -- twice is what a second Test run is for. So a second identical
        -- proposal is answered with the Test that is already there and is not a
        -- refusal: it is a run that reached the same plan the last one did,
        -- which is a fact worth having in this table and not a mistake.
        SELECT t.id, t.label INTO v_id, v_label
          FROM tests t
         WHERE t.hypothesis_id = v_hypothesis AND t.spec_sha256 = v_digest;
        v_outcome := 'existing';
    ELSE
        v_outcome := 'created';
    END IF;

    INSERT INTO test_proposals
        (program_id, hypothesis_id, agent_run_id, spec, outcome, test_id)
    VALUES (p, v_hypothesis, v_agent_run, v_spec, v_outcome, v_id);

    RETURN jsonb_build_object(
        'outcome',     v_outcome,
        'test',        v_label,
        'hypothesis',  v_said,
        -- The identity, because that is what a Test is. `tests` is immutable and
        -- `rk2_test_spec_digest` is over the stored jsonb, so this is the one
        -- value that distinguishes the plan that was stored from any other plan
        -- the run might have meant to send.
        'spec_sha256', v_digest,
        'actions',     jsonb_array_length(v_spec -> 'actions'),
        'assertions',  jsonb_array_length(v_spec -> 'assertions'));
END $fn$;

COMMENT ON FUNCTION propose_test(text, jsonb, uuid) IS
    'Ticket 141. Author one immutable Test specification for a testable claim '
    'named by the label a child can read, or answer the sentence saying why not. '
    'Answers created, existing or refused; a refusal is the first problem '
    '`rk2_test_spec_problem` found, or this file''s own sentence about the label '
    'or the claim''s status, and every attempt leaves a `test_proposals` row.';

REVOKE ALL ON FUNCTION propose_test(text, jsonb, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION propose_test(text, jsonb, uuid) TO rk2_runtime;

-- 066's registry, which is what makes the grant above a declaration rather than
-- a fact somebody would have to go and measure. `check_runtime_privileges`
-- refuses a verb the runtime can execute that no row here names, so the grant
-- and the row are one statement made twice on purpose: the second half is the
-- one a reader of the surface finds.
INSERT INTO runtime_verb_surface (verb, added_by, note) VALUES
    ('propose_test(text, jsonb, uuid)',
     '141',
     'authors the Test specification a replay runs -- the first writer of `tests` any Agent run can reach, and the row `testing -> supported` and therefore every Finding rests on');


-- ===========================================================================
-- 3. What this migration claims, asserted
-- ===========================================================================

DO $$
DECLARE v_before integer; v_after integer;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_proc
         WHERE proname = 'propose_test'
           AND has_function_privilege('rk2_runtime', oid, 'EXECUTE')
    ) THEN
        RAISE EXCEPTION 'ticket 141: the runtime cannot carry a specification';
    END IF;

    -- The point of the whole ticket, stated as the thing that would have to stay
    -- true. Before this file the only way to a `tests` row was through a Finding
    -- or through a fixture; a later file that revoked this grant, or renamed the
    -- function out from under its caller, should fail here rather than quietly
    -- return the tree to the state the wiring audit found it in.
    IF NOT has_table_privilege('rk2_runtime', 'tests', 'INSERT') THEN
        RAISE EXCEPTION 'ticket 141: the runtime cannot write the row it just decided on';
    END IF;

    -- A proposal that names no claim still leaves a row, which is the half of
    -- the record the early refusal above could have lost. If the column ever
    -- stopped accepting a null claim, that row could not be written and the
    -- refusal would raise instead of answering.
    IF EXISTS (
        SELECT 1 FROM pg_attribute
         WHERE attrelid = 'test_proposals'::regclass
           AND attname = 'hypothesis_id' AND attnotnull
    ) THEN
        RAISE EXCEPTION 'ticket 141: a proposal naming no claim can no longer be filed';
    END IF;

    -- And the shape rule is still a function a caller can read the answer of,
    -- rather than a CHECK a caller can only be raised at. Every refusal this
    -- file files for a well-named claim is that function's sentence.
    SELECT count(*) INTO v_before FROM pg_proc WHERE proname = 'rk2_test_spec_problem';
    IF v_before <> 1 THEN
        RAISE EXCEPTION 'ticket 141: the specification rule is not one readable function';
    END IF;

    -- The two-step is real rather than declared: the tool's write target and the
    -- canonical row it leads to are different tables, and only the second is one
    -- `roster.CANONICAL` names.
    SELECT count(*) INTO v_after FROM pg_class
     WHERE relname IN ('tests', 'test_proposals') AND relkind = 'r';
    IF v_after <> 2 THEN
        RAISE EXCEPTION 'ticket 141: the proposal and the Test are not two tables';
    END IF;
END $$;
