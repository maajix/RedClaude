-- ---------------------------------------------------------------------------
-- 20261118T000000Z__the_walk_ends_at_the_bundle_it_fetched.sql
--
-- Refreezes `enumerate-surface` at the text that reads what it fetched.
--
-- `20261117T000000Z` gave `recon` the three source analysers and gave the door
-- a reason to file a bundle as `source`. Neither is a technique. The Skill now
-- carries the step that is: after the walk stores a script, run `js_routes`
-- over it and propose an Endpoint for every route the run grounds.
--
-- `js_routes` and not `js_parse`, and the step says why. A bundle is full of
-- path-shaped strings and `js_routes` reports only the ones handed to something
-- that makes a request, with the call site and the byte offset beside each --
-- which is the same distinction `check_source_citation` enforces afterwards, so
-- the step teaches the rule the runtime is going to apply anyway.
--
-- `bb:runtime-tools` gains the three names. That line is what the frame admits,
-- so a step naming a tool the line does not would be a step the model cannot
-- take.
--
-- AN UPDATE AND NOT AN UPSERT, for `20260928T020000Z`'s reason.
-- ---------------------------------------------------------------------------

UPDATE skills
   SET source_sha256 = 'b02ce721596b927984448d2503fd3a5e47db58263f5ebd389c112a40f6c86116',
       version       = '04c24c78373a98119d934e05295fe611647bee75656e332571be93b586162179'
 WHERE name = 'enumerate-surface';

UPDATE skill_dependencies
   SET sha256 = 'b02ce721596b927984448d2503fd3a5e47db58263f5ebd389c112a40f6c86116'
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
