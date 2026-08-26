-- ---------------------------------------------------------------------------
-- A hunter that may load the skill may run what it prescribes
--
-- WHAT WAS MEASURED. `20261206T000000Z` gave `enumerate-surface` the three
-- runtime tools its front matter has named since ticket 186, and the standing
-- check answered:
--
--     tool_ungranted enumerate-surface
--       "enumerate-surface may run js_map, which web_hunter may not"
--       "enumerate-surface may run js_parse, which web_hunter may not"
--       "enumerate-surface may run js_routes, which web_hunter may not"
--
-- `role_skills` lets `recon` and `web_hunter` load the Skill.
-- `offline_tool_roles` grants the three tools to `js_analyst` and `recon`. The
-- Skill therefore prescribed, to one of its two readers, three steps that
-- reader could not take.
--
-- WHICH HALF MOVES. The grant, not the Skill. Section 5 of the Skill is not an
-- aside a hunter may skip -- it reads the scripts a page loaded, runs
-- `js_routes` over what came back, and where that earns it follows `js_parse`
-- to a source map and `js_map` into the map. A Skill whose middle is unreachable
-- for half its readers is a Skill that has been narrowed by an omission rather
-- than by a decision, and the decision on record -- `bb:roles` names both -- is
-- that a hunter maps a surface too.
--
-- WHY IT IS SAFE TO WIDEN. All three are offline analysers under
-- `open_offline_tool_run`: they read an Artifact this Program already holds and
-- write nothing to the network. `recon` and `js_analyst` hold them already, so
-- nothing here is a capability that did not exist -- it is the same read, by the
-- other role that was already told to make it.
-- ---------------------------------------------------------------------------

INSERT INTO offline_tool_roles (tool, role) VALUES
    ('js_map',    'web_hunter'),
    ('js_parse',  'web_hunter'),
    ('js_routes', 'web_hunter')
ON CONFLICT (tool, role) DO NOTHING;


DO $$
DECLARE problems text;
BEGIN
    -- The check this file is the answer to, run here rather than described.
    SELECT string_agg(detail, '; ') INTO problems
      FROM check_skill_registry() WHERE code = 'tool_ungranted';
    IF problems IS NOT NULL THEN
        RAISE EXCEPTION 'a skill still prescribes what its reader may not run: %',
                        problems;
    END IF;
END $$;
