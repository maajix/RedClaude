# 92 — Read a method-prefixed route template out of a source Artifact

**What to build:** One agreed answer to "what is a path", used by both readers, that does not throw away the shape a target's own API client is written in.

**Blocked by:** nothing. Ticket 90's measurement found this and ADR 0006 records the numbers.

**Status:** ready-for-agent

- [ ] The two readers stop disagreeing. `jsscan.path_of` and `extract_paths.py`'s `PATH` accept the same set of literals, and where they cannot -- one is a Skill script with an empty working directory and cannot import the other -- the pattern is stated once in a comment that names the other and says they are kept in step by a test.
- [ ] A literal that carries a method in front of the path is read. `"GET /orgs/{org}/actions/runners"` reports the path, and the method beside it, because a route template that names its own verb is a better fact than one that does not.
- [ ] A braced segment is a path segment. `/orgs/{org}/labels` is a path in both readers, as it already is in `jsscan.path_of`, whose `_named_hole` emits exactly that spelling for a template hole.
- [ ] What is now accepted cannot be laundered. `path_of` refuses a literal with a space for a reason -- a sentence is not a route -- so the method form is admitted by naming the methods rather than by dropping the rule, and anything else holding a space is still refused.
- [ ] The measurement is the test. `@octokit/plugin-rest-endpoint-methods` 10.4.1's `dist-web/index.js` holds 917 endpoint strings over 591 distinct paths; a fixture carrying a representative slice of that shape is checked in, and the test states the count it expects rather than that the count is greater than zero.
- [ ] `rk2_clean_path` still accepts every path either reader now reports, or the reader does not report it. A path the analysers name and the schema refuses is a proposal that dies at the door with no way to see why.
- [ ] The registry digests follow. `skills.source_sha256`, `skills.version` and the `skill_dependencies` row for `extract_paths.py` are updated in a new migration with digests read out of `skill.SKILLS`, and `jsscan`'s `VERSION` moves if its answer shape does.

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

Two readers, two different refusals, and neither is the same rule:

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
