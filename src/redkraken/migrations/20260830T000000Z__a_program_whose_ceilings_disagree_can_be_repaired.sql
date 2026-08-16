-- ---------------------------------------------------------------------------
-- 20260830T000000Z__a_program_whose_ceilings_disagree_can_be_repaired.sql
--                                                                   (ticket 81)
--
-- Ticket 81 fixes a trap that 025 built and nobody walked into until a live
-- validation did. `check_program_configuration` learned to fail a Program whose
-- per-run ceiling stands above its lane's or its campaign's, which is right --
-- such a Program refuses every Task and blames its budget for it. But the gate
-- that reads that check runs in `program.open_program` *before* anything is
-- written, so the only command that could repair the row refuses to start on
-- account of the row it was going to repair. And it is corpus-wide, so one
-- poisoned Program stops every other Program's run as well.
--
-- Two facts are wrong here and they are separate. A standing check may be a
-- statement about the whole corpus or a statement about one Program, and the
-- runner has never been able to tell which. So:
--
--   1. `standing_checks.program_scoped` records the distinction, and a
--      constraint keeps the column honest: a scoped row's query must carry the
--      `$1` the runner binds the Program list to.
--
--   2. `check_program_configuration` takes that list, defaulting to NULL --
--      every Program, which is what `rk db verify` and every migration ask for,
--      so strictness is unchanged where it was already correct and every
--      existing no-argument call still resolves. An empty list is no Program,
--      which is how a caller says "the global invariants only". The filter goes
--      in the checker rather than in the runner because only the checker knows
--      which column carries a slug: two of its five arms report
--      `slug || ' revision ' || n`, and a runner filtering the `object` column
--      by equality would silently stop asking those two anything.
--
--   3. `run_standing_checks(text[], boolean)` threads the list through and says
--      whether the scoped rows are the only ones wanted. The no-arg version
--      delegates to it with NULL and false, so every existing caller keeps the
--      behaviour it has.
--
-- What this buys, in `program.py`: the pre-adoption gate asks for the global
-- families only, then the Program-scoped checks run again inside the same
-- transaction that adopted the configuration. A corrected file repairs the row
-- and passes; a file that is still contradictory rolls the adoption back. And a
-- neighbour's poisoned row is nobody else's refusal, which is what it never
-- should have been.
-- ---------------------------------------------------------------------------

-- 1. The registry learns which of its rows are about one Program.
ALTER TABLE standing_checks
    ADD COLUMN program_scoped boolean NOT NULL DEFAULT false;

ALTER TABLE standing_checks
    ADD CONSTRAINT standing_checks_scoped_query
    CHECK (NOT program_scoped OR query LIKE '%$1%');

COMMENT ON COLUMN standing_checks.program_scoped IS
  'Whether this check states something about one Program rather than about the corpus. A scoped query takes the Program list as $1 and reads NULL as every Program, so the runner can ask a caller''s question -- "is this Program sound" -- without answering it with a neighbour''s row.';

-- 2. The checker takes the list. The body is 025's, arm for arm, with one
--    predicate added to each: the arms are what they were and this only decides
--    which Programs they are asked about. The default keeps every existing
--    no-argument call resolving to it, which is what makes this a widening
--    rather than a break -- 025's own self-check and two tests call it that way.
DROP FUNCTION check_program_configuration();

CREATE FUNCTION check_program_configuration(p_programs text[] DEFAULT NULL)
RETURNS TABLE (problem text, object text, detail text)
LANGUAGE sql STABLE AS $$
    -- 1. A Program nobody can say the policy of. This is what a create path
    --    that wrote the root row and then failed leaves behind, and what a
    --    Program opened by hand around `rk run` would leave behind for good.
    SELECT 'program_without_configuration', p.slug,
           'programs row with no program_configurations revision; nothing records the policy it runs under'
      FROM programs p
     WHERE NOT EXISTS (SELECT 1 FROM program_configurations c
                        WHERE c.program_id = p.id)
       AND (p_programs IS NULL OR p.slug = ANY(p_programs))
  UNION ALL
    -- 2. Revisions are 1..n with no gap. A gap means a revision was lost, and
    --    a lost revision is a policy that authorised work and cannot be read
    --    back -- the failure the append-only rule exists to prevent.
    SELECT 'configuration_revisions_not_contiguous', p.slug,
           'revisions ' || c.lowest || '..' || c.highest || ' but ' || c.total || ' row(s)'
      FROM programs p
      JOIN (SELECT program_id, min(revision) AS lowest, max(revision) AS highest,
                   count(*) AS total
              FROM program_configurations GROUP BY program_id) c
        ON c.program_id = p.id
     WHERE (c.lowest <> 1 OR c.highest <> c.total)
       AND (p_programs IS NULL OR p.slug = ANY(p_programs))
  UNION ALL
    -- 3. A revision that changes nothing. Recording one is how a resume path
    --    that compares the wrong hash announces itself: the policy is
    --    identical, so the revision says a change happened that did not, and
    --    every row citing it afterwards cites a version number with no meaning.
    SELECT 'configuration_revision_changes_nothing',
           p.slug || ' revision ' || c.revision,
           'canonical_sha256 is identical to revision ' || (c.revision - 1)
      FROM program_configurations c
      JOIN program_configurations prior
        ON prior.program_id = c.program_id AND prior.revision = c.revision - 1
       AND prior.canonical_sha256 = c.canonical_sha256
      JOIN programs p ON p.id = c.program_id
     WHERE p_programs IS NULL OR p.slug = ANY(p_programs)
  UNION ALL
    -- 4. The Program is not running the policy its newest revision states.
    --    `programs` carries the platform and the budget ceilings as columns
    --    because the scheduler and the quota views read them there, and it
    --    emits no event of its own, so a write that moved them without
    --    recording a revision is a policy change with no before and after. The
    --    revision history is only worth citing if this cannot happen quietly.
    --    The four ceilings 25 added are compared against the revision's own
    --    document, which is where the loader read them from.
    SELECT 'configuration_not_applied', p.slug || ' revision ' || c.revision,
           'the Program runs platform ' || coalesce(p.platform, '(none)') ||
           ' with budget ' || coalesce(p.token_budget::text, '(none)') ||
           ' (run ' || coalesce(p.run_token_budget::text, '(none)') || '/' ||
           coalesce(p.run_request_budget::text, '(none)') || ', lane ' ||
           coalesce(p.lane_token_budget::text, '(none)') || '/' ||
           coalesce(p.lane_request_budget::text, '(none)') ||
           '); its newest revision states ' || coalesce(c.platform, '(none)') ||
           ' with ' || c.token_budget ||
           ' (run ' || coalesce(c.document #>> '{budgets,run_tokens}', '(none)') || '/' ||
           coalesce(c.document #>> '{budgets,run_requests}', '(none)') || ', lane ' ||
           coalesce(c.document #>> '{budgets,lane_tokens}', '(none)') || '/' ||
           coalesce(c.document #>> '{budgets,lane_requests}', '(none)') || ')'
      FROM programs p
      JOIN LATERAL (SELECT revision, platform, token_budget, document
                      FROM program_configurations
                     WHERE program_id = p.id
                     ORDER BY revision DESC
                     LIMIT 1) c ON true
     WHERE (p.platform     IS DISTINCT FROM c.platform
        OR p.token_budget IS DISTINCT FROM c.token_budget
        OR p.run_token_budget    IS DISTINCT FROM (c.document #>> '{budgets,run_tokens}')::bigint
        OR p.run_request_budget  IS DISTINCT FROM (c.document #>> '{budgets,run_requests}')::bigint
        OR p.lane_token_budget   IS DISTINCT FROM (c.document #>> '{budgets,lane_tokens}')::bigint
        OR p.lane_request_budget IS DISTINCT FROM (c.document #>> '{budgets,lane_requests}')::bigint)
       AND (p_programs IS NULL OR p.slug = ANY(p_programs))
  UNION ALL
    -- 5. Ceilings that cannot all be true at once. A per-run ceiling above the
    --    lane's or the campaign's is a Program where every claim promises more
    --    than there is, so `budget_refusal_for` refuses every Task from the
    --    first one -- and reports it as an exhausted budget, which is the true
    --    answer to the wrong question. The configuration is what is wrong, and
    --    a Program that can never claim anything should say so where the
    --    operator is already looking. Only the per-run ceiling is compared
    --    upwards: a lane ceiling above the total is slack, because the total
    --    binds first and the lane simply never does. A ceiling nobody stated
    --    is not compared either: NULL is unbounded, and unbounded disagrees
    --    with nothing.
    SELECT 'configuration_ceilings_disagree', p.slug,
           'per run ' || coalesce(p.run_token_budget::text, '(none)') || ' tokens/' ||
           coalesce(p.run_request_budget::text, '(none)') || ' requests, per lane ' ||
           coalesce(p.lane_token_budget::text, '(none)') || '/' ||
           coalesce(p.lane_request_budget::text, '(none)') || ', campaign ' ||
           coalesce(p.token_budget::text, '(none)') || '/' ||
           coalesce(q.budget_requests::text, '(none)')
      FROM programs p
      LEFT JOIN LATERAL (SELECT sv.budget_requests FROM program_scope_versions sv
                          WHERE sv.program_id = p.id AND sv.version = p.scope_version) q ON true
     WHERE (p.run_token_budget   > p.token_budget
        OR p.run_token_budget   > p.lane_token_budget
        OR p.run_request_budget > q.budget_requests
        OR p.run_request_budget > p.lane_request_budget)
       AND (p_programs IS NULL OR p.slug = ANY(p_programs))
$$;

COMMENT ON FUNCTION check_program_configuration(text[]) IS
  'Every Program states the policy it runs under, the statement is complete, no revision claims a change that did not happen, the Program runs every ceiling its newest revision states, and those ceilings can all be true at once -- one run may not be promised more than its lane or its campaign has, which is a Program that admits nothing and blames its budget for it. A lane or campaign ceiling nobody can reach is slack, not a contradiction: the tighter one binds first. The argument names which Programs to ask about: NULL is all of them, and the empty array is none, which is how a caller asks for the corpus-wide invariants without being handed a neighbour''s fault.';

UPDATE standing_checks
   SET query = 'SELECT * FROM check_program_configuration($1)',
       program_scoped = true
 WHERE name = 'program_configuration';

-- 3. The runner binds the list, and only for the rows that asked for it.
--    `EXECUTE ... USING` on a query with no placeholder is an error, so the
--    branch is on `program_scoped` rather than on whether an argument arrived --
--    and the branch is over `USING` alone, because the statement either side of
--    it is the same statement and reading it twice invites the two to drift.
CREATE FUNCTION run_standing_checks(p_programs text[], p_scoped_only boolean)
RETURNS TABLE (name text, problems bigint, detail text)
LANGUAGE plpgsql STABLE AS $$
DECLARE r record; n bigint; d text; counted text;
BEGIN
    FOR r IN SELECT s.name, s.query, s.program_scoped FROM standing_checks s
              WHERE s.program_scoped OR NOT p_scoped_only
              ORDER BY s.name LOOP
        counted := format(
            'SELECT count(*), left(coalesce(string_agg(x::text, ''; ''), ''''), 240) FROM (%s) x',
            r.query);
        IF r.program_scoped THEN
            EXECUTE counted INTO n, d USING p_programs;
        ELSE
            EXECUTE counted INTO n, d;
        END IF;
        name := r.name; problems := n; detail := d;
        RETURN NEXT;
    END LOOP;
END $$;

COMMENT ON FUNCTION run_standing_checks(text[], boolean) IS
  'Every registered standing check, or only the Program-scoped ones, with the scoped ones asked about the named Programs. NULL is every Program and the empty array is none. The scoped-only form is for a caller holding a transaction open over one Program''s write: it asks whether that Program is sound without re-asking corpus-wide invariants against rows nobody has committed yet.';

-- The no-argument form is the whole corpus about every Program, which is what
-- roughly thirty callers mean when they name it. It delegates rather than
-- repeating the loop, so there is one place that decides how a registered query
-- is executed. There is deliberately no one-argument form in between: nothing
-- wants "these Programs and also the corpus-wide rows" without also saying
-- which of the two it is asking about.
CREATE OR REPLACE FUNCTION run_standing_checks()
RETURNS TABLE (name text, problems bigint, detail text)
LANGUAGE sql STABLE AS $$
    SELECT name, problems, detail FROM run_standing_checks(NULL::text[], false)
$$;

COMMENT ON FUNCTION run_standing_checks() IS
  'Every registered standing check across every Program. What `rk db verify`, every migration and `assert_standing_checks` ask for.';

-- ---------------------------------------------------------------------------
-- What this file claims, asked of the database that just applied it.
--
-- Not `assert_standing_checks()`, which is what a file changing a table usually
-- ends with: the runner applies the state RLS, the state grants and the
-- event-trigger fixups after the whole corpus, so five corpus-wide checks are
-- not yet true at this point and a migration asserting them would be asserting
-- the runner's order rather than its own work. These assert this file's own
-- work instead, which is the part nothing else covers.
-- ---------------------------------------------------------------------------
DO $$
DECLARE n bigint; m bigint; refused boolean;
BEGIN
    -- 1. The registry records which row is about one Program, of the one row
    --    that is.
    SELECT count(*) INTO n FROM standing_checks WHERE program_scoped;
    IF n <> 1 THEN
        RAISE EXCEPTION 'ph2-81 expects exactly one Program-scoped check, found %', n;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM standing_checks
                    WHERE name = 'program_configuration' AND program_scoped
                      AND query = 'SELECT * FROM check_program_configuration($1)') THEN
        RAISE EXCEPTION 'ph2-81 did not leave program_configuration scoped and bound to $1';
    END IF;

    -- 2. The constraint keeps the column honest. A scoped row whose query binds
    --    nothing would be handed a Program list the checker never reads, and
    --    would answer a caller's narrow question with everybody's rows -- which
    --    is the failure this whole file exists to end.
    BEGIN
        UPDATE standing_checks SET program_scoped = true
         WHERE NOT program_scoped AND query NOT LIKE '%$1%';
        refused := false;
    EXCEPTION WHEN check_violation THEN
        refused := true;
    END;
    IF NOT refused THEN
        RAISE EXCEPTION 'ph2-81 lets a check that binds no $1 call itself Program-scoped';
    END IF;

    -- 3. Scoped-only runs the scoped rows and nothing else; the no-argument
    --    form still runs everything registered.
    SELECT count(*) INTO n FROM run_standing_checks(NULL::text[], true);
    IF n <> 1 THEN
        RAISE EXCEPTION 'ph2-81 scoped-only ran % check(s), expected 1', n;
    END IF;
    SELECT count(*) INTO n FROM run_standing_checks();
    SELECT count(*) INTO m FROM standing_checks;
    IF n <> m THEN
        RAISE EXCEPTION 'ph2-81 no-argument form ran % of % registered check(s)', n, m;
    END IF;

    -- 4. The empty list is no Program, which is what the pre-adoption gate in
    --    `program.open_program` passes to ask for the corpus-wide invariants
    --    alone. It has to report nothing whatever the corpus holds.
    SELECT coalesce(sum(problems), 0) INTO n
      FROM run_standing_checks(ARRAY[]::text[], true);
    IF n <> 0 THEN
        RAISE EXCEPTION 'ph2-81 reports % problem(s) about no Program at all', n;
    END IF;

    -- 5. Every existing no-argument call still resolves -- 025's self-check and
    --    two tests make them -- and NULL means every Program rather than
    --    merely "no filter that happens to match".
    SELECT count(*) INTO n FROM check_program_configuration();
    SELECT count(*) INTO m FROM check_program_configuration(NULL::text[]);
    IF n <> m THEN
        RAISE EXCEPTION 'ph2-81 no-argument checker answers % where NULL answers %', n, m;
    END IF;
    SELECT count(*) INTO n FROM check_program_configuration(
        (SELECT coalesce(array_agg(slug), ARRAY[]::text[]) FROM programs));
    IF n <> m THEN
        RAISE EXCEPTION 'ph2-81 naming every Program answers % where NULL answers %', n, m;
    END IF;
END $$;
