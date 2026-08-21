-- Ticket 91: the browser Skill learns to wait, and the registry follows.
--
-- ADR 0005 declined agent-browser and kept its prose, and prose that is not
-- written down anywhere is a paragraph rather than a decision. Ticket 89 read
-- their Skill corpus against the browser slice ticket 31 built and found four
-- things better said there than in `skills/browser-evidence/SKILL.md`. This
-- migration is here because the fourth of them changed a file the database
-- keeps a copy of.
--
-- What the file gained. Its fifty lines were all about evidence -- write the
-- plan, run it behind the door, cite the run, stop on a run that did not close
-- -- and every one of them was correct and is still there. What it never said
-- was anything about the failure an Agent hits first, which is a step that ran
-- before the page was ready. So: a wait discipline, per page-changing action,
-- in the one action that waits; an enumeration of the four channels whose
-- content the target wrote, because a list is checkable and a principle is not;
-- a troubleshooting section written as symptom, cause, next action against the
-- outcome keys `browser_actions` actually declares; the scoping rule that a
-- browser is the right tool for the first visit and the wrong one for the
-- hundredth; and the record-twice discipline, which this harness has had by
-- construction since ticket 31 and had never told an Agent to use.
--
-- What it did not gain. No action was added to `browser_actions`, no tool was
-- added to `allowed-tools`, and nothing in the text tells an Agent to run
-- anything its roster does not already grant. The ten verbs are the ten that
-- were there. This is a rewrite of instructions, not a capability grant, which
-- is why the only column that moves below is a digest.
--
-- The registry has to follow for the reason ticket 87's file gave and ticket
-- 92's repeated: `skills.source_sha256` and `skill_dependencies.sha256` are a
-- copy of what is on disk, and the copy is only worth having because
-- `CleanCreationTest` compares it against `skill.SKILLS`. The version moves
-- with them because a Skill's version is the digest over its dependencies'
-- digests, which is what makes "the instructions changed" a fact this database
-- can state. `browser-evidence` owns one file, so one dependency row moves and
-- the version is the digest of a one-line manifest.
--
-- The source text is Apache-2.0, "Copyright 2025 Vercel, Inc.", and the notice
-- and the statement of changes sit at the foot of the Skill body. They sit
-- there because there is nowhere else: `_compile` refuses a frontmatter key
-- nothing reads, and `document.strays` refuses a second file in a Skill
-- directory that is not a declared script or reference. The file says so in
-- its own words, so the placement is a decision a reader can find rather than
-- one they have to reconstruct.

UPDATE skill_dependencies
   SET sha256 = 'b9333b500e2f863faeecafcab892e19c29f44af4aa0e22ff933a684fc613125f'
 WHERE skill_name = 'browser-evidence'
   AND kind = 'instruction'
   AND path = 'SKILL.md';

UPDATE skills
   SET source_sha256 = 'b9333b500e2f863faeecafcab892e19c29f44af4aa0e22ff933a684fc613125f',
       version       = 'b4b6d9d931999774e04d228e1401b253b095c0d702a76c98a24f0ba175b0f81e'
 WHERE name = 'browser-evidence';

-- An UPDATE that matched nothing is a digest recorded for a row that is not
-- there, which is the one failure mode a copy of the disk has.
DO $$
DECLARE n integer;
BEGIN
    SELECT count(*) INTO n FROM skills
     WHERE name = 'browser-evidence'
       AND source_sha256 = 'b9333b500e2f863faeecafcab892e19c29f44af4aa0e22ff933a684fc613125f'
       AND version = 'b4b6d9d931999774e04d228e1401b253b095c0d702a76c98a24f0ba175b0f81e';
    IF n <> 1 THEN
        RAISE EXCEPTION 'ticket 91: the browser-evidence skill row did not move';
    END IF;

    SELECT count(*) INTO n FROM skill_dependencies
     WHERE skill_name = 'browser-evidence'
       AND kind = 'instruction'
       AND path = 'SKILL.md'
       AND sha256 = 'b9333b500e2f863faeecafcab892e19c29f44af4aa0e22ff933a684fc613125f';
    IF n <> 1 THEN
        RAISE EXCEPTION 'ticket 91: the browser-evidence instruction digest did not move';
    END IF;
END $$;
