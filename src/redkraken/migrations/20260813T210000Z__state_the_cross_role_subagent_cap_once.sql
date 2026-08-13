-- ---------------------------------------------------------------------------
-- 20260813T210000Z__state_the_cross_role_subagent_cap_once.sql        (PH2-73)
--
-- The number 3 was written twice. `scheduler_weights.max_concurrent_subagents`
-- is what `claimable_for` filters the Slate by and refuses the claim by, and
-- what `check_lane_quota_closure()` bounds the sum of lane entitlements
-- against. `roster.GLOBAL_SUBAGENTS`, now `roster.DEFAULT_SUBAGENTS`, was the
-- same number again in a Python constant, and the pre-tool gate refused a
-- delegation by that one. They were equal by coincidence, and one of them is a
-- column on the one active weights row, which an operator versions: raised to
-- 4, the Slate offers a fourth hunt, the orchestrator delegates it and the
-- gate denies it -- the Task claimed, the run row open, the child never
-- started. Lowered to 2, the gate is dead code.
--
-- The runtime now reads this column with the claim (`execution.STARTED`) and
-- hands it to `roster.Gate`, so this row is the one statement and the constant
-- is only the default the schema also defaults to. Nothing in the schema
-- changes here: what the schema was missing is the sentence saying what the
-- number means on each side of that seam, and a check that keeps the count on
-- this side reading the column rather than a second copy of its value.
-- ---------------------------------------------------------------------------

-- ---------------------------------------------------------------------------
-- 1. What the number means, on the column that holds it
-- ---------------------------------------------------------------------------

-- Both populations, because two equal constants were what made two different
-- counts look like agreement. Said once here and once on `roster.Gate`, which
-- are the two places a reader of either count arrives at.
COMMENT ON COLUMN scheduler_weights.max_concurrent_subagents IS
  'How many subagents may run at once, across every lane. Counted twice, over two populations: the scheduler counts Tasks in claimed or running whose lane role runs as a subagent, across the whole Program and across orchestrator rotations, and refuses an offer and a claim past this (claimable_for); the runtime reads this column with the claim and gives it to the pre-tool gate, which counts the delegations one orchestrator session is holding, which is that SDK''s concurrency and that machine''s containers. The session''s population is a subset of the Program''s, which is why one number bounds both, and why they disagree during a rotation. Set on the one active weights row, which an operator versions for the whole scheduler: that row is the one statement of it, and the runtime carries no copy.';

-- And once where the scheduler spends it. `claimable_for` is not rewritten
-- here -- the comment is replaced whole, because a comment cannot be appended
-- to, so the sentence 170000Z wrote is restated with the population added.
COMMENT ON FUNCTION claimable_for(tasks, scheduler_weights) IS
    'NULL when this Task may be claimed, else the name of the condition that '
    'refuses it. The offer filters on it and the claim re-asks it, so the list '
    'the orchestrator was given and the decision the runtime commits cannot be '
    'answers to two different questions. Its global_subagent_cap arm counts '
    'the Program''s claimed and running subagent Tasks, which is the wider of '
    'the two populations max_concurrent_subagents bounds: the pre-tool gate '
    'counts one session''s outstanding delegations against the same number.';


-- ---------------------------------------------------------------------------
-- 2. The standing check
-- ---------------------------------------------------------------------------

-- Textual, and about where a bound comes from rather than what a row holds --
-- for the reason PH2-71's arms are: a cap compared against a literal that
-- happens to equal today's weights row is indistinguishable, row by row, from
-- one that read the row, and they differ on exactly the day an operator moves
-- it. Comments are stripped first so that a body mentioning the column only in
-- a comment does not read as one that consults it.
--
-- The shape matched is the counting subquery and not `runs_as` alone: a
-- function that merely tells subagent roles from session ones is not bounding
-- anything, and firing on it would make this check something to be worked
-- around rather than obeyed.
CREATE FUNCTION check_subagent_cap()
RETURNS TABLE (problem text, subject text, detail text)
LANGUAGE sql STABLE AS $fn$
    SELECT 'subagent_cap_stated_outside_the_weights_row'::text, p.proname,
           'a function counts concurrent subagents against a bound it did not '
           'read from scheduler_weights.max_concurrent_subagents'
      FROM pg_proc p
     CROSS JOIN LATERAL (
         SELECT regexp_replace(p.prosrc, '--[^' || chr(10) || ']*', '', 'g')
     ) AS s(src)
     WHERE p.pronamespace = 'public'::regnamespace
       AND s.src ~ 'count\(\*\)[^;]*runs_as[^;]*''subagent'''
       AND s.src !~ 'max_concurrent_subagents'
$fn$;

REVOKE ALL ON FUNCTION check_subagent_cap() FROM PUBLIC;

COMMENT ON FUNCTION check_subagent_cap() IS
    'The cross-role subagent cap has one source. A function that counts the '
    'subagents running and bounds that count by anything other than '
    'scheduler_weights.max_concurrent_subagents is a second statement of a '
    'number an operator sets in one place.';

INSERT INTO standing_checks(name, query, owner_ticket, note) VALUES
    ('subagent_cap', 'SELECT * FROM check_subagent_cap()', '73',
     'how many subagents may run at once is the weights column, on both sides of the runtime seam');


-- ---------------------------------------------------------------------------
-- 3. The invariants this file must not have broken
-- ---------------------------------------------------------------------------

DO $$
DECLARE n integer; d text;
BEGIN
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_subagent_cap();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-73 refuses to finish: % subagent cap problem(s): %', n, d;
    END IF;

    -- The two readers of the column, asked to still be closed over it. Neither
    -- is rewritten here, which is the point: a comment and a check are all this
    -- ticket owes the schema, and a file that claimed that and moved a
    -- predicate would be caught by one of these two.
    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_slate_claim();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-73 breaks the slate and the claim (% problems): %', n, d;
    END IF;

    SELECT count(*), string_agg(problem || ': ' || detail, '; ')
      INTO n, d FROM check_lane_quota_closure();
    IF n > 0 THEN
        RAISE EXCEPTION 'ph2-73 breaks lane quota closure (% problems): %', n, d;
    END IF;
END $$;
