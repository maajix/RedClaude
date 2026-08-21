# 92 — Read a method-prefixed route template out of a source Artifact

**What to build:** One agreed answer to "what is a path", used by both readers, that does not throw away the shape a target's own API client is written in.

**Blocked by:** nothing. Ticket 90's measurement found this and ADR 0006 records the numbers.

**Status:** resolved

- [x] The two readers stop disagreeing about what a path *is*. They answer different questions and always will -- one reports routes for grounding, the other reports what an analyst can read -- so the rule is narrower and checkable: for any literal both of them call a path, the path they report is the same string. A test feeds one corpus to both and says so. They cannot share code, because `extract_paths.py` runs as a Skill script with an empty working directory and nothing beside it to import, so each carries the pattern with a comment naming the other and naming the test.
- [x] A literal that carries a method in front of the path is read. `"GET /orgs/{org}/actions/runners"` reports the path, and the method beside it, because a route template that names its own verb is a better fact than one that does not.
- [x] A braced segment is a path segment. `/orgs/{org}/labels` is a path in both readers, as it already is in `jsscan.path_of`, whose `_named_hole` emits exactly that spelling for a template hole.
- [x] What is now accepted cannot be laundered. `path_of` refuses a literal with a space for a reason -- a sentence is not a route -- so the method form is admitted by naming the methods rather than by dropping the rule, and anything else holding a space is still refused.
- [x] The measurement is the test. `@octokit/plugin-rest-endpoint-methods` 10.4.1's `dist-web/index.js` holds 917 endpoint strings over 591 distinct paths; a fixture carrying a representative slice of that shape is checked in, and the test states the count it expects rather than that the count is greater than zero.
- [x] `js_routes` still answers 0 on this bundle, and a test says so. Its 0 is correct and is not the defect: octokit reaches `octokit.request.defaults(defaults)` with the route in an object, so there is no call site carrying a path literal. A change that made `js_routes` report the 591 would have broken its grounding rule, which is the one thing here worth more than the paths.
- [x] `rk2_clean_path` accepts every path either reader reports, or the reader does not report it. This already fails today and is the worst of the three faults: `extract_paths` keeps the query string, its declared case reports `/api/orders?id=1&sort=asc`, `analyser = 'extract_paths.py'` means `_named` files that into `tool_run_paths`, and `rk2_source_citation` cleans both sides before comparing -- so the row cleans to nothing, matches nothing, and an analyst who proposes `/api/orders` citing that very run is dropped `path_not_in_output` by the run that found it.
- [x] Nothing the query string said is lost. `paths` carries the route, because that is the key `_named` files and every entry in it has to clean; the literal that carried a query is still reported, under its own key, because the parameter half of a surface is a real fact and this Skill was right to want it.
- [x] The registry digests follow. `skills.source_sha256`, `skills.version` and the `skill_dependencies` row for `extract_paths.py` are updated in a new migration with digests read out of `skill.SKILLS`, and `jsscan`'s `VERSION` moves if its answer shape does.

## Why this is asked

Ticket 90 measured CodeGraph against the harness on real fetched source, and the
first subject indicted both. `@octokit/plugin-rest-endpoint-methods` is 88 KB
that is almost nothing but a target's API surface: 917 endpoint strings over 591
distinct paths, in the plainest possible form.

CodeGraph reported one of them. So did we.

That is the finding worth acting on, because the CodeGraph half is a property of
what a symbol table is and ours is a pattern somebody can change this afternoon.
A client bundle that enumerates a target's whole API is close to the best thing a
hunt can pull out of a source Artifact, and the shape it is written in --
`"METHOD /path/{param}"` -- is a convention, not an accident. OpenAPI generators
emit it. So does every hand-written route table that keeps the verb beside the
path.

## What is actually wrong, exactly

Three disagreements, and the third one is not about octokit at all:

- `src/redkraken/jsscan.py`'s `path_of` opens with
  `if not value or "\n" in value or " " in value: return None`. The space between
  `GET` and `/orgs` is what stops it. Given `/orgs/{org}/labels` on its own it
  answers `/orgs/{org}/labels`, and `_named_hole` already spells a template hole
  `{id}` -- so the braced form is a shape this module emits and then declines to
  read back.
- `src/redkraken/skills/analyse-source/scripts/extract_paths.py`'s `PATH` is
  `^/(?!/)(?:[A-Za-z0-9._~%!&'()*+,;=:@/?-]|\$\{[^{}]*\})+$`. It refuses the same
  literal at the leading `/` that is not there, and it would still refuse 522 of
  the 591 with the method stripped, because `{` is not in the class and only
  `${...}` is. 68 of 591 match.

- And underneath both, the one the measurement did not find and reading the code
  did: `jsscan.path_of` cuts `?` and `#` because `rk2_clean_path` refuses them,
  while `extract_paths`'s `PATH` deliberately keeps `?` -- "a query string is the
  parameter half of what this Skill grounds", says the comment, and it is right
  about the fact and wrong about where to put it. `extract_paths` is registered
  with `analyser = 'extract_paths.py'`, so `tool.serve` files its `paths` into
  `tool_run_paths`, and `rk2_source_citation` runs both sides through
  `rk2_clean_path` before comparing. A stored `/api/orders?id=1&sort=asc` cleans
  to nothing. It grounds nothing. An analyst who reads that answer, proposes
  `/api/orders` and cites the run that found it is dropped `path_not_in_output`
  by the run that found it, and the drop reason says the run never named the
  path.

The space rule in `path_of` is right and should stay: a sentence holding a slash
is not a route, and admitting one would be inventing surface. So this is not
"drop the check". It is "one method name, one space, one path" as its own
admitted shape, and everything else refused as before.

## The rule that must not bend

Whatever comes out of either reader is a claim about bytes the run read, and
`_named` files it against the Artifact's digest so a proposed route is held
against a row rather than against a sentence. Widening what counts as a path
widens what can be proposed, which is why the fourth criterion is not optional:
the new shape is admitted by naming it, never by relaxing the refusal that
guards everything else.

`rk2_clean_path` is the other end of the same rope. A reader that reports a path
the schema will not store has moved the failure from a place with a message to a
place without one.

## Comments

Built. Measured against the file the ticket names: `dist-web/index.js` from
`@octokit/plugin-rest-endpoint-methods` 10.4.1, 88 KB, 917 endpoint strings over
591 distinct paths, which is 588 once the RFC 6570 query expansions are cut the
way both readers now cut them.

| Reader | Before | After | Extra | Missed |
| --- | --- | --- | --- | --- |
| `extract_paths.py` | 0 | 587 | 0 | `/` |
| `js_parse` | 1 | 588 | 0 | none |

The "before" column is ADR 0006's own row, not a fresh reading: `js_parse` found
one of them and `extract_paths` found none, because the leading `/` a literal
starting `GET ` does not have is checked before anything else it would fail.

The one `extract_paths` misses is the bare root, refused on purpose: a bundle
that told an analyst only that it has a `/` has told them nothing.

Three changes in each program, and one of them was a live defect rather than a
gap. `VERB` admits one named method and exactly one space in front of a path, so
the space rule that keeps a sentence from becoming a route is intact and the
method is reported as its own key. `PATH` is RFC 3986's `query` production
written out -- which is where the missing `$` came from, a `sub-delim` this
repository's inherited class had dropped -- plus `{...}` and `${...}` for the
hole the source left. And `groundable` restates `rk2_clean_path` where the
analyser can reach it, so a query string leaves `paths` and stays in `literals`:
before this, every query-bearing entry `extract_paths` filed into
`tool_run_paths` cleaned to nothing on both sides of `rk2_source_citation`, and
an analyst proposing the route that run had just found was dropped
`path_not_in_output` by the run that found it.

Two things nearly went wrong and are worth recording. The first cut of the fix
turned `/repos/{owner}/{repo}/actions/caches{?key,ref}` into
`/repos/{owner}/{repo}/actions/caches{` -- six of them on the real bundle -- and
that malformed string is `groundable`, so it would have been filed. `route()` is
depth-aware for that reason and a test states the property rather than the six
cases. The second is `js_routes`, which still answers 0 here: octokit reaches
`octokit.request.defaults(defaults)` with the route inside an object, so no call
site carries a path literal, and a change that made it report the 588 would have
broken the grounding rule that is worth more than the paths. A test now says so.

`jsscan.VERSION` moved to `rk2-jsscan 2` because `path_literals` gained a
`method` key, and `20260922T040000Z__a_route_template_names_its_own_method.sql`
carries the `analyse-source` digests, read out of `skill.SKILLS` rather than
typed.

The two-axis code review found four more, all of them the same mistake in
different places: a rule was widened and the widening was not named.

- `groundable` refused `//` only at the front. `rk2_clean_path` refuses
  `v LIKE '%//%'` anywhere, so `/api//orders` reached `tool_run_paths` and could
  never be matched -- the exact `path_not_in_output` drop criterion 7 exists to
  close, still open inside the fix for it.
- `VERB` ended in `$`, which matches before a trailing newline, and `path_of`
  cut the method off before it reached its own newline guard. So `"GET /x\n"`
  became a route. The rule the method form is admitted through was the one it
  was widening. `\Z` now.
- The query cut was depth-aware but cut at any depth, so `/x/{a{?b}}` gave
  `/x/{a`. Dangling, `groundable`, filed. The cut is made at depth zero only,
  and `path_of` refuses a result whose braces do not pair -- which
  `extract_paths.PATH` already did, so this was also a criterion 1 disagreement.
- `\$?\{[^{}]*\}` admitted a space and a newline inside a hole, so
  `/a{see the docs}` was a path. A hole is one segment. `[^{}\s]` now.

Each has a test. The measurement was re-run afterwards and is unchanged: 588 and
587 of 588.

Two things the review is right about and that are recorded rather than fixed.
The criteria were edited during implementation: criterion 1 was narrowed from
"accept the same set of literals" to "for any literal both of them call a path,
the path they report is the same string", because the two readers answer
different questions on purpose -- `extract_paths` files a host under `urls` and
`jsscan.path_of` follows it to its path -- and the original wording could only
be met by breaking one of them. `DIVIDED` in the test names every such case.
Criterion 8 was added, not weakened. And the numbers in this comment are a
measurement against a file this repository does not ship, so the test carries
the shape and ADR 0006 carries the reading; neither is re-derivable from the
tree alone, which is the honest limit of a finding about somebody else's bundle.

