-- A banded Finding gets the Task that asks for its impact       (ticket 226)
--
-- Wall 1 of ticket 226, and the last of the three. Wall 2 gave an impact Test a
-- lane that performs it (`20261231T000000Z...`); this file is what writes one.
--
-- `grep -n "open_impact_task" src/redkraken/execution.py` returned nothing. The
-- verb is granted, wrapped by ticket 103 as `propose_impact_task`
-- (`20261031T000000Z...:110`), and lives in `state.conclude`, which `web_hunter`
-- holds alone (`roster.py:2275`). But the two `conclude` objectives are ticket
-- 156's, which names a Finding, and ticket 221's, which states a severity.
-- Neither mentions impact, so no child has ever been asked to prove one, so no
-- impact Test has ever existed, so `pivot_stamps` has never held a row and
-- `chains` has never held a row -- on a Program that had run 197 laps.
--
-- This is ticket 221's shape a third time: served, described, granted and
-- unreachable.
--
-- THE ORDER, AND WHY IT IS BAND FIRST. `rk2_severity_frontier` refuses a
-- Finding that any `conclude` Task already names, in any status
-- (`20261230T000000Z...`). So an impact Task opened before the band would be the
-- row that stops the band from ever being derived, and 221's whole lane would
-- close the day this file landed. Banding first costs the first statement its
-- strongest basis -- `state_severity` refuses `demonstrated_impact` when there
-- is no demonstration, so the first band is an inference -- and buys two things
-- instead: 221 is not touched at all, and the band becomes a fence in time that
-- separates the two shapes of this kind without a column, because a band Task
-- can only ever be opened before the first statement about its Finding.
--
-- `severity_statements` is append-only and says so -- "a severity that changed
-- is two rows, and the later one has to say why" -- so a demonstration that
-- lands later can still be stated on. Deriving THAT restatement is not in this
-- file and is not in ticket 226's acceptance; what is here is the ask that makes
-- a demonstration possible at all.
--
-- Scope: the specification and nothing else. `compose_finding_report` is the
-- third verb of `state.conclude` and is its own ticket, for 221's reason -- a
-- Task asked for three things it can only do one of is a Task that ends having
-- done none.

-- ===========================================================================
-- 1. Which of this kind's three jobs a Task was opened for
-- ===========================================================================
-- Ticket 156's `conclude` Task names a Finding and carries no `finding_id`.
-- Ticket 221's bands one and carries it. This ticket's proves one and carries
-- it too, so the column that told the first from the second cannot tell the
-- second from the third, and the fence is time instead: `rk2_severity_frontier`
-- refuses a Finding whose `severity_basis` has moved, so a band Task is always
-- opened BEFORE the first statement about that Finding, and every `conclude`
-- Task opened after one was opened to ask this ticket's question.
--
-- One function and not the same expression in three places, for the reason
-- `rk2_subject_addressable` is one function: the frontier, `novelty_for` and
-- `execution.py`'s claim query all have to read it the same way, and a rule
-- written out three times is three rules that can drift. Ticket 157 measured
-- what that costs when two of them did.
--
-- NULL where the Finding has no statement at all, which is a band Task before
-- its band -- so every caller asks `IS TRUE`, the way `ready_for` asks
-- `rk2_subject_addressable`.

CREATE FUNCTION rk2_task_proves_impact(t tasks) RETURNS boolean
LANGUAGE sql STABLE AS $fn$
    SELECT t.kind = 'conclude'
       AND t.finding_id IS NOT NULL
       AND t.created_at >= (SELECT min(s.created_at) FROM severity_statements s
                             WHERE s.finding_id = t.finding_id
                               AND s.program_id = t.program_id);
$fn$;

COMMENT ON FUNCTION rk2_task_proves_impact(tasks) IS
  'Ticket 226 wall 1. Whether a `conclude` Task naming a Finding was opened to prove its impact rather than to band it, which is decided by whether it was opened after the band was stated -- `rk2_severity_frontier` will not open a band Task once `severity_basis` has moved, so the two can never overlap. NULL for a Finding nobody has banded; every caller asks IS TRUE.';

REVOKE ALL ON FUNCTION rk2_task_proves_impact(tasks) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rk2_task_proves_impact(tasks) TO rk2_runtime;


-- ===========================================================================
-- 2. The frontier, and the derivation that spends it
-- ===========================================================================

CREATE FUNCTION rk2_impact_specification_frontier(p_program_id uuid)
RETURNS TABLE (finding_id uuid, hypothesis_id uuid, subject_entity_id uuid,
               banded_at timestamptz)
LANGUAGE sql STABLE AS $fn$
    SELECT f.id, fh.hypothesis_id, f.subject_entity_id, b.banded_at
      FROM findings f
      JOIN entities e ON e.id = f.subject_entity_id AND e.program_id = f.program_id
      -- One claim, and the lowest-ordered of them, which is the rule
      -- `rk2_severity_frontier` uses and the rule `open_impact_task` itself
      -- uses when it picks the claim the impact Test hangs off
      -- (`20260816T000000Z...:1248`). Three readers of one question have to
      -- agree, and taking the deterministic one rather than the interesting one
      -- is how they do.
      JOIN LATERAL (
             SELECT x.hypothesis_id FROM finding_hypotheses x
              WHERE x.finding_id = f.id AND x.program_id = f.program_id
              ORDER BY x.hypothesis_id LIMIT 1
           ) fh ON true
      -- When somebody first said what this Finding is worth. It is the order
      -- written as a row -- a Finding with no statement is one 221's Task is
      -- still owed -- and it is what the derivation ranks by, so a pass that
      -- cannot afford every candidate spends the ceiling on the oldest band.
      JOIN LATERAL (
             SELECT min(s.created_at) AS banded_at FROM severity_statements s
              WHERE s.finding_id = f.id AND s.program_id = f.program_id
           ) b ON b.banded_at IS NOT NULL
     WHERE f.program_id = p_program_id
       -- `validated` and not `validated, reported`, which is narrower than
       -- `ready_for`'s conclude arm on purpose: `open_impact_task` refuses
       -- anything else by name (`20260816T000000Z...:1229`), and a frontier that
       -- named a row the verb would turn away is a Task that ends in a refusal.
       AND f.status = 'validated'
       AND e.in_scope
       AND rk2_subject_addressable(f.subject_entity_id) IS TRUE
       AND EXISTS (SELECT 1 FROM hypotheses h
                    WHERE h.id = fh.hypothesis_id AND h.status = 'supported')
       -- Nothing to ask for where it is already proved.
       AND NOT EXISTS (SELECT 1 FROM impact_demonstrations d
                        WHERE d.finding_id = f.id AND d.program_id = f.program_id)
       -- And nothing to ask for where it has already been asked and answered.
       -- The marker is the Test rather than the demonstration, because the Test
       -- is what this Task's one call writes: `propose_impact_task` reaches
       -- `open_impact_task`, which writes `tests` with the class on it. Wall 2's
       -- lane takes it from there, and `novelty_for` reads the same row, so the
       -- frontier and the novelty agree by construction.
       AND NOT EXISTS (SELECT 1 FROM tests ts
                         JOIN finding_hypotheses x ON x.hypothesis_id = ts.hypothesis_id
                        WHERE x.finding_id = f.id AND ts.impact_class IS NOT NULL)
       AND NOT EXISTS (
             SELECT 1 FROM tasks k
              WHERE k.program_id = f.program_id
                AND k.kind = 'conclude'
                AND k.finding_id = f.id
                -- (i) the dedup guard. `tasks_live_dedup_idx` is UNIQUE over
                --     the live statuses on a key this row would repeat, so a
                --     band Task still `running` when its own statement landed
                --     would make the INSERT below raise -- and a unique
                --     violation inside a derivation takes the whole pass with
                --     it.
                AND (k.status IN ('pending', 'claimed', 'running', 'parked')
                -- (ii) the respawn guard, and 221's rule said in the one way
                --      this shape can say it. 221 refuses a Finding any
                --      `conclude` Task names in any status; here that would
                --      match the band Task and this frontier would never fire
                --      at all. `rk2_task_proves_impact` is the same rule over
                --      the Tasks this ticket opens, in any status -- so it is
                --      asked once and a Task that ended having filed nothing is
                --      not respawned, which is 221's behaviour and its reason:
                --      a Finding stuck is a fact an operator can read and a
                --      Task the pass re-derives forever is not.
                     OR rk2_task_proves_impact(k.*) IS TRUE));
$fn$;

COMMENT ON FUNCTION rk2_impact_specification_frontier(uuid) IS
  'Ticket 226 wall 1. The validated Findings of a Program that somebody has banded, whose impact nobody has specified or demonstrated, whose subject is in scope and addressable, that rest on a claim still supported, and that no `conclude` Task has named since the band was stated. Shaped after `rk2_severity_frontier`, and ordered after it: the band is derived first because that frontier refuses a Finding any `conclude` Task already names.';

REVOKE ALL ON FUNCTION rk2_impact_specification_frontier(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rk2_impact_specification_frontier(uuid) TO rk2_runtime;


CREATE FUNCTION derive_impact_specifications() RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p        uuid := rk2_program_required();
    ceiling  smallint;
    n_wanted bigint := 0;
    n_tasks  bigint := 0;
BEGIN
    -- The same ceiling as `derive_finding_claims` and `derive_finding_bands`,
    -- and deliberately not a third column, for 221's reason: all three open
    -- `conclude` Tasks, so one bound over all three is the honest reading of
    -- "how many conclusions may a pass derive". A pass that spends it all
    -- elsewhere derives no specifications and the next pass derives them, which
    -- is the deferral the return value already reports.
    SELECT w.max_conclusions_derived_per_pass INTO ceiling
      FROM scheduler_weights w WHERE w.active;
    IF NOT FOUND THEN RAISE EXCEPTION 'no active scheduler_weights row'; END IF;

    SELECT count(*) INTO n_wanted FROM rk2_impact_specification_frontier(p);

    -- Oldest band first, for the reason the other three derivations order by
    -- arrival: these Tasks do not exist yet, so there is no ranking to prefer
    -- one by, and arrival order is the one deterministic answer -- which is what
    -- makes the ceiling reproducible.
    WITH wanted AS (
        SELECT fr.finding_id, fr.hypothesis_id, fr.subject_entity_id
          FROM rk2_impact_specification_frontier(p) fr
         ORDER BY fr.banded_at, fr.finding_id
         LIMIT ceiling
    ), made AS (
        INSERT INTO tasks (program_id, kind, finding_id, hypothesis_id,
                           subject_entity_id)
        SELECT p, 'conclude', w.finding_id, w.hypothesis_id, w.subject_entity_id
          FROM wanted w
        RETURNING 1 AS one
    )
    SELECT count(*) INTO n_tasks FROM made;

    RETURN jsonb_build_object('candidates', n_wanted,
                              'derived', n_tasks,
                              'deferred', greatest(n_wanted - n_tasks, 0),
                              'ceiling', ceiling);
END $fn$;

COMMENT ON FUNCTION derive_impact_specifications() IS
  'Ticket 226 wall 1. Opens one `conclude` Task per banded Finding whose impact nobody has specified, carrying `finding_id` like ticket 221''s -- `rk2_task_proves_impact` is what tells the two apart, and it can because a band Task is always opened before the band. Bounded by `max_conclusions_derived_per_pass`, shared with the other two conclusion derivations because all three open the same kind.';

REVOKE ALL ON FUNCTION derive_impact_specifications() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION derive_impact_specifications() TO rk2_runtime;


-- ===========================================================================
-- 3. The one factor that would otherwise end this Task on the next pass
-- ===========================================================================
-- Replaced whole, because that is how this corpus edits a function. `ready_for`
-- needs no change: its `conclude` arm asks a Task carrying a Finding for a
-- claim that is `supported` and a Finding that is `validated` or `reported`,
-- and both shapes of the kind satisfy it. `cancel_reason_for` needs none
-- either: ticket 156's exception already keeps a `conclude` Task alive over a
-- settled claim, and everything else it would say is about a history a Task
-- created moments ago does not have.
--
-- `novelty_for` is the one that would. Its `conclude` arm scores a Task
-- carrying a Finding 0 as soon as `severity_basis` is no longer `undetermined`
-- -- which is true of every Task this file derives, by construction -- and
-- `cancel_reason_for`'s general rule reads a zero as nothing left to learn.
-- Without this, the pass after the derivation abandons the Task as `answered`
-- before it is ever offered: ticket 152's measurement, in a third place.

CREATE OR REPLACE FUNCTION public.novelty_for(t tasks)
 RETURNS numeric
 LANGUAGE plpgsql
 STABLE
AS $function$
DECLARE
    covered   integer;
    total     integer;
    n_ev      integer;
    st        text;
    fired     boolean;
BEGIN
    IF t.kind = 'recon' THEN
        -- Ticket 27, measured: the denominator is the 8 FAMILIES, not the 33
        -- leaves. Family coverage ranged 0.625 across the corpus against 0.24
        -- for leaf coverage, so the leaf denominator makes every recon task
        -- look equally novel forever.
        --
        -- And the numerator routes through `hypotheses`, not `observations`:
        -- 27 executed the schema and found `observations` has no
        -- `property_class` at all, and said explicitly not to add one. A
        -- property class is a claim about what a test IS; an observation is a
        -- fact. What "has this property been looked at on this subject" means
        -- is therefore "has a hypothesis about it been written down".
        --
        -- Ticket 193: "on this subject" is half the question. Since ticket 191
        -- a subject is walked once per state, and a claim reached while signed
        -- out says nothing about what is visible while signed in. The state a
        -- claim was reached in is not on the claim -- ticket 190 -- but the run
        -- that reached it is, and ticket 131 put the Identity on that run's
        -- Task. A claim with no provenance counts for no state rather than for
        -- every one: the failure that direction produces is one walk too many,
        -- and the other direction hides a whole state for the life of a hunt.
        SELECT count(DISTINCT pc.family_id) INTO covered
          FROM hypotheses h
          JOIN property_classes pc ON pc.id = h.property_class
         WHERE h.subject_entity_id = t.subject_entity_id
           AND h.superseded_by IS NULL
           AND EXISTS (SELECT 1
                         FROM hypothesis_provenance hp
                         JOIN agent_runs ar ON ar.id = hp.agent_run_id
                         JOIN tasks k ON k.id = ar.task_id
                        WHERE hp.hypothesis_id = h.id
                          AND k.selected_identity_entity_id
                              = t.selected_identity_entity_id);
        SELECT count(*) INTO total FROM property_class_families;
        RETURN greatest(1.0 - covered::numeric / total, 0);

    ELSIF t.kind = 'analyze' THEN
        -- Same shape over the other vocabulary 27 built. "analysis-kind" is
        -- decidable now: it is a kind a tool run may back, which is exactly
        -- what offline analysis over a content-addressed artifact produces.
        SELECT count(DISTINCT o.kind) INTO covered
          FROM observations o
          JOIN observation_kinds k ON k.id = o.kind
         WHERE o.subject_entity_id = t.subject_entity_id
           AND o.provenance_kind = 'tool_run'
           AND 'tool_run' = ANY (k.allowed_provenance);
        SELECT count(*) INTO total
          FROM observation_kinds WHERE 'tool_run' = ANY (allowed_provenance);
        RETURN greatest(1.0 - covered::numeric / total, 0);

    ELSIF t.kind = 'hunt' THEN
        SELECT h.status INTO st FROM hypotheses h WHERE h.id = t.hypothesis_id;
        SELECT EXISTS (SELECT 1 FROM hypothesis_retest_triggers x
                        WHERE x.hypothesis_id = t.hypothesis_id
                          AND x.fired_at IS NOT NULL) INTO fired;
        IF st IN ('supported','refuted') AND NOT fired THEN
            RETURN 0;
        END IF;
        SELECT count(*) INTO n_ev
          FROM hypothesis_evidence WHERE hypothesis_id = t.hypothesis_id;
        -- Ticket 127: the `penalised` discount that used to multiply this is
        -- gone with the action it belonged to. There is no similarity in this
        -- schema to discount by.
        RETURN 1.0 / (1 + n_ev);

    ELSIF t.kind = 'validate' THEN
        -- 32/D13 was closed by migration 015: a validate task names its
        -- finding, so this is a lookup rather than a scan of the subject.
        RETURN CASE WHEN EXISTS (
                 SELECT 1 FROM findings f
                  WHERE f.id = t.finding_id
                    AND f.status IN ('validated','reported','rejected'))
               THEN 0 ELSE 1 END;

    ELSIF t.kind = 'perform' THEN
        -- Ticket 152, found in the first live run that had a `perform` Task in
        -- it. Without this arm the function fell through to the closing
        -- `RETURN 0`, `cancel_reason_for`'s general rule read that as nothing
        -- left to learn, and every `perform` Task the pass derived was
        -- abandoned as `answered` before it could be offered once. `rk2hunt13`
        -- measured it exactly: T5 abandoned with 0 attempts, T6 pending and
        -- ready with `claimable_for = 'answered'`, and the lap that should
        -- have claimed T6 reported `nothing_to_execute`.
        --
        -- Shaped like `validate`'s and for the same reason: the Task names the
        -- Test it performs, so this is a lookup and not a scan of the subject.
        -- A specification nobody has walked is the whole of what is not yet
        -- known about it; once a replay is on file there is nothing further a
        -- second walk of the same actions could learn, which is also what
        -- `ready_for` says when it refuses `perform.already_performed`.
        RETURN CASE WHEN EXISTS (
                 SELECT 1 FROM test_replays tp WHERE tp.test_id = t.test_id)
               THEN 0 ELSE 1 END;

    ELSIF t.kind = 'conclude' THEN
        -- Ticket 156. A settled claim that no Finding rests on has one thing
        -- left to learn about it, and it is the thing this kind exists to
        -- write down: what the claim is a Finding OF. Once an edge in
        -- `finding_hypotheses` names it there is nothing further, and the
        -- second conclusion of one claim would be a merge into a row that is
        -- already open.
        --
        -- Ticket 221 splits the arm the way `ready_for`'s is split. A Task
        -- carrying a `finding_id` is not asking what the claim is a Finding of;
        -- it is asking what the Finding is worth, and what is left to learn
        -- about that is whether anybody has said. `findings.severity_basis` is
        -- the answer because `state_severity` writes it in the same statement
        -- that writes the band, so it cannot drift from the statement row.
        --
        -- Ticket 226 adds the third job of this kind ahead of both, and 221's
        -- answer is left exactly as it was underneath. A Task opened after its
        -- Finding was banded is not asking what the Finding is worth; it is
        -- asking for the thing the band could not rest on, because
        -- `state_severity` refuses `demonstrated_impact` while no demonstration
        -- is on file. What is left to learn about that is whether anybody ever
        -- went and specified it, and the marker is the impact Test rather than
        -- the demonstration, because writing that Test is the whole of what the
        -- Task was opened to do -- `rk2_impact_specification_frontier` reads
        -- the same row, so the frontier and this factor cannot disagree about
        -- when the question is answered.
        IF rk2_task_proves_impact(t) IS TRUE THEN
            RETURN CASE WHEN EXISTS (
                     SELECT 1 FROM tests ts
                       JOIN finding_hypotheses fh
                         ON fh.hypothesis_id = ts.hypothesis_id
                      WHERE fh.finding_id = t.finding_id
                        AND ts.impact_class IS NOT NULL)
                   THEN 0 ELSE 1 END;
        END IF;
        IF t.finding_id IS NOT NULL THEN
            RETURN CASE WHEN EXISTS (
                     SELECT 1 FROM findings f
                      WHERE f.id = t.finding_id
                        AND f.severity_basis <> 'undetermined')
                   THEN 0 ELSE 1 END;
        END IF;
        RETURN CASE WHEN EXISTS (
                 SELECT 1 FROM finding_hypotheses fh
                  WHERE fh.hypothesis_id = t.hypothesis_id)
               THEN 0 ELSE 1 END;

    ELSIF t.kind = 'report' THEN
        RETURN CASE WHEN EXISTS (
                 SELECT 1 FROM findings f
                  WHERE f.program_id = t.program_id AND f.status = 'validated'
                    AND f.reported_at IS NULL) THEN 1 ELSE 0 END;
    END IF;
    RETURN 0;
END $function$;


-- ===========================================================================
-- 4. The pass that runs it
-- ===========================================================================
-- Replaced whole for the same reason, with one step added. The body below is
-- the live definition; step (3g) is the only new thing in it.

CREATE OR REPLACE FUNCTION public.rank_pass(p_trigger text DEFAULT 'timer'::text)
 RETURNS jsonb
 LANGUAGE plpgsql
AS $function$

DECLARE
    p            uuid := rk2_program_required();
    w            scheduler_weights%ROWTYPE;
    n_cancelled  bigint := 0;
    n_retired    bigint := 0;
    n_ranked     bigint := 0;
    n_fired      bigint := 0;
    v_retests    jsonb;
    edges        jsonb;
    unlocks      jsonb;
    hunts        jsonb;
    performances jsonb;
    impact_runs  jsonb;
    conclusions  jsonb;
    bands        jsonb;
    impacts      jsonb;
    by_reason    jsonb;
    top          jsonb;
    doomed       record;
    t0           timestamptz := clock_timestamp();
BEGIN
    SELECT * INTO w FROM scheduler_weights WHERE active;
    IF NOT FOUND THEN RAISE EXCEPTION 'no active scheduler_weights row'; END IF;

    -- (1) Retest re-entry. Decision 11: the pass owns it, because it is the
    -- only runtime step that reads the whole program. 034 moved the body out
    -- into `refresh_negative_knowledge`, which is where the kept refutations
    -- are and where 022's per-Application fingerprint comparison had to go; the
    -- pass keeps the decision about WHEN, which is what decision 11 was about.
    --
    -- It stays first, and that ordering is load-bearing twice over. A claim
    -- whose refutation stopped being current has to be out of `refuted` before
    -- step (2) reads its status, or the Task asking the question again is
    -- abandoned in the same pass that reopened it. And an imported refutation
    -- -- one nothing on file settles -- is reopened here before step (2) could
    -- ever read it as suppression.
    v_retests := refresh_negative_knowledge();
    n_fired   := (v_retests ->> 'reopened')::bigint;

    -- (2) Cancellation, before ranking: a task that should not run must not be
    -- ranked into a slate this pass.
    WITH c AS (
        SELECT t.id, cancel_reason_for(t, w) AS reason
          FROM tasks t WHERE t.program_id = p AND t.status = 'pending'
    ), u AS (
        UPDATE tasks t SET status = 'abandoned', abandoned_reason = c.reason,
                           finished_at = now(), priority = NULL
          FROM c WHERE t.id = c.id AND c.reason IS NOT NULL
        RETURNING t.abandoned_reason AS reason
    )
    SELECT count(*), coalesce(jsonb_object_agg(reason, n), '{}'::jsonb)
      INTO n_cancelled, by_reason
      FROM (SELECT reason, count(*) AS n FROM u GROUP BY reason) g;

    -- (2b) The unreadiness counter, over what step (2) left standing. After
    -- the cancellation rather than before it, because a Task that should not
    -- run at all has already ended and counting it would be counting a row
    -- nobody will read again.
    --
    -- Reset to 0 by the pass that finds it ready, so what the column holds is
    -- the length of the CURRENT run of unready passes and not a lifetime total.
    -- A Task that was blocked for two passes and then ran and then blocked
    -- again has not been blocked for three.
    UPDATE tasks t
       SET unready_passes = CASE WHEN ready_for(t.*) IS NULL THEN 0
                                 ELSE t.unready_passes + 1 END
     WHERE t.program_id = p AND t.status = 'pending';

    -- (2c) Ticket 158, and the whole of it. A Task with no attempts whose
    -- predicate has named the same kind of fact about its own row for
    -- `max_attempts` consecutive passes is a Task the scheduler will never call
    -- ready. It ends the way 143 ends the same state seen from the other side:
    -- `undispatchable`, with the predicate as the sentence on the event.
    --
    -- `attempts = 0` is not decoration. A Task that ran and came back is
    -- `attempts_exhausted`'s case, which step (2) has already answered; this
    -- one is about work that never started and never could.
    --
    -- The same ceiling as the attempts, deliberately. It is the number an
    -- operator already sets to say how many times this scheduler tries
    -- something before giving up on it, and a second knob would be a second
    -- answer to one question.
    -- A loop rather than a count over a subquery that calls it. `retire_task`
    -- is what this step DOES, not a value it reads, and a planner is entitled
    -- to drop an unreferenced target-list column -- which would make the whole
    -- step a no-op that reported the right number of nothings.
    FOR doomed IN
        SELECT t.id, ready_for(t.*) AS predicate
          FROM tasks t
         WHERE t.program_id = p
           AND t.status = 'pending'
           AND t.attempts = 0
           AND t.unready_passes >= w.max_attempts
           AND rk2_terminal_predicate(ready_for(t.*))
    LOOP
        PERFORM retire_task(doomed.id, doomed.predicate);
        n_retired := n_retired + 1;
    END LOOP;

    -- (3) Dependency edges, after cancellation and before ranking, for the
    -- same reason in both directions: a Task abandoned above must stop
    -- unlocking anything, and an edge derived below must be visible to the
    -- ranking in this pass rather than the next one.
    edges := derive_task_dependencies();

    -- (3b) Chain unlocks, after the edges for the first of those two reasons
    -- and before the ranking for the second. Not folded into (3): that function
    -- is 026's two rules over `ready_for` and this one creates Tasks, and a
    -- derivation that both restates a readiness predicate and mints rows would
    -- be two jobs sharing a name and a transaction-local licence.
    --
    -- The Tasks it creates are not put through (2). They cannot need it: the
    -- frontier will not name a subject off the Surface or a superseded
    -- hypothesis, and the other cancellation reasons are about a history a Task
    -- created moments ago does not have. The pass after this one asks anyway.
    unlocks := derive_chain_unlocks();

    -- (3c) Claims into work, after the chain unlocks and before the ranking,
    -- for the second of the two reasons above: a Task derived from a claim must
    -- be ranked in the pass that derived it or it waits a whole pass to be
    -- looked at. It runs after (3b) rather than before it because a chain
    -- unlock is a Task the corpus already knew how to want, and where both
    -- would name the same hypothesis the guard in either one sees the other's
    -- row and does not duplicate it -- whichever ran first.
    --
    -- Like (3b)'s Tasks, these are not put through (2). They cannot need it:
    -- the frontier will not name a subject off the Surface or a superseded
    -- claim, and the other cancellation reasons are about a history a Task
    -- created moments ago does not have. The pass after this one asks anyway.
    hunts := derive_hypothesis_hunts();

    -- (3d) The performances, after the hunts and before the ranking, for the
    -- third time in this function and the same two reasons. A Test authored by
    -- a hunt in the pass before this one is on file with nothing to perform it;
    -- this is what opens the Task that does. Not folded into (3c): that
    -- function grades claims and opens the work that produces a Test, and this
    -- one opens the work that spends one, which is the other end of the same
    -- loop and a different question about a different row.
    --
    -- Like (3b)'s and (3c)'s, these are not put through (2), and for the reason
    -- (3c) gives: a Task created moments ago has no history for a cancellation
    -- rule to read.
    performances := derive_test_performances();

    -- (3d2) The impact performances, immediately after the detection ones and
    -- for the same reason they come after the hunts: a Task derived here can be
    -- ranked in this pass rather than in the next one. Its own step and not a
    -- widening of (3d), because `rk2_test_performance_frontier` excludes
    -- `impact_class IS NOT NULL` deliberately -- an impact Test hangs off a
    -- claim that settled, so it can never satisfy that frontier's
    -- `h.status = 'testable'`, and a frontier told to ignore its own ordering
    -- rule is two frontiers wearing one name.
    impact_runs := derive_impact_performances();

    -- (3e) The conclusions, last of the four and for the same two reasons a
    -- fourth time. This one is the end of the loop rather than a step inside
    -- it: (3c) turns a claim into a question, (3d) spends the answer, and this
    -- opens the work that writes down what the answer was. Ticket 156 -- until
    -- it, a claim reached `supported` and the campaign stopped there, because
    -- `propose_finding` had no Task that would ever put a role holding it in
    -- front of a settled claim.
    --
    -- Not put through (2) either, and here that is not merely unnecessary but
    -- would be wrong: step (2) reads a `supported` claim as an answered
    -- question, and 156's exception is what stops it reading these Tasks that
    -- way at all. Nor through (2b) and (2c): a Task created moments ago has no
    -- run of unready passes behind it, and its counter starts at 0 where the
    -- column's default put it.
    conclusions := derive_finding_claims();

    -- (3f) The bands, after the conclusions and for the reason (3e) comes after
    -- (3d): this is the other end of the same loop. (3e) opens the work that
    -- names what a settled claim is a Finding of; this opens the work that says
    -- what that Finding is worth, once a validation has confirmed it. Ticket
    -- 221 -- until it, a Finding reached `validated` and stopped there, because
    -- `state_severity` had no Task that would ever put a role holding it in
    -- front of a validated Finding.
    --
    -- Not put through (2), (2b) or (2c), for the three reasons (3e) gives: a
    -- Task created moments ago has no history, no unready passes and no
    -- suppression behind it.
    bands := derive_finding_bands();

    -- (3g) The impact specifications, immediately after the bands and never
    -- before them. Ticket 226 wall 1 -- until it, no objective in this runtime
    -- asked a child to call `propose_impact_task`, so no impact Test was ever
    -- written, so wall 2's lane had nothing to run and `pivot_stamps` and
    -- `chains` held zero rows after 197 laps.
    --
    -- The order is not a preference. `rk2_severity_frontier` refuses a Finding
    -- that any `conclude` Task already names in any status, so a specification
    -- Task derived before the band would be the row that stops the band being
    -- derived at all -- and the frontier here reads `severity_statements`, so
    -- running before (3f) would simply find nothing on the first pass and the
    -- next pass would do the same work one lap later.
    --
    -- Not put through (2), (2b) or (2c), for (3f)'s three reasons.
    impacts := derive_impact_specifications();

    -- (4) The ranking. One statement, eight components, no clock in it.
    WITH r AS (
        SELECT t.id,
               novelty_for(t)         AS novelty,
               cost_for(t, w)         AS estimated_cost,
               time_for(t, w)         AS estimated_time,
               safety_for(t, w)       AS safety_cost,
               confidence_for(t, w)   AS confidence,
               value_for(t, w)        AS direct_value,
               unlock_for(t, w)       AS direct_unlock,
               chain_unlock_for(t)    AS chain_unlock
          FROM tasks t
         WHERE t.program_id = p AND t.status = 'pending'
    ), u AS (
        UPDATE tasks t
           SET novelty = r.novelty,
               estimated_cost = r.estimated_cost,
               estimated_time = r.estimated_time,
               safety_cost = r.safety_cost,
               confidence_of_execution = r.confidence,
               direct_value = r.direct_value,
               chain_unlock_value = r.chain_unlock,
               unlock_value = least(r.direct_unlock + r.chain_unlock, 1.0),
               ranked_weights_version = w.version,
               -- NULL, not 0: an unestimated task must sink via NULLS LAST, and
               -- a task scored 0 is a different statement from one never scored
               priority = CASE
                   WHEN r.direct_value IS NULL THEN NULL
                   ELSE r.novelty * r.confidence
                        * (r.direct_value
                           + w.w_unlock * least(r.direct_unlock + r.chain_unlock, 1.0))
                        / greatest(w.w_tokens * r.estimated_cost
                                 + w.w_time   * r.estimated_time
                                 + w.w_safety * r.safety_cost, w.cost_floor)
               END
          FROM r WHERE t.id = r.id
        RETURNING t.id
    )
    SELECT count(*) INTO n_ranked FROM u;

    SELECT coalesce(jsonb_agg(j ORDER BY ord), '[]'::jsonb) INTO top
      FROM (
        SELECT row_number() OVER (ORDER BY t.priority DESC NULLS LAST,
                                           t.created_at, t.id) AS ord,
               jsonb_build_object(
                 'task', t.label, 'kind', t.kind,
                 'priority', round(t.priority, 6),
                 'factors', task_rank_factors(t)) AS j
          FROM tasks t WHERE t.program_id = p AND t.status = 'pending'
          ORDER BY t.priority DESC NULLS LAST, t.created_at, t.id
          LIMIT 10) s;

    INSERT INTO events (program_id, type, actor_kind, payload)
    VALUES (p, 'scheduler.ranked', 'runtime', jsonb_build_object(
        'trigger', p_trigger,
        'weights_version', w.version,
        'candidates', n_ranked,
        'retests', v_retests,
        'abandoned_by_reason', by_reason,
        'retired_unready', n_retired,
        'dependency_edges', edges,
        'chain_unlocks', unlocks,
        'hypothesis_hunts', hunts,
        'test_performances', performances,
        'impact_performances', impact_runs,
        'finding_claims', conclusions,
        'finding_bands', bands,
        'impact_specifications', impacts,
        'lane_slots', (SELECT coalesce(jsonb_object_agg(kind, live_slots), '{}'::jsonb)
                         FROM scheduler_lane_state WHERE program_id = p),
        'top', top,
        'further_omitted', greatest(n_ranked - 10, 0),
        'duration_ms', round(extract(epoch FROM clock_timestamp() - t0) * 1000)));

    RETURN jsonb_build_object('ranked', n_ranked, 'abandoned', n_cancelled,
                              -- `retests_fired` is 023's key and stays what it
                              -- was: how many claims re-entered. `retests` is
                              -- the breakdown behind it, so a caller can tell a
                              -- pass that reopened nothing because nothing moved
                              -- from one that reopened nothing because it found
                              -- nothing to reopen.
                              'retests_fired', n_fired,
                              'retests', v_retests,
                              -- Beside `abandoned` and not folded into it: one
                              -- is work the engagement answered and the other is
                              -- work this installation could never start, and an
                              -- operator reading a lap needs to tell them apart.
                              'retired_unready', n_retired,
                              'edges_derived', edges -> 'derived',
                              'edges_withdrawn', edges -> 'withdrawn',
                              'unlock_candidates', unlocks -> 'candidates',
                              'unlocks_derived', unlocks -> 'derived',
                              'unlocks_withdrawn', unlocks -> 'withdrawn',
                              'claims_graded', hunts -> 'graded',
                              'hunts_derived', hunts -> 'derived',
                              'hunts_deferred', hunts -> 'deferred',
                              'performances_derived', performances -> 'derived',
                              'performances_deferred', performances -> 'deferred',
                              'impact_runs_derived', impact_runs -> 'derived',
                              'impact_runs_deferred', impact_runs -> 'deferred',
                              'conclusions_derived', conclusions -> 'derived',
                              'conclusions_deferred', conclusions -> 'deferred',
                              'bands_derived', bands -> 'derived',
                              'bands_deferred', bands -> 'deferred',
                              'impacts_derived', impacts -> 'derived',
                              'impacts_deferred', impacts -> 'deferred');
END
 $function$;


-- ===========================================================================
-- 5. The arm that makes the empty graph stop reading as green
-- ===========================================================================
-- Ticket 226's fourth acceptance line. Replaced whole with one arm added; (a)
-- to (g) are the live text.

CREATE OR REPLACE FUNCTION public.check_kill_chains()
 RETURNS TABLE(problem text, detail text)
 LANGUAGE sql
 STABLE
AS $function$
    WITH RECURSIVE walk AS (
        SELECT e.chain_id, e.from_stamp_id AS root, e.to_stamp_id AS at
          FROM chain_edges e
         UNION ALL
        SELECT w.chain_id, w.root, e.to_stamp_id
          FROM walk w
          JOIN chain_edges e ON e.chain_id = w.chain_id AND e.from_stamp_id = w.at
    ) CYCLE at SET looped USING trail
    -- (a) a chain whose digest no longer covers what it says
    SELECT 'chain_digest_disagrees_with_its_source'::text, c.label
      FROM chains c WHERE c.source_sha256 <> equivalence_key(c.source)
UNION ALL
    -- (b) criterion 6's empty graph, asked of the corpus. A chain of fewer than
    --     two steps is the row a vacuous soundness answer would be about, and
    --     the one shape of this table that would make every rule below it true.
    SELECT 'chain_composes_fewer_than_two_steps', c.label
      FROM chains c
     WHERE (SELECT count(*) FROM chain_steps cs WHERE cs.chain_id = c.id) < 2
UNION ALL
    -- (c) criterion 2: a stored edge the stamps do not agree with. The edges are
    --     derived once and read many times, so this is the question of whether
    --     what was derived is still what would be derived.
    SELECT 'chain_edge_is_not_what_the_stamps_say', c.label || ' ' || e.capability
      FROM chain_edges e
      JOIN chains c ON c.id = e.chain_id
      JOIN pivot_stamps u ON u.id = e.from_stamp_id
      JOIN pivot_stamps d ON d.id = e.to_stamp_id
     WHERE u.provides <> e.capability OR NOT (e.capability = ANY (d.requires))
UNION ALL
    -- (d) criterion 3's vocabulary mismatch, as a corpus fact
    SELECT 'chain_composes_two_vocabularies', c.label
      FROM chains c JOIN chain_steps cs ON cs.chain_id = c.id
      JOIN pivot_stamps s ON s.id = cs.stamp_id
     GROUP BY c.label
    HAVING count(DISTINCT s.vocabulary_sha256) > 1
UNION ALL
    -- (e) criterion 1: a chain no `chain.built` Event attributes to the runtime.
    --     026's guard makes an actor authentic at the moment of writing; this
    --     asks after the fact, so a chain whose Event says something else and a
    --     chain with no Event are one answer.
    SELECT 'chain_was_not_built_by_the_runtime', c.label
      FROM chains c
     WHERE NOT EXISTS (SELECT 1 FROM events ev
                        WHERE ev.subject_id = c.id
                          AND ev.type = 'chain.built'
                          AND ev.actor_kind = 'runtime')
UNION ALL
    -- (f) criterion 3: a step requiring a capability nothing in its own chain
    --     brings it and the chain did not start with. The stored counterpart of
    --     the rule the builder refuses on, asked of the rows rather than of the
    --     proposal, because a chain whose requirements stopped being covered is
    --     a chain that composes over a gap.
    SELECT 'chain_step_requires_what_nothing_supplies',
           c.label || ' ' || s.label || ' ' || wanted.need
      FROM chain_steps cs
      JOIN chains c ON c.id = cs.chain_id
      JOIN pivot_stamps s ON s.id = cs.stamp_id
      CROSS JOIN LATERAL unnest(s.requires) AS wanted(need)
     WHERE NOT (wanted.need = ANY (c.entry))
       AND NOT EXISTS (SELECT 1 FROM chain_edges e
                        WHERE e.chain_id = cs.chain_id
                          AND e.to_stamp_id = cs.stamp_id
                          AND e.capability = wanted.need)
UNION ALL
    -- (g) criterion 3's cycle, asked of the stored edges. The builder refuses
    --     one and nothing edits an edge afterwards, so a cycle here is a row
    --     that did not come through the verb.
    SELECT DISTINCT 'chain_contains_a_cycle', c.label
      FROM walk w JOIN chains c ON c.id = w.chain_id
     WHERE w.root = w.at
UNION ALL
    -- (h) ticket 226. Every arm above is `FROM chains` or `FROM chain_edges`,
    --     so an empty table satisfies all seven of them: on 2026-08-30 this
    --     corpus had run 197 laps with zero rows in every table under this
    --     check and the check had never said a word. That is what "vacuously
    --     green" means, and this arm is what ends it.
    --
    --     WHAT IT DOES NOT ASSERT, and why. Not "a validated Finding has a
    --     chain". `build_kill_chain` refuses a proposal of fewer than two
    --     members, so a Program holding one Finding may compose no chain and be
    --     entirely healthy; that arm could never go green and would be a worse
    --     lie than silence. Not "a validated Finding has an impact
    --     demonstration" either -- a child that reads a Finding and says no
    --     impact class fits it has answered correctly, and an arm that refused
    --     that answer would halt the harness over a run that did its job.
    --
    --     WHAT IT ASSERTS. The pair: this Program is in the state the empty
    --     graph is a symptom of -- it holds a Finding a validation confirmed
    --     and no chain at all -- AND the runtime has no caller left that could
    --     ever fill it. Two halves because either alone is wrong. The state
    --     half fires the moment a Finding is validated, before the impact lane
    --     has had a turn, and a standing check that returns rows refuses every
    --     pass, so that arm would halt the campaign rather than report on it.
    --     The code half alone would be a lint about a function nobody had asked
    --     to run.
    --
    --     Read off the text of `rank_pass` because that is where the wiring
    --     lives and the wiring is the thing that was missing: the shape of
    --     `check_chain_unlocks` arm (d), which asks the same kind of question
    --     of `rk2_chain_unlock_frontier`. Comments are stripped first, for
    --     `check_scheduler_closure` arm (g)'s reason -- an explanation of why a
    --     call is there is not the call.
    SELECT 'validated_finding_under_a_runtime_that_derives_no_impact',
           f.label || ': rank_pass no longer calls ' || w.callee
                   || ' and this Program holds no chain'
      FROM findings f
      CROSS JOIN unnest(ARRAY['derive_impact_specifications',
                              'derive_impact_performances']) AS w(callee)
     WHERE f.status IN ('validated', 'reported')
       AND NOT EXISTS (SELECT 1 FROM chains c WHERE c.program_id = f.program_id)
       AND EXISTS (SELECT 1 FROM pg_proc p
                    WHERE p.pronamespace = 'public'::regnamespace
                      AND p.proname = 'rank_pass'
                      AND regexp_replace(p.prosrc, '--[^' || chr(10) || ']*',
                                         '', 'g') !~ w.callee)
$function$;


-- ===========================================================================
-- 6. The register
-- ===========================================================================
-- Ticket 66's rule, paid the way 221 paid it: a verb the runtime may execute has
-- one row in `runtime_verb_surface`, and a grant with no row is a grant nobody
-- declared. The three replaced functions keep the rows they already have -- a
-- replacement is the same verb.

INSERT INTO runtime_verb_surface (verb, added_by, note) VALUES
    ('rk2_task_proves_impact(tasks)', '226',
     'whether a conclude Task naming a Finding was opened to prove its impact '
     'rather than to band it, which is whether it was opened after the band'),
    ('rk2_impact_specification_frontier(uuid)', '226',
     'the validated Findings somebody has banded whose impact nobody has specified '
     'or demonstrated, and that no conclude Task has named since the band'),
    ('derive_impact_specifications()', '226',
     'opens the conclude Task that reaches propose_impact_task, carrying finding_id '
     'like the band Task and told from it by the Finding''s own severity_basis')
ON CONFLICT (verb) DO NOTHING;
