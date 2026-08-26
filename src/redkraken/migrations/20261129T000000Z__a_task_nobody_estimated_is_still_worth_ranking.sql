-- ---------------------------------------------------------------------------
-- 20261129T000000Z__a_task_nobody_estimated_is_still_worth_ranking.sql
--
-- The scheduler's value term, given a floor it can stand on.
--
-- Measured on `rk2here`, 2026-08-26, after a full sitting: 480 Tasks, 0 with a
-- priority. Every other derived column is filled -- all 480 carry a `novelty`,
-- a `safety_cost` and an `estimated_cost` -- and `priority` alone is NULL, on
-- every row this harness has ever written, in every database on this machine.
--
-- The chain is four links and each one is correct on its own:
--
--   * `tasks.expected_information_gain` and `tasks.potential_impact` are
--     model-estimated columns, and no verb was ever built that writes them.
--     Nothing in `src/redkraken/*.py` names either. Only `tests/` sets them,
--     which is why every unit test of the ranking passes.
--   * `value_for(t, w)` returns NULL when either is NULL -- deliberately, and
--     its comment says why: an unestimated Task is a different statement from
--     a worthless one.
--   * `rank_pass` writes `priority = NULL` when `direct_value` is NULL.
--   * `rank_candidates()` orders by `priority DESC NULLS LAST, created_at, id`,
--     so a queue of NULLs is a queue sorted by age.
--
-- The first recon Task of this engagement was created at 18:51:01.999922 and
-- the first hunt Task at 18:51:02.376201. Four tenths of a second decided eight
-- hours of a live campaign.
--
-- WHICH WAY OUT. Ticket 196 lists three. This is the second: a per-kind prior,
-- in the place `cost_prior` and `time_prior` already live, read the way
-- `cost_for` and `time_for` already read theirs. It is chosen over a verb
-- because the verb is a design question about where a model belongs in the
-- scheduler, and over dropping the term because gain and impact are the only
-- two factors that say what a Task is FOR -- novelty, cost, safety and unlock
-- are all statements about what it costs and whether it is new.
--
-- The column keeps its meaning. `coalesce(t.expected_information_gain, prior)`
-- reads the estimate when there is one, so the day a verb is built the priors
-- become what they say they are: a fallback, not a replacement. And NULL
-- survives for a kind nobody priced -- a new `kind` with no entry falls through
-- both coalesces and ranks NULL, which is the old behaviour and is now a
-- standing problem rather than a silence.
--
-- THE NUMBERS ARE UNVALIDATED, exactly as decision 16 says every number in this
-- table is. What they encode is one ordering and it is defensible in one line
-- each: a hunt resolves a claim either way and is the largest reduction in
-- uncertainty this harness makes; a perform is what turns a resolved claim into
-- evidence; a recon is information by construction but one subject is a small
-- share of a map; a conclude, a validate and a report learn nothing new and are
-- worth what they carry. Under the shipped `w_gain 0.4 / w_impact 0.6` that is
--
--     perform 0.72  hunt 0.70  conclude 0.57  validate 0.54
--     analyze 0.46  report 0.40  recon 0.35
--
-- Hunt is worth twice a recon, which is the sentence this file exists to make
-- the scheduler able to say. It could not say anything at all before.
-- ---------------------------------------------------------------------------

-- Defaulted so every existing version row gets a value, then filled and the
-- default dropped: `cost_prior` is NOT NULL with no default, so a new weights
-- version must state its own priors rather than inherit an old campaign's.
ALTER TABLE scheduler_weights
    ADD COLUMN gain_prior   jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN impact_prior jsonb NOT NULL DEFAULT '{}'::jsonb;

-- The trigger comes off for the fill and goes back on ALWAYS, which is
-- `20261014T000000Z`'s shape and its reason: an old version row is completed
-- rather than changed. Leaving the priors empty on the inactive versions would
-- make every one of them unreplayable, because `value_for` reads the row the
-- replay names and not the row that is active today.
ALTER TABLE scheduler_weights
    DISABLE TRIGGER scheduler_weights_versions_are_immutable;

UPDATE scheduler_weights
   SET gain_prior = '{"recon":0.50,"hunt":0.70,"perform":0.60,"analyze":0.55,'
                    '"conclude":0.30,"validate":0.30,"report":0.10}'::jsonb,
       impact_prior = '{"recon":0.25,"hunt":0.70,"perform":0.80,"analyze":0.40,'
                      '"conclude":0.75,"validate":0.70,"report":0.60}'::jsonb;

ALTER TABLE scheduler_weights
    ENABLE ALWAYS TRIGGER scheduler_weights_versions_are_immutable;

ALTER TABLE scheduler_weights
    ALTER COLUMN gain_prior   DROP DEFAULT,
    ALTER COLUMN impact_prior DROP DEFAULT;

COMMENT ON COLUMN scheduler_weights.gain_prior IS
  'kind -> expected information gain in [0,1], read by value_for() when the Task carries no model estimate. Unvalidated, like every number in this table.';
COMMENT ON COLUMN scheduler_weights.impact_prior IS
  'kind -> potential impact in [0,1], read by value_for() when the Task carries no model estimate. Unvalidated, like every number in this table.';


-- The one changed function. `coalesce` on each side rather than on the pair, so
-- a Task that carries one estimate and not the other uses the estimate it has:
-- a half-filled row is what a partially built verb would leave, and taking the
-- prior for both would throw away the half somebody measured.
--
-- The CASE stays, and it is not decoration. `greatest(NULL, 0)` is 0 in this
-- database -- greatest and least return NULL only when every argument is NULL
-- -- so an unpriced kind without it would rank as worthless rather than as
-- unpriced, which is the exact distinction the old body's comment was written
-- to keep. The two coalesced values are named once in a subquery so the CASE
-- and the arithmetic cannot fall out of step.
CREATE OR REPLACE FUNCTION value_for(t tasks, w scheduler_weights) RETURNS numeric
LANGUAGE sql STABLE AS $fn$
    SELECT CASE WHEN v.gain IS NULL OR v.impact IS NULL THEN NULL
                ELSE least(greatest(w.w_gain * v.gain + w.w_impact * v.impact, 0), 1.0)
           END
      FROM (SELECT coalesce(t.expected_information_gain,
                            (w.gain_prior   ->> t.kind)::numeric),
                   coalesce(t.potential_impact,
                            (w.impact_prior ->> t.kind)::numeric)) AS v(gain, impact);
$fn$;

COMMENT ON FUNCTION value_for(tasks, scheduler_weights) IS
  'The Task''s own value under these weights, normalised into [0, 1]: the model''s estimate where there is one, this kind''s prior where there is not, and NULL for a kind with neither -- NULL and not zero, because an unpriced kind is a different statement from a worthless one.';


-- Arm (a) of the closure check, which asked this question about cost alone.
-- Reproduced whole because a `CREATE OR REPLACE` is the whole body; the only
-- change is the two arms after `kind_has_no_cost_prior` and the comment above
-- them. Everything from (b) down is `20261003T000000Z:232` character for
-- character.
CREATE OR REPLACE FUNCTION check_scheduler_closure()
RETURNS TABLE (problem text, detail text) LANGUAGE sql STABLE AS $fn$
    -- (a) every kind the roster grants can be ranked by every factor. A kind
    --     with no prior in one of them is a task that ranks NULL forever and
    --     nobody notices -- which is ticket 196, measured over 480 Tasks and
    --     eight hours of a live engagement. With all three priors present a
    --     NULL priority is unreachable, so these three arms ARE the check the
    --     ticket asked for and there is no fourth one counting unranked queues.
    SELECT 'kind_has_no_cost_prior'::text, k.kind
      FROM task_kinds k, scheduler_weights w
     WHERE w.active AND NOT (w.cost_prior ? k.kind)
UNION ALL
    SELECT 'kind_has_no_gain_prior', k.kind
      FROM task_kinds k, scheduler_weights w
     WHERE w.active AND NOT (w.gain_prior ? k.kind)
UNION ALL
    SELECT 'kind_has_no_impact_prior', k.kind
      FROM task_kinds k, scheduler_weights w
     WHERE w.active AND NOT (w.impact_prior ? k.kind)
UNION ALL
    -- (b) the per-program lane override is reachable. This is the defect the
    --     migration exists to close; asserting it means dropping the view or
    --     reverting the join cannot make overrides silently inert again.
    SELECT 'lane_override_unreachable', p.id::text || ' ' || l.kind
      FROM scheduler_lanes l JOIN programs p ON p.id = l.program_id
     WHERE NOT EXISTS (SELECT 1 FROM effective_lane_capacity c
                        WHERE c.program_id = l.program_id AND c.kind = l.kind
                          AND c.overridden)
UNION ALL
    -- (c) an entitlement above the roster's cap, now for OVERRIDE rows too --
    --     ticket 34's check (e) reads `lane_capacity`, which only ever contains
    --     the NULL-program rows.
    SELECT 'lane_min_above_role_cap',
           coalesce(c.program_id::text, 'default') || ' ' || c.kind
      FROM effective_lane_capacity c WHERE c.min_slots > c.max_slots
UNION ALL
    -- (d) every skill a task requires is registered.
    SELECT 'task_requires_unregistered_skill', t.label || ' ' || s
      FROM tasks t CROSS JOIN LATERAL unnest(t.required_skills) AS s
     WHERE NOT EXISTS (SELECT 1 FROM skills k WHERE k.name = s)
UNION ALL
    -- (e) is gone with ticket 127. It asked whether a `penalised` near-match
    --     named the hypothesis it penalised; `penalised` is no longer an action
    --     `hypothesis_near_matches` accepts, and the CHECK on the column is
    --     what says so now, at write time rather than at check time.
    --
    -- (f) the slate cannot be larger than the table that holds it.
    SELECT 'slate_size_exceeds_task_slate', w.slate_size::text
      FROM scheduler_weights w WHERE w.active AND w.slate_size > 5
UNION ALL
    -- (g) the ranking pass has no clock in it. Decision 12 is a property of the
    --     text, so it is checked against the text: `now()` / `current_timestamp`
    --     inside the three factor functions would make two replays of the same
    --     rows disagree, and nothing else would ever say so. Comments are
    --     stripped first: the first version of this check fired on a comment
    --     explaining why the clock is absent, which is the check calling its
    --     own documentation a defect.
    SELECT 'ranking_factor_reads_the_clock', p.proname
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.proname IN ('novelty_for','cost_for','confidence_for')
       AND regexp_replace(p.prosrc, '--[^' || chr(10) || ']*', '', 'g')
           ~* '(now\(\)|current_timestamp|clock_timestamp)'
UNION ALL
    -- (h) the claim takes the lock. Ticket 32 found lane caps unheld without
    --     it, and ticket 08's text still says no lock is needed.
    SELECT 'claim_task_takes_no_advisory_lock', 'claim_task'
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace AND p.proname = 'claim_task'
       AND p.prosrc !~ 'pg_advisory_xact_lock'
UNION ALL
    -- (i) no scheduler function is callable by PUBLIC.
    SELECT 'scheduler_function_public_executable', p.proname
      FROM pg_proc p
     WHERE p.pronamespace = 'public'::regnamespace
       AND p.proname IN ('novelty_for','cost_for','confidence_for','ready_for',
                         'cancel_reason_for','rank_pass','rank_candidates',
                         'offer_slate','claim_task','sweep_expired_leases',
                         'scheduler_idle_report')
       AND has_function_privilege('public', p.oid, 'EXECUTE')
$fn$;


DO $$
DECLARE n integer; d text; v numeric;
BEGIN
    -- Every registered kind is priced on all three, which is what makes a NULL
    -- priority unreachable rather than merely unlikely.
    SELECT count(*), string_agg(problem || ' ' || detail, '; ')
      INTO n, d FROM check_scheduler_closure()
     WHERE problem LIKE 'kind_has_no_%';
    IF n > 0 THEN
        RAISE EXCEPTION 'ticket 196: % kind(s) still unpriced: %', n, d;
    END IF;

    -- And the value term answers for one. Asked of a real row rather than of
    -- the jsonb, because what broke was the function and not the table: the
    -- estimate columns were always NULL and always will be until a verb writes
    -- them, so the case this guard has to hold is exactly the unestimated one.
    SELECT value_for(t, w) INTO v
      FROM tasks t CROSS JOIN scheduler_weights w
     WHERE w.active AND t.expected_information_gain IS NULL LIMIT 1;
    IF FOUND AND v IS NULL THEN
        RAISE EXCEPTION 'ticket 196: an unestimated Task still values NULL';
    END IF;
END $$;
