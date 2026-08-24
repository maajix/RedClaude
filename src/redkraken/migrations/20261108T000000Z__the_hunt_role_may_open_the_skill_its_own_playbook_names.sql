-- ---------------------------------------------------------------------------
-- 20261108T000000Z__the_hunt_role_may_open_the_skill_its_own_playbook_names.sql
--                                                        (ticket 178)
--
-- `enumerate-surface` moves from `recon` to `web_hunter`, and `web_hunter`
-- gains the one registered tool that Skill drives.
--
-- What was measured. Database `rk2grade4`, 2026-08-24, `attack-surface`
-- against `artifact-exposure-pair`. Twelve recon Tasks ran to `done` and not
-- one of them produced a `playbook_selections` row at all. The only rows in the
-- database are two under a `hunt` Task and one under a `conclude` Task, and
-- every one of them reads `dropped_because = 'role_lacks_skill'`.
--
-- So the Playbook was unreachable from both ends. `bb:triggers_all` on
-- `attack-surface` is `read_method` and `unauthenticated_endpoint`, which are
-- facts recon records rather than facts recon is given, so at recon time the
-- triggers match nothing and the Playbook is not a candidate. By the time they
-- do match, the Task is a hunt Task and `playbook_candidates`
-- (20260918T000000Z) drops the Playbook because the asking role does not hold
-- its Skills. A Playbook that no role can select on a Task whose subject fits
-- it is dead corpus that still passes every gate.
--
-- Which end was wrong. The Playbook's own text is hunt work throughout: step 1
-- requests a control path, step 3 sends one request per candidate at the
-- application, and step 6 proposes the Hypothesis and says in that same step
-- why `enumerate-surface`'s refusal to propose one does not apply here. Its
-- triggers are facts about a route that is already known. Nothing in it is
-- enumeration of an unmapped root, which is what recon is for and what the
-- Skill's own step 4 stops at.
--
-- Moved rather than added. `tests/test_database.py`
-- `test_every_playbook_is_loadable_by_exactly_one_production_role` holds the
-- corpus to one role per Playbook, and grants that make two roles able to load
-- one Playbook are exactly what it exists to catch: "a Playbook that two roles
-- can load is a Playbook whose Skill set no longer picks out who does this
-- work". `attack-surface` is the only Playbook naming this Skill, so the Skill
-- goes with it. `recon` keeps `handle-untrusted-content` and loads what it
-- loaded before this migration, which the measurement above shows was nothing.
--
-- The one tool grant, and why it is the Playbook's own statement rather than a
-- widening invented here. `check_skill_registry` refuses a Skill held by a role
-- that may not run the tools it drives -- "enumerate-surface may run jq, which
-- web_hunter may not" -- so the `offline_tool_roles` row is part of the same
-- change. `attack-surface` step 5 writes its whole identification step on top
-- of that grant and states it outright: "this Playbook's role is granted `jq`
-- alone". The supported claim needs a `content_match`, `content_match` takes
-- tool-run provenance alone, and the tool run the text names is `jq`.
--
-- What that grant is bounded by. `jq` reads one stored Artifact this Program
-- already holds. It opens no socket, writes no state, and its output is an
-- Artifact with a Tool run behind it. `web_hunter` already holds
-- `exec.tool_run` and already runs `compare_responses` through it, so no new
-- kind of execution appears. The roster keeps `js_parse`, `js_routes` and
-- `js_map` to `js_analyst` because they turn a bundle into a source
-- conclusion; `jq` selects a field out of a document that is already JSON.
-- `recon` keeps its own `jq` row: this migration is not the place to decide
-- what recon runs, and the row grants nothing that a Task can reach without a
-- Skill naming it.
--
-- No tool group moves. `enumerate-surface` declares `exec.tool_run`,
-- `net.request`, `state.propose` and `state.read`; `web_hunter` already holds
-- all four. `roster._check_skills` enforces the subset rule at import, so a
-- grant that widened a group would refuse there rather than reach this file.
--
-- The digests follow for the reason tickets 87, 91, 92 and 99 each gave:
-- `skills.source_sha256` and `skill_dependencies.sha256` are a copy of what is
-- on disk, and the copy is only worth having because `CleanCreationTest`
-- compares it against `skill.SKILLS`. `enumerate-surface` owns one file, so one
-- dependency row moves and the version is the digest of a one-line manifest.
-- ---------------------------------------------------------------------------

DELETE FROM role_skills WHERE role = 'recon' AND skill_name = 'enumerate-surface';

INSERT INTO role_skills (role, skill_name) VALUES ('web_hunter', 'enumerate-surface');

INSERT INTO offline_tool_roles (tool, role) VALUES ('jq', 'web_hunter');

UPDATE skill_dependencies
   SET sha256 = '179577d571410741b5afffa26a4fdbd6cd57e64d23cdcbefb810d645dffba18e'
 WHERE skill_name = 'enumerate-surface'
   AND kind = 'instruction'
   AND path = 'SKILL.md';

UPDATE skills
   SET source_sha256 = '179577d571410741b5afffa26a4fdbd6cd57e64d23cdcbefb810d645dffba18e',
       version       = 'fbab50260528dd0ff6fe238af8bd6fd9031c7acc46f4000ab7a7d63c007f9910'
 WHERE name = 'enumerate-surface';

DO $$
DECLARE n integer;
BEGIN
    SELECT count(*) INTO n FROM skills
     WHERE name = 'enumerate-surface'
       AND source_sha256 = '179577d571410741b5afffa26a4fdbd6cd57e64d23cdcbefb810d645dffba18e'
       AND version = 'fbab50260528dd0ff6fe238af8bd6fd9031c7acc46f4000ab7a7d63c007f9910';
    IF n <> 1 THEN
        RAISE EXCEPTION 'ticket 178: the enumerate-surface skill row did not move';
    END IF;

    SELECT count(*) INTO n FROM skill_dependencies
     WHERE skill_name = 'enumerate-surface'
       AND kind = 'instruction'
       AND path = 'SKILL.md'
       AND sha256 = '179577d571410741b5afffa26a4fdbd6cd57e64d23cdcbefb810d645dffba18e';
    IF n <> 1 THEN
        RAISE EXCEPTION 'ticket 178: the enumerate-surface instruction digest did not move';
    END IF;

    -- One role holds it, and it is the hunt role. Both halves asserted, because
    -- an INSERT that landed beside a DELETE that did not would leave the corpus
    -- with the two-role shape this migration exists to avoid.
    SELECT count(*) INTO n FROM role_skills WHERE skill_name = 'enumerate-surface';
    IF n <> 1 THEN
        RAISE EXCEPTION 'ticket 178: % role(s) hold enumerate-surface, expected 1', n;
    END IF;

    SELECT count(*) INTO n FROM role_skills
     WHERE skill_name = 'enumerate-surface' AND role = 'web_hunter';
    IF n <> 1 THEN
        RAISE EXCEPTION 'ticket 178: web_hunter does not hold enumerate-surface';
    END IF;

    -- Nothing this Playbook names is beyond the role that is now offered it.
    SELECT count(*) INTO n
      FROM playbook_skills s
      JOIN playbooks p ON p.id = s.playbook_id
     WHERE p.path = 'playbooks/attack-surface/playbook.md'
       AND NOT EXISTS (SELECT 1 FROM role_skills r
                        WHERE r.role = 'web_hunter' AND r.skill_name = s.skill_name);
    IF n <> 0 THEN
        RAISE EXCEPTION 'ticket 178: % Skill(s) left that web_hunter cannot open', n;
    END IF;

    -- The one grant this file adds, and no other. A second tool arriving under
    -- `web_hunter` would be a widening this ticket did not argue for.
    SELECT count(*) INTO n FROM offline_tool_roles WHERE role = 'web_hunter';
    IF n <> 2 THEN
        RAISE EXCEPTION 'ticket 178: web_hunter holds % offline tool(s), expected 2', n;
    END IF;
END $$;
