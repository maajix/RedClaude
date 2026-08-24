-- Ticket 99: the browser Skill names the tool that now runs it.
--
-- `mcp__rk2__browse` exists as of this ticket, so the one instruction in
-- `skills/browser-evidence/SKILL.md` that could not be followed -- "Start the
-- mission through `mcp__rk2__run_tool`", whose enum is closed to offline
-- binaries -- names the Contract that opens a mission instead. Three smaller
-- corrections travel with it, and none of them is a capability.
--
-- The Identity slot stops being something the plan carries. Ticket 97 settled
-- that it is a property of the Tool run, ticket 131 gave every Task the one
-- Identity it acts as, and the Contract declares no such argument, so a Skill
-- still telling a model to name one was telling it to write a key the gate
-- refuses.
--
-- The response headers are stated as already recorded, with the caveat that
-- makes the statement honest: the `message/http` transcript behind each
-- response carries CSP, CSP-Report-Only, COOP, COEP, CORP, Permissions-Policy,
-- Service-Worker-Allowed and Vary, and `Set-Cookie` and the target's
-- authentication headers are not there because the door strips them. A cookie
-- reading that did not know the second half would be a reading of a header
-- nobody kept.
--
-- And the repetition paragraph names `compare-responses`. It named
-- `mcp__rk2__run_tool`, and a `web_hunter` is granted exactly one program --
-- `compare_responses`, a Skill script -- so the sentence pointed a role at a
-- tool that runs nothing for it. `check_wiring`'s W10 register carried that as
-- an owed gap for as long as it was true and carries no row now.
--
-- What the file did not gain: no action was added to `browser_actions`, no
-- built-in was added to `allowed-tools`, and `mcp__rk2__run_tool` left it. The
-- ten verbs are the ten that were there. This is a rewrite of instructions
-- around one new Contract, which is why the only columns that move below are
-- digests.
--
-- The registry has to follow for the reason tickets 87, 91 and 92 each gave:
-- `skills.source_sha256` and `skill_dependencies.sha256` are a copy of what is
-- on disk, and the copy is only worth having because `CleanCreationTest`
-- compares it against `skill.SKILLS`. The version moves with them because a
-- Skill's version is the digest over its dependencies' digests.
-- `browser-evidence` owns one file, so one dependency row moves and the version
-- is the digest of a one-line manifest.

UPDATE skill_dependencies
   SET sha256 = '43b3d35f834e1542b8f83f420e35093d22f6187b3c4aa82c67a03c93c815160b'
 WHERE skill_name = 'browser-evidence'
   AND kind = 'instruction'
   AND path = 'SKILL.md';

UPDATE skills
   SET source_sha256 = '43b3d35f834e1542b8f83f420e35093d22f6187b3c4aa82c67a03c93c815160b',
       version       = 'eb5ebfdc5b4a6e82010a081d39206cdd41ca08e8ea8b7c434ab70834fe6f3400'
 WHERE name = 'browser-evidence';

-- An UPDATE that matched nothing is a digest recorded for a row that is not
-- there, which is the one failure mode a copy of the disk has.
DO $$
DECLARE n integer;
BEGIN
    SELECT count(*) INTO n FROM skills
     WHERE name = 'browser-evidence'
       AND source_sha256 = '43b3d35f834e1542b8f83f420e35093d22f6187b3c4aa82c67a03c93c815160b'
       AND version = 'eb5ebfdc5b4a6e82010a081d39206cdd41ca08e8ea8b7c434ab70834fe6f3400';
    IF n <> 1 THEN
        RAISE EXCEPTION 'ticket 99: the browser-evidence skill row did not move';
    END IF;

    SELECT count(*) INTO n FROM skill_dependencies
     WHERE skill_name = 'browser-evidence'
       AND kind = 'instruction'
       AND path = 'SKILL.md'
       AND sha256 = '43b3d35f834e1542b8f83f420e35093d22f6187b3c4aa82c67a03c93c815160b';
    IF n <> 1 THEN
        RAISE EXCEPTION 'ticket 99: the browser-evidence instruction digest did not move';
    END IF;
END $$;
