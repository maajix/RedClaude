-- ---------------------------------------------------------------------------
-- 20260825T000000Z__the_analyst_carries_the_packs_it_reads_source_with.sql
--                                                                   (ticket 48)
--
-- The registry is a copy of the corpus, and 037 wrote the copy that was true
-- when it applied. Ticket 48 moved the corpus: `analyse-source` gained the ten
-- v1 code-review packs as `references/`, gained `extract_paths.py` so that its
-- own step 2 stops conceding that a bundle is read by eye, and its `SKILL.md`
-- changed to say both. Twelve dependency rows where there was one, and a new
-- manifest digest over them.
--
-- This is what a Skill edit costs, and the cost is the point. 037 registered
-- the digest so that drift is a question with an answer; the answer is only
-- worth having if the row moves when the file does. `check_skill_registry`
-- recomputes `version` from the dependency rows and reports `version_disagrees`
-- otherwise, so a corpus edit that skipped this migration would fail the gate
-- rather than quietly serve one text while recording another.
--
-- A new file rather than an edit to 037: a recorded migration whose file has
-- changed is schema drift and `rk db migrate` refuses the whole corpus for it.
--
-- The digests below are Python's, computed by `skill.py` from the files in the
-- wheel. Nothing here is authority for them -- the gate derives `version` from
-- the dependency rows independently, and `tests/test_database.py` compares
-- every column to what the compiler holds.
-- ---------------------------------------------------------------------------


-- ===========================================================================
-- 1. The manifest, as rows
-- ===========================================================================

-- Replaced rather than merged. A dependency list is the whole manifest and not
-- a set of additions: a reference deleted from the corpus has to leave the
-- table too, or the version the gate recomputes is over a file nobody ships.
DELETE FROM skill_dependencies WHERE skill_name = 'analyse-source';

INSERT INTO skill_dependencies (skill_name, kind, path, sha256) VALUES
    ('analyse-source', 'instruction', 'SKILL.md',
     'be9bdfcf3164becff9843cfcb6a4457b2505ff8f2871ed1764b44a0abd3a59aa'),
    ('analyse-source', 'reference', 'references/code-review.md',
     '4bbcdb88dcb18604b2f9e19a82c221b647fa04bc8fee79f013658546865433db'),
    ('analyse-source', 'reference', 'references/sinks-csharp.md',
     '64710fbba82da92a444340190c0468062785b5f3bca93be0b8be6ede938c5a11'),
    ('analyse-source', 'reference', 'references/sinks-go.md',
     '3b46d8aa1b3f959e003080ed4c98d7f693c00f2e6a977e82633fcb8a99b6aad8'),
    ('analyse-source', 'reference', 'references/sinks-java.md',
     'f2709caa6747cdb3b289c4585d4b918f40f8b713e8f689156de9e0443cdd2d06'),
    ('analyse-source', 'reference', 'references/sinks-js.md',
     'b434ebedef5d9d6226f4d72868b5a1d01ef31697347b1a94ddeeb44027b55db4'),
    ('analyse-source', 'reference', 'references/sinks-kotlin.md',
     '6c3d1a3c9193d03b17b9322c9190052345b4abbf0ef057b175076ed9fc0dd13d'),
    ('analyse-source', 'reference', 'references/sinks-php.md',
     '1f4605e855dd0cee51ef6025912ba17978a2fb9be5f4076f16754284e379632c'),
    ('analyse-source', 'reference', 'references/sinks-python.md',
     'ff66cd78e2b6fcd7359fb62e315c9bed519b19d2cc2cfd99d1f7c2a47baf918e'),
    ('analyse-source', 'reference', 'references/sinks-ruby.md',
     '61b10ab26498df0738c623709787ec053ff5a3aaf453e25552b7700ecea4670b'),
    ('analyse-source', 'reference', 'references/sinks-rust.md',
     '6f1ac72a2380d7745b239716c39013356286f28136850bc28f17f6fe382f2f9e'),
    ('analyse-source', 'script', 'scripts/extract_paths.py',
     'f66047d48ce8a20d8276edf6722fb6cc5126e86404e8c5c3600d715107c435e7');


-- ===========================================================================
-- 2. The skill row the manifest is the version of
-- ===========================================================================

-- `description` and `evidence_profile_id` did not move: what the analyst is for
-- and what it must leave behind are the same. The instruction digest and the
-- manifest digest did, which is the whole of the edit.
UPDATE skills
   SET source_sha256 = 'be9bdfcf3164becff9843cfcb6a4457b2505ff8f2871ed1764b44a0abd3a59aa',
       version       = 'a56586b724fae8727fdd6748494f38378677a6640499f8a35f1cb66a9fa8c199'
 WHERE name = 'analyse-source';
