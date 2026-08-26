-- ---------------------------------------------------------------------------
-- The skill that maps a surface names the tools it drives
--
-- WHAT WAS MEASURED. `CleanCreationTest` compares the shipped corpus against
-- the registry row for row:
--
--     AssertionError: Tuples differ:
--       (('analyse-source', 'jq'), ('enumerate-surface', 'jq'),
--        ('enumerate-surface', 'js_map'), ('enumerate-surface', 'js_parse'),
--        ('enumerate-surface', 'js_routes'))
--     != (('analyse-source', 'jq'), ('enumerate-surface', 'jq'))
--
-- `enumerate-surface/SKILL.md` names four runtime tools and
-- `skill_runtime_tools` holds one of them.
--
-- HOW IT GOT THERE. Ticket 186 gave the source-analysis chain a way to start,
-- and `js_map`, `js_parse` and `js_routes` were registered in `offline_tools`
-- and written into the Skill's front matter. Nothing wrote the link rows,
-- because the only writer of this table is a migration -- `20260822T000000Z`
-- inserted the two rows that were true then, and the corpus has moved twice
-- since without this table moving with it.
--
-- WHAT IT COSTS. `skill_runtime_tools` is criterion 3's second arm: where a
-- Skill's deterministic behaviour is a registered tool rather than a checked
-- script, this is the row that says so, and the foreign key is what stops a
-- Skill naming a program nobody registered. A Skill whose tools are absent from
-- it is a Skill the registry describes as driving nothing, so the arm holds
-- vacuously for three quarters of the one Skill that drives anything.
--
-- The rows and not a rewrite: the three tools are already in `offline_tools`
-- with their own `version_argv` and `version_pattern`, so what was missing is
-- the statement that this Skill is what drives them.
-- ---------------------------------------------------------------------------

INSERT INTO skill_runtime_tools (skill_name, tool) VALUES
    ('enumerate-surface', 'js_map'),
    ('enumerate-surface', 'js_parse'),
    ('enumerate-surface', 'js_routes')
ON CONFLICT (skill_name, tool) DO NOTHING;


DO $$
DECLARE n integer;
BEGIN
    SELECT count(*) INTO n FROM skill_runtime_tools
     WHERE skill_name = 'enumerate-surface';
    IF n <> 4 THEN
        RAISE EXCEPTION
          'enumerate-surface drives % runtime tool(s), and the corpus names 4', n;
    END IF;
END $$;
