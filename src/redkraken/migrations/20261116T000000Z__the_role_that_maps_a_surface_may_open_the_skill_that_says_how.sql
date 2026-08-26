-- ---------------------------------------------------------------------------
-- 20261116T000000Z__the_role_that_maps_a_surface_may_open_the_skill_that_says_how.sql
--
-- `enumerate-surface` names `recon` in its own frontmatter now, and this
-- refreezes it at that text.
--
-- What was measured. Database `rk2here`, 2026-08-25. Seventeen `recon` agent
-- runs, and `agent_runs.tools_called` on every one of them is
-- `http_request, submit_mission_result` -- no run ever called the Skill tool.
-- It could not have. `roster.ROLES['recon'].skills` answered
-- `('handle-untrusted-content',)`, because `Role.skills` is derived from the
-- `bb:roles` line of each Skill and `enumerate-surface` named `web_hunter`
-- alone. `agent.stage_skills` writes that tuple into the child's launch
-- directory, so the instructions were never staged for the role whose whole
-- Task kind is the one they describe.
--
-- 20260822 wrote `('recon', 'enumerate-surface')` into `role_skills` and the
-- row has been correct and inert since: the table records the grant and the
-- roster stages the file, and nothing compares them. That the two disagreed for
-- as long as they did is the second half of this finding and is recorded in
-- ticket 188 rather than fixed here.
--
-- `web_hunter` keeps the Skill. `20261108T000000Z` gave the hunt role the
-- Skills its own Playbook names, and `attack-surface` names this one.
--
-- AN UPDATE AND NOT AN UPSERT, for `20260928T020000Z`'s reason.
-- ---------------------------------------------------------------------------

UPDATE skills
   SET source_sha256 = '00ccc5f17f2d757f252c1b27575ea050485583439479b82835142e11dcedf53c',
       version       = '8ce79e503f178ba560e2d028604e3617c3550582fd2266660130b164553bfb9d'
 WHERE name = 'enumerate-surface';

UPDATE skill_dependencies
   SET sha256 = '00ccc5f17f2d757f252c1b27575ea050485583439479b82835142e11dcedf53c'
 WHERE skill_name = 'enumerate-surface' AND path = 'SKILL.md';


DO $$
DECLARE n integer; d text;
BEGIN
    SELECT count(*), string_agg(code || ': ' || subject || ' -- ' || detail, '; ')
      INTO n, d FROM check_skill_registry()
     WHERE subject = 'enumerate-surface';
    IF n > 0 THEN
        RAISE EXCEPTION 'the refreeze left % problem(s) on enumerate-surface: %', n, d
          USING ERRCODE = '23514';
    END IF;
END $$;
