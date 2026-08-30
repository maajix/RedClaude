-- The reproduction window is the validation lane's own                (ticket 223)
--
-- `check_finding_candidates` (`20260815T120000Z:970-981`) reports a Finding whose
-- claim is not `supported`, and `reopen_for_reproduction`
-- (`20260815T180000Z:783`) moves exactly that claim `supported -> testable` as
-- the first half of `rk finding validate`. The two were written three days apart
-- and the second one priced the collision in its own header
-- (`20260815T180000Z:777-782`):
--
--     The window between this verb and the replay's close is a Finding on a
--     claim that is not `supported`, which 036's `finding_claim_not_supported`
--     reports and is meant to ... It is not narrowed here. The runtime holds the
--     window inside one command, and an operator who sees it has seen something
--     true.
--
-- The premise is false in this runtime, and ticket 222 is why: the replay half
-- never runs. `open_test_replay` (`20260815T000000Z:1165-1168`) requires an open
-- `agent_runs` row on the named session, `rk finding validate` opens none, and
-- the one process that could open one is the hunt -- which `one_peer`
-- (`isolation.py:1738-1764`) refuses to run beside a second child. So the command
-- opens the window and returns, and nothing in this tree closes it.
--
-- A window nothing closes is not a window. Measured on `rk2here` after one
-- `rk finding validate` at 00:08:37 on 2026-08-30:
--
--     problem                     | subject | detail
--     finding_claim_not_supported | F8      | H160 is testable
--
--     lap 01 -> refused | exit 9
--     integrity_failed | standing:finding_candidates
--
-- The standing family gates every pass and this row is not program-scoped
-- (`standing_checks.program_scoped` is false), so one Program that asked for a
-- validation stopped every Program in the database -- the same sentence
-- `hypothesis_transition_refusal` already carries about its own predecessor.
--
-- What is narrowed, and what is not. The rule keeps its whole reach except for
-- the one shape the validation lane writes on purpose: a claim in `testable` or
-- `testing` whose Finding holds a `queued` or `running` row in
-- `validation_queue`. That claim is on its way back through the replay the lane
-- asked for, and `reopen_for_reproduction` is the only thing that put it there.
-- A claim reopened by 034's negative-knowledge retest still reports, a claim that
-- came back `refuted` still reports, and a Finding on a claim nobody asked to
-- validate still reports. State `done` reports too: a lane that finished and left
-- the claim unsupported is the refutation the packet is meant to show, not a
-- window.
--
-- This does not fix 222 and does not pretend to. It stops one unrunnable command
-- from taking the runtime with it, so the hunt that owns the replay can run at
-- all. The stale window itself is 222's to close.

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
    -- Except when the validation lane is what reopened it. Ticket 223:
    -- `reopen_for_reproduction` moves the claim to `testable` and the replay it
    -- expects to move it back does not run, so the row is permanent rather than
    -- momentary and every pass in the database refuses over it. The exclusion is
    -- the exact shape that verb writes and nothing wider.
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
    'supported outside the validation lane''s own reproduction window, a '
    'candidate stating impact, two Findings on one cell, and a proposal record '
    'that disagrees with the Findings it names. And one thing that is about the '
    'function rather than the rows: whether it still takes the lock that keeps '
    'two opens off one cell.';

UPDATE standing_checks
   SET note = 'every Finding names the holding Test run it was opened from, rests on a claim that is still supported unless the validation lane reopened it to reproduce, states no impact it has not demonstrated, and shares its cell with no other -- and the open still takes the lock that keeps it that way'
 WHERE name = 'finding_candidates';
