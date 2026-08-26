-- ---------------------------------------------------------------------------
-- 20261126T000000Z__the_role_that_maps_a_surface_holds_the_skill_it_stages.sql
--
-- The row `20261116T000000Z` said was already there.
--
-- That file returned `enumerate-surface` to `recon` in its own frontmatter,
-- which is what `roster.Role.skills` is derived from and what
-- `agent.stage_skills` writes into the child's launch directory. It said, in a
-- comment, that `role_skills` had held `('recon', 'enumerate-surface')` since
-- 20260822 and that the two had only ever disagreed the other way round.
--
-- It had not. `20261108T000000Z:72` is
--
--     DELETE FROM role_skills WHERE role = 'recon' AND skill_name = 'enumerate-surface';
--
-- with a guard three lines later asserting that exactly one role holds the
-- Skill. Eight days later the frontmatter said two roles and the table said
-- one, and nothing in the harness compared them -- which is the whole of ticket
-- 188 and is now W11 in `tools/check_wiring.py`.
--
-- What it costs while it stands. `skills_ungranted_for(t)` asks `role_skills`
-- whether the one role that runs a Task's kind holds every Skill in
-- `t.required_skills`, and `claimable_for` refuses on it. No Task in any live
-- Program sets `required_skills` today, so the row's absence has cost nothing
-- yet; the first recon Task that requires the Skill its own role is staged
-- leaves the queue as unclaimable, and the refusal names the Skill rather than
-- the missing grant.
--
-- `20261108T000000Z`'s guard is not touched. An applied migration is immutable
-- here -- `migrate.py` compares checksums and calls a changed file schema drift
-- -- and the guard was a one-time assertion about the state that file left, not
-- a standing rule. What replaces it is W11, which asks the question the guard
-- was reaching for and asks it of both sources at once.
-- ---------------------------------------------------------------------------

INSERT INTO role_skills (role, skill_name) VALUES ('recon', 'enumerate-surface');


DO $$
DECLARE n integer; d text;
BEGIN
    -- Both roles hold it, which is what the two frontmatter lines say.
    SELECT count(*) INTO n FROM role_skills WHERE skill_name = 'enumerate-surface';
    IF n <> 2 THEN
        RAISE EXCEPTION 'ticket 188: % role(s) hold enumerate-surface, expected 2', n;
    END IF;

    -- And the registry is still whole. A grant to a role that loads nothing
    -- fails at `role_skills_role_loads_fkey` before reaching here; this is for
    -- everything the registry checks that a foreign key cannot.
    SELECT count(*), string_agg(code || ': ' || subject || ' -- ' || detail, '; ')
      INTO n, d FROM check_skill_registry();
    IF n > 0 THEN
        RAISE EXCEPTION 'the grant left % problem(s) in the registry: %', n, d
          USING ERRCODE = '23514';
    END IF;
END $$;
