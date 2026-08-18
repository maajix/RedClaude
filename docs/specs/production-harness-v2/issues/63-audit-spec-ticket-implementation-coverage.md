# 63 — Audit Spec, ticket and implementation coverage

**What to build:** Produce a machine-checkable proof that every requirement in the production Spec is delivered by completed implementation and at least one meaningful verification before release is considered complete.

**Blocked by:** 62 — Pass fresh-install and release hardening gates.

**Status:** resolved

- [x] All 230 numbered User Stories map to one or more implementing tickets and concrete automated or operator acceptance evidence.
- [x] Every Implementation Decision, Testing Decision, known prototype regression and Out-of-Scope constraint maps to an implementation or explicit enforcement check.
- [x] Every ticket from 01 through 62 has a resolvable implementation revision, passing acceptance evidence and no unresolved blocker.
- [x] The dependency graph is acyclic, every non-root ticket's blockers exist and every completed ticket lies on a path to a release outcome.
- [x] Coverage reports missing, duplicated, prose-only or testless requirements as release-blocking failures rather than warnings.
- [x] The audit explicitly verifies complete runtime, agents, Skills, all 49 in-scope Playbooks, UI/CLI, v1 import, long-session recovery and first-hunt prerequisites.

## What was built

`baseline/spec-evidence.tsv`, `tools/check_audit.py` and `tests/test_audit.py`.
The table is the work; the checker is what stops the table from being a
document. One row per requirement -- 230 stories, 19 Implementation Decisions,
24 Testing Decisions, 9 Out-of-Scope constraints and the 7 registered prototype
regressions, 289 rows -- and each row carries the digest of the requirement's own
text, the tickets that built it and the tests or gates that check it. 211 distinct
citations: 205 test names and the six repository gates.

**The digest is the reason the map cannot rot quietly.** Anything else -- a
count, a key, a heading -- keeps matching after somebody rewrites the sentence
underneath it, and a rewritten requirement is exactly the case where the chosen
evidence stops being the right evidence. `story:070` was mapped against
"fairness between ready Lanes after hard constraints" and cites the budget
reservation tests; reword the story and the row fails rather than quietly
covering a different claim.

**Evidence is a test this checkout can run or a gate it ships, and there is no
third kind.** That single closed vocabulary is criterion 5: a requirement with
nothing cited is `no test or gate checks it`, and a requirement citing an ADR, a
heading or a sentence is `neither a test nor a gate`. Prose citations are what an
audit of a document-heavy project drifts into, and they are refused at the same
severity as a missing row, because a document cannot go red. Names are resolved
by reading `tests/` with `ast` rather than by importing it, so the static pass
needs no database and no container -- and `--run` then executes what the rows
cite, where a skip counts as a refusal: most live arms stand down without a
server, and a citation that stood down proves nothing about the requirement
citing it.

**Criterion 3 found eleven unticked boxes on resolved tickets.** 46, 49, 50, 51,
52, 53, 54, 55, 56 and 57, and all eleven are the same missing thing: the
production evaluator's proxy route to a loopback fixture, which ticket 78
decides. Two of them already said so. The rule the checker now enforces is that a
resolved ticket may leave a box unticked only if that line names a ticket which
exists and is still open -- a deferral to finished work is not a deferral, and a
box that names nothing is a box somebody stopped looking at. The other nine lines
now carry the same `**Partial:** ... Ticket 78 closes it.` marker, which is a
documentation change with the audit standing behind it.

**Criterion 4 found thirteen finished tickets the release did not rest on.**
67 through 76 and 81 through 83 were raised beside the plan while it ran, resolved
green, and reachable from nothing: the reading walks back from ticket 65 through
blockers and every resolved ticket has to be in that set. Ticket 64 now names all
thirteen, which is also what its own first criterion asks for -- "the reviewed
head contains every completed ticket". 77 through 80 are untouched by this: they
are open, and the reading is about work that is finished and attached to nothing.

**The audit never spells the tree it audits.** `tools/` is production-classified
and its string constants may not name a documentation path, so the Spec is found
by asking the status registry which tree it classifies under this slug. That is
the same constraint ticket 62 met, and it buys the same thing: a Spec that moves
without the registry moving with it fails instead of being silently unaudited.

What this does not measure is whether the cited evidence is any good. A test that
asserts nothing satisfies every reading here. That is ticket 64's job, and the
reason these two are separate tickets rather than one.
