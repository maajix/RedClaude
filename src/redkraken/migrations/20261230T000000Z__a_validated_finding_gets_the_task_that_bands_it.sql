-- A validated Finding gets the Task that bands it                   (ticket 221)
--
-- `state_severity` is the only writer of `findings.severity` and it refuses a
-- Finding that is not `validated`. Ticket 221 measured that refusal against a
-- live Program and read it correctly: the order is right, and what was missing
-- was upstream. Ticket 105 built the ask, ticket 224 shape 1 built the drain,
-- and on 2026-08-30 `F9` on `rk2here` became the first `validated` Finding this
-- harness has held.
--
-- It is still `info`, because nothing puts a run in front of a validated
-- Finding. `rk2_finding_frontier` is the only producer of `conclude` Tasks and
-- its last two clauses exclude exactly this row: a hypothesis that already
-- carries a Finding, and a hypothesis a `conclude` Task has already named. `F9`
-- is both. So `state_severity` is served, described, granted and unreachable.
--
-- What this file adds is the second half of a walk the roster already describes.
-- `roster.py` says a `conclude` Task "runs from a validated Finding to the
-- impact specification, the severity band and the composed report", and that is
-- not what the frontier produces -- it produces the Task that runs from a
-- supported claim to a candidate Finding. Both are `conclude` and they are told
-- apart by `tasks.finding_id`, which is the column `validate` already reads for
-- the same question and which `tasks_live_dedup_idx` already discriminates on.
-- So a second `conclude` Task on one hypothesis is a distinct row without a new
-- index, and a new Task kind would have cost a `task_kinds` row, a
-- `role_task_kinds` row, cost and time priors, lane quota rows, a `MISSIONS`
-- sentence and a `web_hunter.task_kinds` change -- for a run that reaches the
-- same three verbs through the same tool group.
--
-- Scope: the band and nothing else. `open_impact_task` and
-- `compose_finding_report` are the other two verbs of `state.conclude` and they
-- are their own tickets; a Task asked for three things it can only do one of is
-- a Task that ends having done none.

-- ===========================================================================
-- 1. The frontier, and the derivation that spends it
-- ===========================================================================

CREATE FUNCTION rk2_severity_frontier(p_program_id uuid)
RETURNS TABLE (finding_id uuid, hypothesis_id uuid, subject_entity_id uuid,
               status_changed_at timestamptz)
LANGUAGE sql STABLE AS $fn$
    SELECT f.id, fh.hypothesis_id, f.subject_entity_id, f.status_changed_at
      FROM findings f
      JOIN entities e ON e.id = f.subject_entity_id AND e.program_id = f.program_id
      -- One claim, and the lowest-ordered of them when a Finding rests on
      -- several. The Task needs a hypothesis because `ready_for`'s `conclude`
      -- arm asks for one first, and because the child is told which claim it is
      -- banding. Which of several is not a judgement this function should make,
      -- so it takes the deterministic one rather than the interesting one.
      JOIN LATERAL (
             SELECT x.hypothesis_id FROM finding_hypotheses x
              WHERE x.finding_id = f.id AND x.program_id = f.program_id
              ORDER BY x.hypothesis_id LIMIT 1
           ) fh ON true
     WHERE f.program_id = p_program_id
       AND f.status = 'validated'
       -- The column, not `severity = 'info'`. `info` is the default and means
       -- nobody judged; `severity_basis` is what `state_severity` writes in the
       -- same statement as the band, so it cannot drift from the statement row
       -- -- and it is the one place this schema distinguishes unjudged from
       -- judged harmless.
       AND f.severity_basis = 'undetermined'
       AND e.in_scope
       AND rk2_subject_addressable(f.subject_entity_id) IS TRUE
       AND EXISTS (SELECT 1 FROM hypotheses h
                    WHERE h.id = fh.hypothesis_id AND h.status = 'supported')
       -- In any status, which is the rule `rk2_finding_frontier` uses and the
       -- reason it gives: every clause here is a refusal `state_severity` would
       -- otherwise make after the work. It also means an abandoned band Task is
       -- not respawned, and that is the sibling's behaviour rather than an
       -- oversight -- a Finding stuck unbanded is a fact an operator can read,
       -- and a Task the pass re-derives forever is not.
       AND NOT EXISTS (SELECT 1 FROM tasks k
                        WHERE k.program_id = f.program_id
                          AND k.kind = 'conclude'
                          AND k.finding_id = f.id);
$fn$;

COMMENT ON FUNCTION rk2_severity_frontier(uuid) IS
  'The Findings of a Program a validation confirmed, that nobody has stated a band about, whose subject is in scope and addressable, that rest on a claim still supported, and that no `conclude` Task already names by finding_id in any status. Shaped after `rk2_finding_frontier` and refusing for the same reason: every clause is one `state_severity` would otherwise make after the work.';

REVOKE ALL ON FUNCTION rk2_severity_frontier(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rk2_severity_frontier(uuid) TO rk2_runtime;


CREATE FUNCTION derive_finding_bands() RETURNS jsonb
LANGUAGE plpgsql AS $fn$
DECLARE
    p        uuid := rk2_program_required();
    ceiling  smallint;
    n_wanted bigint := 0;
    n_tasks  bigint := 0;
BEGIN
    -- The same ceiling as `derive_finding_claims`, and deliberately not a
    -- second column. Both derivations open `conclude` Tasks, so one bound over
    -- both is the honest reading of "how many conclusions may a pass derive".
    -- A pass that spends it all on claims derives no bands and the next pass
    -- derives them, which is the deferral the return value already reports.
    SELECT w.max_conclusions_derived_per_pass INTO ceiling
      FROM scheduler_weights w WHERE w.active;
    IF NOT FOUND THEN RAISE EXCEPTION 'no active scheduler_weights row'; END IF;

    SELECT count(*) INTO n_wanted FROM rk2_severity_frontier(p);

    -- Oldest validation first, for `derive_finding_claims`'s reason: these
    -- Tasks do not exist yet, so there is no ranking to prefer one by, and
    -- arrival order is the one deterministic answer -- which is what makes the
    -- ceiling reproducible.
    WITH wanted AS (
        SELECT fr.finding_id, fr.hypothesis_id, fr.subject_entity_id
          FROM rk2_severity_frontier(p) fr
         ORDER BY fr.status_changed_at, fr.finding_id
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

COMMENT ON FUNCTION derive_finding_bands() IS
  'Ticket 221. Opens one `conclude` Task per validated Finding nobody has banded, carrying `finding_id` -- which is what tells this shape from ticket 156''s, in `ready_for`, in `novelty_for` and in `tasks_live_dedup_idx`. Bounded by `max_conclusions_derived_per_pass`, shared with `derive_finding_claims` because both open the same kind.';

REVOKE ALL ON FUNCTION derive_finding_bands() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION derive_finding_bands() TO rk2_runtime;


-- ===========================================================================
-- 2. The three functions that would otherwise end this Task before it ran
-- ===========================================================================
-- Each is replaced whole because that is how this corpus edits a function --
-- `rank_pass` alone has been replaced by seven earlier files. The bodies below
-- are the live definitions with one arm changed; the changed arm carries the
-- ticket number and says what it splits on.
--
-- Without all three, the Task this file derives is abandoned before it is ever
-- offered. `ready_for` returns `conclude.already_found`, because the Finding it
-- was opened about is the edge that answer reads. `novelty_for` returns 0 for
-- the same edge, and `cancel_reason_for`'s general rule reads a zero as nothing
-- left to learn and abandons the row as `answered` on the first pass -- which
-- is ticket 152's measurement against `perform`, in a new place.

CREATE OR REPLACE FUNCTION public.ready_for(t tasks)
 RETURNS text
 LANGUAGE plpgsql
 STABLE
AS $function$
DECLARE ok boolean;
BEGIN
    IF t.subject_entity_id IS NOT NULL THEN
        SELECT e.in_scope INTO ok FROM entities e WHERE e.id = t.subject_entity_id;
        IF NOT coalesce(ok, false) THEN RETURN t.kind || '.subject_not_in_scope'; END IF;
    END IF;

    IF t.kind = 'recon' THEN
        IF t.subject_entity_id IS NULL THEN RETURN 'recon.no_subject'; END IF;
        IF rk2_subject_addressable(t.subject_entity_id) IS NOT TRUE THEN
            RETURN 'recon.no_address';
        END IF;
        RETURN NULL;

    ELSIF t.kind = 'hunt' THEN
        IF t.hypothesis_id IS NULL THEN RETURN 'hunt.no_hypothesis'; END IF;
        IF NOT EXISTS (SELECT 1 FROM hypotheses h
                        WHERE h.id = t.hypothesis_id AND h.status = 'testable') THEN
            RETURN 'hunt.hypothesis_not_testable';
        END IF;
        -- Asked only where there is a subject to ask it about. A hunt Task
        -- with none is undispatchable too, but it is not this predicate's
        -- sentence to say so: `derive_chain_unlocks` takes the subject off the
        -- frontier and a NULL there is the runtime's case, ended by
        -- `retire_task` at the point the URL comes back missing.
        IF t.subject_entity_id IS NOT NULL
           AND rk2_subject_addressable(t.subject_entity_id) IS NOT TRUE THEN
            RETURN 'hunt.no_address';
        END IF;
        RETURN NULL;

    ELSIF t.kind = 'analyze' THEN
        -- "at least one agent-visible artifact reachable from an observation on
        -- the subject". Reachability is ticket 12's `artifact_refs` bridge:
        -- `artifacts` is content-addressed and program-global, so a bare hash
        -- lookup would cross programs.
        IF NOT EXISTS (
             SELECT 1
               FROM observations o
               JOIN receipts r     ON r.id = o.receipt_id
               JOIN artifact_refs x ON x.ref_label = r.label
                                   AND x.program_id = o.program_id
               JOIN artifacts a    ON a.sha256 = x.sha256
              WHERE o.subject_entity_id = t.subject_entity_id
                AND a.visibility = 'agent_visible'
                AND NOT a.encrypted AND a.purged_at IS NULL) THEN
            RETURN 'analyze.no_agent_visible_artifact';
        END IF;
        RETURN NULL;

    ELSIF t.kind = 'perform' THEN
        IF t.test_id IS NULL THEN RETURN 'perform.no_test'; END IF;
        IF NOT EXISTS (SELECT 1 FROM tests ts
                         JOIN hypotheses h ON h.id = ts.hypothesis_id
                        WHERE ts.id = t.test_id AND h.status = 'testable') THEN
            RETURN 'perform.claim_not_testable';
        END IF;
        IF EXISTS (SELECT 1 FROM test_replays tp WHERE tp.test_id = t.test_id) THEN
            RETURN 'perform.already_performed';
        END IF;
        RETURN NULL;

    ELSIF t.kind = 'conclude' THEN
        IF t.hypothesis_id IS NULL THEN RETURN 'conclude.no_hypothesis'; END IF;
        IF NOT EXISTS (SELECT 1 FROM hypotheses h
                        WHERE h.id = t.hypothesis_id AND h.status = 'supported') THEN
            RETURN 'conclude.claim_not_supported';
        END IF;
        -- Ticket 221. Two shapes under one kind, told apart by `finding_id` --
        -- the column `validate` already uses for exactly this question. A Task
        -- carrying none is 156's: name the Finding this settled claim is one
        -- of, and an edge in `finding_hypotheses` means that work is done. A
        -- Task carrying one is this ticket's: state the band of a Finding a
        -- validation confirmed, and the same edge is its precondition rather
        -- than its refusal.
        IF t.finding_id IS NULL THEN
            IF EXISTS (SELECT 1 FROM finding_hypotheses fh
                        WHERE fh.hypothesis_id = t.hypothesis_id) THEN
                RETURN 'conclude.already_found';
            END IF;
        ELSIF NOT EXISTS (SELECT 1 FROM findings f
                           WHERE f.id = t.finding_id
                             AND f.status IN ('validated', 'reported')) THEN
            -- Not terminal, and `rk2_terminal_predicate` says so without a row:
            -- a candidate Finding is one a validation can still confirm, so a
            -- band Task that arrives early waits rather than ends.
            RETURN 'conclude.finding_not_validated';
        END IF;
        IF t.subject_entity_id IS NOT NULL
           AND rk2_subject_addressable(t.subject_entity_id) IS NOT TRUE THEN
            RETURN 'conclude.no_address';
        END IF;
        RETURN NULL;

    ELSIF t.kind = 'validate' THEN
        IF t.finding_id IS NULL THEN RETURN 'validate.no_finding'; END IF;
        IF NOT EXISTS (SELECT 1 FROM findings f
                        WHERE f.id = t.finding_id AND f.status = 'candidate') THEN
            RETURN 'validate.finding_not_candidate';
        END IF;
        IF NOT EXISTS (SELECT 1 FROM tests ts
                         JOIN finding_hypotheses fh ON fh.hypothesis_id = ts.hypothesis_id
                        WHERE fh.finding_id = t.finding_id) THEN
            RETURN 'validate.no_test_spec';
        END IF;
        RETURN NULL;

    ELSIF t.kind = 'report' THEN
        IF NOT EXISTS (SELECT 1 FROM findings f
                        WHERE f.program_id = t.program_id AND f.status = 'validated') THEN
            RETURN 'report.no_validated_finding';
        END IF;
        RETURN NULL;
    END IF;
    RETURN t.kind || '.unknown_kind';
END $function$;

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
    conclusions  jsonb;
    bands        jsonb;
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
        'finding_claims', conclusions,
        'finding_bands', bands,
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
                              'conclusions_derived', conclusions -> 'derived',
                              'conclusions_deferred', conclusions -> 'deferred',
                              'bands_derived', bands -> 'derived',
                              'bands_deferred', bands -> 'deferred');
END
 $function$;


-- ===========================================================================
-- 3. The register
-- ===========================================================================
-- Ticket 66's rule, paid the way `20261225T000000Z` paid it: a verb the runtime
-- may execute has one row in `runtime_verb_surface`, and a grant with no row is
-- a grant nobody declared. The three replaced functions keep the rows they
-- already have -- a replacement is the same verb.

INSERT INTO runtime_verb_surface (verb, added_by, note) VALUES
    ('rk2_severity_frontier(uuid)', '221',
     'the rows a band Task would be opened about: validated, unbanded, in scope, '
     'addressable, resting on a supported claim, and named by no conclude Task'),
    ('derive_finding_bands()', '221',
     'opens the conclude Task that reaches state_severity, carrying finding_id so '
     'that ready_for and novelty_for can tell it from the Task that names a Finding')
ON CONFLICT (verb) DO NOTHING;
