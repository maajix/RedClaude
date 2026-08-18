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

`baseline/spec-verification.tsv`, `tools/check_audit.py` and `tests/test_audit.py`.
The table is the work; the checker is what stops the table from being a
document. One row per requirement -- 230 stories, 19 Implementation Decisions,
24 Testing Decisions, 9 Out-of-Scope constraints, the 6 release conditions under
Further Notes and the 7 registered prototype regressions, 295 rows -- and each row
carries the digest of the requirement's own text, the tickets that built it and
the tests or gates that check it. 213 distinct citations: 208 test names and five
repository gates. The Spec's seven top-level sections are frozen too, so a
requirement arriving under a heading nobody parses is release-blocking rather
than invisible, and a story is digested at every line it wraps onto rather than
at its first, because half a requirement is not one.

**The column is `verification`, not `evidence`.** `CONTEXT.md` owns Evidence as
the role an observation plays for a claim; what a row here names is what would
report the requirement broken, which is a different thing, and the v1 disposition
ledger beside it already spells that column `verification`. One vocabulary, one
word per idea.

**What a citation is, is decided once.** `citations()` reads a row's column and
returns a kind -- test, gate, owed or prose -- and every reading after it compares
kinds. The prefixes `gate:` and `owed:` are cut in exactly one place. The same
tightening runs through what a citation may name: a class holding no test method,
directly or from a base in its own module, is not a test this checkout can run,
because `unittest` loads it to an empty suite and an empty suite passes for the
same reason a document does. And the one skip `--run` forgives is now matched as
a whole sentence rather than as a substring, so a test cannot excuse itself from
being measured by quoting the exception inside a longer reason.

**The audit is inside its own range.** Criterion 3 now reads tickets 01 through
63 rather than 01 through 62: an audit that exempts the ticket it was delivered
by is an audit with exactly one ticket nobody reads, and it is the one whose
author had the most reason to want it unread.

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
severity as a missing row, because a document cannot go red. This gate is not
allowed to be its own evidence either, which is a rule it needed: story 230 asks
for the final Standards and Spec review and testing decision 24 for final
acceptance, and both were first mapped to the gate whose own docstring disclaims
measuring evidence quality. What they say now is `owed:64` and `owed:65` -- the
one honest way to have no evidence, naming the open ticket that owes it, exactly
as a resolved ticket's unticked box names the ticket that closes it. An owed row
is a tracked absence rather than a claim, and ticket 65 resolving while one is
still there is itself a failure. Names are resolved
by reading `tests/` with `ast` rather than by importing it, so the static pass
needs no database and no container -- and `--run` then executes what the rows
cite, tests and gates both, where a skip counts as a refusal: most live arms
stand down without a server, and a citation that stood down proves nothing about
the requirement citing it. Two carve-outs, both named: the release gate is
reported as deferred rather than run, because it builds an install and provisions
two databases, and the one skip accepted is the inverse case the suite states in
its own words -- a test requiring the runtime to be absent cannot run in the
interpreter this mode requires it to be present in.

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

**Criterion 6 names a number, so the audit names it too.** "All 49 in-scope
Playbooks" is checked against the gate that enforces the catalogue: the audit
holds 49 itself and refuses if `check_coverage` is planning a different one, read
out of that gate's source rather than imported, because importing it would pull
the application into a check that reads files. With `--run` executing cited
gates, that catalogue check is then actually run rather than merely shipped.

**`--run` inherits the conditions of every arm it runs.** Two of them bit during
this ticket and are worth writing down. The Agent SDK has to be installed at the
version `KNOWN_RUNTIME` pins -- a newer one is an unmeasured runtime, and a dozen
agent citations refuse rather than pass, correctly. And the surface benchmarks
measure wall time inside the process the audit is already running the other two
thousand tests in: run under load, `slate` measured 1698.1 ms against a 1500 ms
budget and the audit refused; run alone on the same machine it measured 192.1 ms.
The audit is right both times, which is why the fix is an idle host rather than a
carve-out.

What this does not measure is whether the cited evidence is any good. A test that
asserts nothing satisfies every reading here. That is ticket 64's job, and the
reason these two are separate tickets rather than one. It is also not one of the
gates the release gate runs inside its export: criterion 3 reads this
repository's history for the commit that resolved each ticket, and a tarball
committed once as a checkout would answer that with one synthetic revision for
every ticket in the plan.
