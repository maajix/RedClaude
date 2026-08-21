-- Ticket 92: a route template names its own method, and the registry follows.
--
-- Ticket 90's measurement pointed a real client bundle at this harness's two
-- path readers, and ADR 0006 records what came back: `js_parse` 1 of 591 and
-- `extract_paths` none of them. The bundle is `@octokit/plugin-rest-endpoint-
-- methods`, and it writes a whole API surface as literals shaped
-- `"GET /orgs/{org}/actions/runners"` -- one method and one path in one string.
-- `jsscan.path_of` refused every one of them because the literal holds a space;
-- `extract_paths` refused them because they do not start with a slash, and
-- would still have refused 522 of the 591 with the method stripped, because `{`
-- was not in its character class. Both now read 587 and 588 of 588.
--
-- Three things changed in the two programs, and this file is only here for the
-- fourth.
--
-- One: a literal may name its method in front of its own path. The methods are
-- named rather than matched and the separator is exactly one space, so prose
-- holding a slash does not walk in behind them, and the method is reported as
-- its own key rather than left inside the route.
--
-- Two: a braced segment is a path segment. `/orgs/{org}` is a parameterised
-- route, and `jsscan._named_hole` already spells a hole `{id}`, so refusing the
-- braced spelling was refusing what this harness itself writes.
--
-- Three: the query string leaves `paths` and stays in `literals`. This is the
-- half that was a live defect rather than a gap. `tool.serve` files an
-- analyser's `paths` into `tool_run_paths`, and `rk2_source_citation` cleans
-- both a proposed `path_template` and the stored path through `rk2_clean_path`
-- before comparing them -- and `rk2_clean_path` refuses a `?`. So every
-- query-bearing entry `extract_paths` filed could match nothing, and an analyst
-- proposing the route the run had just found was dropped `path_not_in_output`
-- by the run that found it. `groundable` in both programs is that acceptor
-- restated, so nothing reaches `tool_run_paths` that the schema will refuse.
-- Nothing the query string said is lost: `literals` carries the string as the
-- build wrote it, method and query and all.
--
-- The registry has to follow here for the reason ticket 87's file gave for
-- `compare-responses`: `skills.source_sha256` and `skill_dependencies.sha256`
-- are a copy of what is on disk, and the copy is only worth having because
-- something compares it. `SKILL.md` moved because its declared checks state the
-- answer shape, and the answer shape gained a key; `extract_paths.py` moved
-- because it is the program. The version moves with them because a Skill's
-- version is the digest over its dependencies' digests, which is what makes
-- "the text changed" a fact this database can state.
--
-- `offline_tools` is untouched. A Skill script's version is the digest of the
-- bytes that ran, computed at run time by `tool.serve` and checked against
-- `version_pattern`, so there is no registered digest of this program to move.

UPDATE skill_dependencies
   SET sha256 = 'b131d9b8f503c2e153b0eac8542f0d44db5159bb7648b5fbb122d24fc6c24b1d'
 WHERE skill_name = 'analyse-source'
   AND kind = 'instruction'
   AND path = 'SKILL.md';

UPDATE skill_dependencies
   SET sha256 = '405229c5633219e01922956bef3c65e44d18c05d7a57e079ac04bb5b42e41737'
 WHERE skill_name = 'analyse-source'
   AND kind = 'script'
   AND path = 'scripts/extract_paths.py';

UPDATE skills
   SET source_sha256 = 'b131d9b8f503c2e153b0eac8542f0d44db5159bb7648b5fbb122d24fc6c24b1d',
       version       = 'bf2397fa870c0956f62b1e5725f05dbc9661a86fa4434f597d0874b617178407'
 WHERE name = 'analyse-source';

-- An UPDATE that matched nothing is a digest recorded for a row that is not
-- there, which is the one failure mode a copy of the disk has.
DO $$
DECLARE n integer;
BEGIN
    SELECT count(*) INTO n FROM skills
     WHERE name = 'analyse-source'
       AND source_sha256 = 'b131d9b8f503c2e153b0eac8542f0d44db5159bb7648b5fbb122d24fc6c24b1d';
    IF n <> 1 THEN
        RAISE EXCEPTION 'ticket 92: the analyse-source skill row did not move';
    END IF;

    SELECT count(*) INTO n FROM skill_dependencies
     WHERE skill_name = 'analyse-source'
       AND sha256 IN ('b131d9b8f503c2e153b0eac8542f0d44db5159bb7648b5fbb122d24fc6c24b1d',
                      '405229c5633219e01922956bef3c65e44d18c05d7a57e079ac04bb5b42e41737');
    IF n <> 2 THEN
        RAISE EXCEPTION 'ticket 92: expected 2 moved dependency digests, found %', n;
    END IF;

    SELECT count(*) INTO n FROM check_skill_scripts();
    IF n > 0 THEN
        RAISE EXCEPTION 'ticket 92 breaks ph2-87: % skill script violation(s)', n;
    END IF;
END $$;
