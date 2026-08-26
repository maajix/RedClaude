-- ---------------------------------------------------------------------------
-- 20261115T000000Z__a_root_that_answered_named_more_than_itself.sql
--
-- Refreezes `enumerate-surface` at the text it now ships.
--
-- What was measured. Database `rk2here`, 2026-08-25, 23 recon Tasks closed over
-- 108 configured applications. The Program's whole recorded surface afterwards
-- was 16 Endpoints, and the Receipts say why: of 62 exchanges that left the
-- door, 11 answered 303 and not one of those `Location` values was ever
-- requested. Two answered 200. The rest were 404, 405 or a host that does not
-- resolve.
--
-- The skill was doing what its step 2 said. That step was headed "Reach each
-- root once", and reaching each root once is what it got. The follow-through
-- was in the step -- "every redirect and subresource is its own call" -- as a
-- subordinate clause inside a sentence about Receipts, in the one step of the
-- four that carried no completion criterion. A criterion is what a step is
-- checked against; without one the heading is the whole instruction, and the
-- heading said once.
--
-- The new text splits that step in two and gives both a criterion. Step 2 asks
-- the root and the three locations a published standard reserves -- robots.txt,
-- sitemap.xml, .well-known/security.txt -- and step 3 requests what the answers
-- named: redirect chains to their end, and the scripts, manifests and documents
-- a stored body points at, one level and no further. Step 4 now also requires
-- an Endpoint to carry its method and whether it answered without a credential,
-- because `rk2_surface_facts` derives `read_method` and
-- `unauthenticated_endpoint` from exactly those two columns and a Playbook
-- triggers on the facts.
--
-- What this does not change. Nothing here is a guess at a path. The three
-- standard locations are requests a server has already agreed to answer, and
-- everything else this skill now fetches was named by an answer it already
-- holds a Receipt for. Candidate-path probing remains the `attack-surface`
-- Playbook's, behind the control it establishes first, and step 5 still refuses
-- to propose a Hypothesis.
--
-- AN UPDATE AND NOT AN UPSERT, for `20260928T020000Z`'s reason: the row exists,
-- 20260822 created it, and an INSERT that recreated it would restate the
-- description and the evidence profile as facts this file is not about.
-- ---------------------------------------------------------------------------

UPDATE skills
   SET source_sha256 = '3dddfabac7aace94bb492c92fd9070bcc1a0b14d936326c1dbecdcbf7fcdcf52',
       version       = '597a1b56c35e68d27ce79dbd4c5894f94408d7b60f6d76161e149f0dcf8c2e58'
 WHERE name = 'enumerate-surface';

-- The row the version is over. `check_skill_registry` re-derives the number by
-- hashing `kind || ' ' || path || ' ' || sha256` across this skill's dependency
-- rows, so the two statements move together or the standing check reports
-- `version_disagrees` on every run. `enumerate-surface` owns no scripts and no
-- references, so its manifest is this one line.
UPDATE skill_dependencies
   SET sha256 = '3dddfabac7aace94bb492c92fd9070bcc1a0b14d936326c1dbecdcbf7fcdcf52'
 WHERE skill_name = 'enumerate-surface' AND path = 'SKILL.md';


-- Both statements or neither. A registry whose number does not follow from its
-- rows is the failure the check exists to name, and a migration that left it
-- that way would be found by the next `rk run` rather than by this file.
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
