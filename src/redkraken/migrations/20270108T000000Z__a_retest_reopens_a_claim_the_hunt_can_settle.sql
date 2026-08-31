-- A retest reopens a claim the hunt can settle                        (ticket 230)
--
-- Ticket 223 narrowed `check_finding_candidates` rule 3 for the validation
-- lane's reproduction window and said, twice, what it was leaving out
-- (`20261223T000000Z:42-43`):
--
--     A claim reopened by 034's negative-knowledge retest still reports, a
--     claim that came back `refuted` still reports, ...
--
-- Measured on `rk2here` on 2026-08-31, that sentence stops the runtime. The
-- watch lane -- `refresh_negative_knowledge()` step (2),
-- `20260814T080000Z:775-786` -- moved H215 `supported -> testable` at
-- 03:25:29.444997 because the watched Application's response fingerprint had
-- changed. F12 rests on H215 and is `candidate`:
--
--     problem                     | subject | detail
--     finding_claim_not_supported | F12     | H215 is testable
--
--     lap 01 -> refused | ok False | exit 9
--     integrity_failed | standing:finding_candidates
--
-- `standing_checks.program_scoped` is false for this row, so one Program's
-- retest stopped every Program in the database, and the supervisor stood down
-- after four restarts inside fifteen minutes.
--
-- The difference from 223, and the reason this file is two changes rather than
-- one: nothing in this tree can close the window the watch lane opens.
--
--   * `rk2_hypothesis_hunt_frontier` (`20261012T000000Z:138-152`) refuses a
--     claim that any `hunt` Task names in any status. A claim that reached
--     `supported` has one.
--   * `rk2_test_performance_frontier` (`20261014T000000Z:284-304`) refuses a
--     Test that has ever been replayed or that any `perform` Task names. A
--     claim that reached `supported` did so through a replay, so its Test has
--     both.
--   * There is no `retest` Task kind, and nothing clears
--     `hypothesis_retest_triggers.fired_at` -- `arm_retest_watches` is
--     idempotent and leaves a fired watch alone (`20260927T010000Z:292`).
--
-- So narrowing the check alone would hide F12 for good and leave H215 in
-- `testable` for good, which is the shape 223 put in its own title. The way
-- back exists and is simply never entered: `open_test_replay` refuses only a
-- replay that is in flight (`tr.status = 'running'`) and asks only that the
-- claim be `testable`, and `close_test_replay` settles it again
-- (`20260815T000000Z:1857-1859`, last overridden `20260816T000000Z:1125-1129`).
--
-- This file lets the Test be performed again, and keeps the runtime alive
-- while it is. Both halves or neither: the exclusion in rule 3 is only honest
-- because the frontier guarantees something closes it.
--
-- Measured read-only against the live rows before this was written: the new
-- exclusion silences exactly one Finding (F12), and the widened frontier
-- admits ten Tests, TST111 among them.


-- ---------------------------------------------------------------------------
-- 1. The one predicate both halves read.
--
-- Two copies of this that have to agree is the defect this function exists to
-- avoid: the check would be hiding a window the frontier had already closed,
-- or the frontier would be minting work for a window the check still refuses.

CREATE FUNCTION rk2_retest_reopened_at(p_hypothesis uuid, p_program uuid)
RETURNS timestamptz
LANGUAGE sql STABLE AS $fn$
    SELECT max(rt.fired_at)
      FROM hypothesis_retest_triggers rt
     WHERE rt.hypothesis_id = p_hypothesis
       AND rt.program_id    = p_program
       AND rt.fired_at IS NOT NULL
       AND rt.fired_at > coalesce(
             (SELECT max(ht.at) FROM hypothesis_transitions ht
               WHERE ht.hypothesis_id = p_hypothesis
                 AND ht.to_status IN ('supported', 'refuted', 'inconclusive')),
             '-infinity'::timestamptz)
$fn$;

COMMENT ON FUNCTION rk2_retest_reopened_at(uuid, uuid) IS
    'When the retest lane last reopened this claim without it settling since, '
    'and NULL when no such reopen stands. Read off `fired_at` against the last '
    'settling transition rather than off `hypotheses.status_changed_at`, '
    'because the window has to hold across `testable -> testing` as well: a '
    'claim moves to `testing` the moment the replay that closes the window '
    'opens, and a `status_changed_at` comparison would drop the exclusion in '
    'the middle of the replay it is waiting for. Self-closing -- '
    '`close_test_replay` writes a settling transition later than `fired_at` '
    'and this answers NULL again, so nothing has to clear `fired_at`.';

REVOKE ALL ON FUNCTION rk2_retest_reopened_at(uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION rk2_retest_reopened_at(uuid, uuid) TO rk2_runtime;

-- Closed to PUBLIC and held by the runtime is exactly the pair 066's registry
-- exists to name: both callers below are read by the runtime connection, so
-- without this row `runtime_holds_undeclared_verb` refuses every pass.
INSERT INTO runtime_verb_surface (verb, added_by, note) VALUES
    ('rk2_retest_reopened_at(uuid, uuid)', '230',
     'when the retest lane reopened a claim without it settling since; read by the performance frontier to put the Test back and by check_finding_candidates to stay silent until it does');


-- ---------------------------------------------------------------------------
-- 2. The window closes because the Test is performed again.
--
-- The two `NOT EXISTS` keep their whole reach; what changes is that they count
-- only what happened since the reopen. With no reopen standing the cut point
-- is `-infinity` and both read exactly as they did, which is what this file's
-- self-check holds onto.

CREATE OR REPLACE FUNCTION rk2_test_performance_frontier(p_program_id uuid)
RETURNS TABLE (test_id uuid, hypothesis_id uuid, subject_entity_id uuid,
               created_at timestamptz)
LANGUAGE sql STABLE AS $fn$
    SELECT ts.id, ts.hypothesis_id, h.subject_entity_id, ts.created_at
      FROM tests ts
      JOIN hypotheses h ON h.id = ts.hypothesis_id AND h.program_id = ts.program_id
      JOIN entities e ON e.id = h.subject_entity_id AND e.program_id = h.program_id
     WHERE ts.program_id = p_program_id
       AND ts.impact_class IS NULL
       AND h.status = 'testable'
       AND h.superseded_by IS NULL
       AND e.in_scope
       AND NOT EXISTS (SELECT 1 FROM tests later
                        WHERE later.supersedes_test_id = ts.id)
       AND NOT EXISTS (SELECT 1 FROM test_replays tp
                        WHERE tp.test_id = ts.id
                          AND tp.started_at > coalesce(
                                rk2_retest_reopened_at(h.id, h.program_id),
                                '-infinity'::timestamptz))
       AND NOT EXISTS (SELECT 1 FROM tasks k
                        WHERE k.program_id = ts.program_id
                          AND k.kind = 'perform'
                          AND k.test_id = ts.id
                          AND k.created_at > coalesce(
                                rk2_retest_reopened_at(h.id, h.program_id),
                                '-infinity'::timestamptz));
$fn$;

COMMENT ON FUNCTION rk2_test_performance_frontier(uuid) IS
    'The Tests of a Program that state no impact, settle a live testable claim '
    'about an in-scope Entity, are not superseded, and that no replay and no '
    '`perform` Task has answered since the claim was last opened for work. Any '
    'status rather than a live one, for the reason the hunt frontier gives: a '
    'Task that ran and finished is an answer, and deriving it again is a loop. '
    'Ticket 230 made "since" mean something: a retest that reopens a settled '
    'claim puts its Test back here, because a fingerprint that moved is the '
    'one case where the old answer is no longer an answer.';


-- ---------------------------------------------------------------------------
-- 3. The runtime stays up while the window is open.
--
-- Rule 3 gains a second exclusion beside 223's. Everything else in the
-- function is 223's, unchanged -- a `CREATE OR REPLACE` replaces the body
-- whole, so the other eight arms are carried across verbatim.

CREATE OR REPLACE FUNCTION check_finding_candidates()
RETURNS TABLE (problem text, subject text, detail text)
LANGUAGE sql STABLE AS $fn$
    -- A Finding that names no holding run. Unreachable through `open_finding`
    -- and reachable by anyone holding INSERT, which is the case the check is
    -- for: the birth guard is a trigger, and a later migration that disables it
    -- to backfill something leaves no other trace.
    SELECT 'finding_without_holding_run', f.label,
           'created ' || f.created_at::date::text || ' and names no Test run'
      FROM findings f
     WHERE f.opened_by_test_run_id IS NULL

    UNION ALL
    -- A Finding whose holding run stopped holding. `test_runs` is immutable so
    -- the outcome cannot have moved, but the run can be repointed by a Finding
    -- that was written around the function.
    SELECT 'finding_run_does_not_hold', f.label,
           'rests on a run that concluded ' || run.outcome
      FROM findings f JOIN test_runs run ON run.id = f.opened_by_test_run_id
     WHERE run.outcome <> 'holds'

    UNION ALL
    -- A Finding resting on a claim that is no longer supported. Not an error in
    -- itself -- 034 can reopen a claim, and a Finding on a reopened claim is
    -- exactly what an operator should be looking at -- but it is never nothing.
    --
    -- Except when a lane of this runtime is what reopened it, on purpose, and
    -- something is going to close it again. Two such lanes, and no more:
    --
    -- Ticket 223: `reopen_for_reproduction` moves the claim to `testable` and
    -- the replay it expects to move it back does not run, so the row is
    -- permanent rather than momentary and every pass in the database refuses
    -- over it. The exclusion is the exact shape that verb writes.
    --
    -- Ticket 230: the watch lane moves the claim to `testable` when a watched
    -- fingerprint changes. Until this file, nothing derived work from that and
    -- the claim stayed reopened for good -- so the exclusion is paired with
    -- `rk2_test_performance_frontier` putting the Test back on the frontier,
    -- and it lapses of its own accord the moment the replay settles the claim.
    --
    -- Still reported, each deliberately: a claim that came back `refuted`,
    -- which is neither `testable` nor `testing`; a Finding on a claim nobody
    -- asked to reopen; and a validation lane that finished and left the claim
    -- unsupported, which is the refutation the packet is meant to show.
    SELECT 'finding_claim_not_supported', f.label,
           h.label || ' is ' || h.status
      FROM findings f
      JOIN finding_hypotheses fh ON fh.finding_id = f.id
      JOIN hypotheses h          ON h.id = fh.hypothesis_id
     WHERE f.status IN ('candidate', 'validating') AND h.status <> 'supported'
       AND NOT (h.status IN ('testable', 'testing')
                AND EXISTS (SELECT 1 FROM validation_queue vq
                             WHERE vq.finding_id = f.id
                               AND vq.program_id = f.program_id
                               AND vq.state IN ('queued', 'running')))
       AND NOT (h.status IN ('testable', 'testing')
                AND rk2_retest_reopened_at(h.id, f.program_id) IS NOT NULL)

    UNION ALL
    -- A candidate carrying a severity it has not earned. The CHECK makes the
    -- pairing unreachable; this reports one that exists, for the reason above.
    SELECT 'candidate_states_impact', f.label,
           'severity ' || f.severity || ' on basis ' || f.severity_basis
      FROM findings f
     WHERE f.status = 'candidate'
       AND (f.severity <> 'info' OR f.severity_basis <> 'undetermined')

    UNION ALL
    -- Two live Findings on one cell. The index makes it unreachable, and the
    -- index is partial -- a later ticket that learns to unmark a duplicate
    -- brings a second row back onto the cell without touching this file.
    SELECT 'findings_share_a_cell',
           string_agg(f.label, ', ' ORDER BY f.label),
           min(coalesce(f.property_class, '(none)'))
      FROM findings f
     WHERE f.duplicate_of_finding_id IS NULL AND f.status <> 'rejected'
     GROUP BY rk2_finding_cell(f.program_id, f.property_class, f.subject_entity_id,
                               f.identity_a_entity_id, f.identity_b_entity_id)
    HAVING count(*) > 1

    UNION ALL
    -- The lock, asserted rather than commented, for 023's reason: the race it
    -- closes is invisible in every test that runs one transaction at a time, so
    -- a later edit that drops it looks like a simplification and reports
    -- nothing until two hunters settle on one cell at once.
    SELECT 'open_finding_takes_no_cell_lock', 'open_finding',
           'the empty-cell race is open again'
      FROM pg_proc pr
     WHERE pr.pronamespace = 'public'::regnamespace AND pr.proname = 'open_finding'
       AND pr.prosrc !~ 'pg_advisory_xact_lock'

    UNION ALL
    -- A refused proposal that reached a Finding after all. The CHECK makes it
    -- unreachable; the reverse -- an accepted proposal naming no Finding -- is
    -- not reported, because 047's importer will write accepted rows for
    -- Findings it did not open and the proposal is still the honest record of
    -- what was asked.
    SELECT 'proposal_disagrees_with_findings', fp.id::text,
           'refused and naming ' || f.label
      FROM finding_proposals fp JOIN findings f ON f.id = fp.finding_id
     WHERE fp.outcome = 'refused'

    UNION ALL
    -- A stored behaviour the shape rule would refuse, for the reason 035 gave:
    -- the constraint is a function, and a later ticket that tightens it does
    -- not revalidate what is already stored.
    SELECT 'finding_demonstrated_refused', f.label,
           rk2_demonstrated_problem(f.demonstrated)
      FROM findings f
     WHERE f.demonstrated IS NOT NULL
       AND rk2_demonstrated_problem(f.demonstrated) IS NOT NULL
$fn$;

COMMENT ON FUNCTION check_finding_candidates() IS
    'What a Finding looks like when it was not opened by `open_finding`: no '
    'holding run, a run that did not hold, a claim that stopped being '
    'supported outside a reopen one of this runtime''s own lanes is going to '
    'close, a candidate stating impact, two Findings on one cell, and a '
    'proposal record that disagrees with the Findings it names. And one thing '
    'that is about the function rather than the rows: whether it still takes '
    'the lock that keeps two opens off one cell.';

UPDATE standing_checks
   SET note = 'every Finding names the holding Test run it was opened from, rests on a claim that is still supported unless the validation lane reopened it to reproduce or the retest lane reopened it and its Test is back on the performance frontier, states no impact it has not demonstrated, and shares its cell with no other -- and the open still takes the lock that keeps it that way'
 WHERE name = 'finding_candidates';


-- ---------------------------------------------------------------------------
-- What this file wrote, asserted rather than assumed.

DO $$
DECLARE
    frontier text;
    candidates text;
BEGIN
    IF to_regprocedure('rk2_retest_reopened_at(uuid, uuid)') IS NULL THEN
        RAISE EXCEPTION 'rk2_retest_reopened_at was not created';
    END IF;

    -- The reason the function exists: with no reopen standing it answers NULL,
    -- so every `coalesce(..., '-infinity')` above collapses to what the two
    -- `NOT EXISTS` said before this file.
    IF rk2_retest_reopened_at(uuidv7(), uuidv7()) IS NOT NULL THEN
        RAISE EXCEPTION 'rk2_retest_reopened_at answers a window on a claim that has none';
    END IF;

    IF NOT has_function_privilege('rk2_runtime',
                                  'rk2_retest_reopened_at(uuid, uuid)', 'EXECUTE') THEN
        RAISE EXCEPTION 'rk2_runtime cannot execute rk2_retest_reopened_at, and both callers run as it';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM runtime_verb_surface
                    WHERE verb = 'rk2_retest_reopened_at(uuid, uuid)') THEN
        RAISE EXCEPTION 'the verb is held by the runtime and not declared, which stops every pass';
    END IF;

    SELECT prosrc INTO frontier FROM pg_proc
     WHERE pronamespace = 'public'::regnamespace AND proname = 'rk2_test_performance_frontier';
    IF frontier !~ 'rk2_retest_reopened_at' THEN
        RAISE EXCEPTION 'the performance frontier does not read the reopen, so nothing closes the window';
    END IF;

    SELECT prosrc INTO candidates FROM pg_proc
     WHERE pronamespace = 'public'::regnamespace AND proname = 'check_finding_candidates';
    IF candidates !~ 'rk2_retest_reopened_at' THEN
        RAISE EXCEPTION 'rule 3 does not read the reopen, so the runtime still stops over it';
    END IF;
    IF candidates !~ 'validation_queue' THEN
        RAISE EXCEPTION 'rule 3 lost ticket 223''s exclusion';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM standing_checks
                    WHERE name = 'finding_candidates' AND note LIKE '%retest lane%') THEN
        RAISE EXCEPTION 'the standing check note does not say what it now excludes';
    END IF;
END $$;
