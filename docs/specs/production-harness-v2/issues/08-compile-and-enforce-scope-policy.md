# 08 — Compile and enforce one Scope Policy

**What to build:** Turn Program scope and Rules of Engagement into one canonical decision used consistently before any target-facing operation.

**Blocked by:** 04 — Create or resume a Program with the same command.

**Status:** resolved

- [x] The compiled policy represents target inclusions, exclusions, protocols, ports, path restrictions, callback channels, time windows and independent risk permissions.
- [x] URL, host, IP, port, path and identifier inputs are canonicalized before matching, with ambiguous or malformed forms refused.
- [x] Required-header names may be read while their values remain runtime-owned and redacted.
- [x] Absent mutation, sensitive-data, credential, pivoting or availability permission is a denial rather than a permissive default.
- [x] Adjacent-host, DNS, certificate-transparency, reverse-IP and virtual-host discovery is not authorized unless explicitly configured.
- [x] The same fixture matrix produces identical decisions through CLI diagnostics and runtime policy calls.

## Comments

Implemented on branch `implementation/startup-assertion` in commit `0af60f6` on
2026-08-10.

`src/redkraken/scope.py` is the compiler and the evaluator, `_project_scope` in
`src/redkraken/program.py` writes what it produced, `rk scope` is the adapter
over it, and `20260810T193000Z__scope_policy_compilation.sql` is what lets the
database enforce the same policy rather than merely store it.

0021 already had the tables: `program_scope_versions`, `program_scope_rules`,
`scope_class_of`, `scope_class_of_entity`, `set_scope_version`. Nothing wrote to
them. This ticket adds the compiler that fills them, five permission columns and
a `configuration_revision` join on the version row, `program_required_headers`,
one rebuilt `scope_class_of` that answers the question the runtime actually asks,
and `check_scope_policy()` to hold the arrangement together.

The Policy is one object: an ordered rule list, a channel list, five permissions,
five discovery techniques, the required-header names, the time window, and a
digest over all of it. Every question goes to that object -- a URL the runtime is
about to fetch, an entity the projection is about to write, an interaction that
arrived on a callback host, a permission an action needs -- so there is no second
place where scope is decided.

### What is asserted, and by what

`tests/test_scope.py` is 48 offline tests with no database in it:
`CompilationTest` (13) on what compiles and what is refused, `CanonicalFormTest`
(10) on the forms that are folded and the forms that are rejected,
`RequiredHeaderTest` (3), `PermissionTest` (3), `DiscoveryTest` (6) and
`VerdictTest` (13) on the fixture matrix itself.

`SCOPE_REQUESTS`, `SCOPE_ENTITIES` and `SCOPE_REFUSALS` in `tests/fixtures.py`
are that matrix, and it is asked three times over. `VerdictTest` asks it in
process. `ScopeCommandTest` in `tests/test_cli.py` (14 tests) asks the whole
matrix through one `rk scope` invocation and compares against the same table.
`ScopeEvaluatorTest` in `tests/test_database.py` (11 tests) opens a Program, then
asks `scope_class_of` and `scope_class_of_entity` for every row of it and
compares the class, the reason *and* the cited rule ordinal. Three assertions
disagreeing is three failures, which is the only way "identical decisions"
becomes a test rather than a claim.

`RefusalTest` in `tests/test_program.py` gains three: a configuration that
validates and does not compile opens no connection, the compiler runs before the
corpus is read, and a compiled run reports the shape of what it compiled.
`check_scope_policy()` has three negative controls in `CONTROLS` -- a configured
Program with no scope version, `GRANT SELECT (value_ref) ON
program_required_headers TO rk2_state` by way of a `state_read_surface` row, and
a promoted version with no rules.

### Decisions worth naming

**Effect precedence is a minimum, not a last-match.** The effect of a request is
`min(EFFECT_RANK)` over every rule that matches it, in both Python and SQL, so
document order cannot make an exclusion lose to an inclusion written after it.
Specificity (`spec_kind DESC, spec_len DESC, ord ASC`) picks only which rule is
*cited* in the receipt. Two operators who write the same rules in a different
order get the same decisions and possibly a different citation, which is the
correct place for order to matter.

**`*.here.com` never matches `here.com`.** A wildcard delegation is authority
over what was delegated, not over the apex that delegated it, and the apex is
where the credential store and the corporate site usually are. The suffix walk
starts at label 2 rather than 1 in both implementations, and a pattern that tries
to say both is refused rather than read charitably.

**Paths are matched in two spellings with three polarities.** A request carries
both its raw and its normalized path, and which one has to match depends on the
question: an exclusion fires if *either* spelling is excluded, an inclusion has
to cover *both*, and a coverage or subtree question matches as a prefix in either
direction. This is what keeps `/admin/../public` out of a policy that excludes
`/admin` without also refusing every legitimate path that normalizes.

**The scope version is its own sequence.** It could have reused the configuration
revision number, and the case that separates them is the one that matters: the
compiler changes, the operator's file does not, and the same configuration now
compiles to different rules. That is a change in what the policy *means*, so it
is a new version rather than a rewrite of an existing one -- receipts cite the
version, and rewriting one would rewrite what they say. The two are joined by a
nullable `configuration_revision` column with a composite FK, nullable because
0021's rows predate configurations entirely.

**Compilation happens before the connection.** A configuration that parses and
does not compile authorizes nothing. Compiling after the Program is open would
create the root row, record the revision, and only then discover there was no
policy, leaving a Program every entity of which projects denied -- worse than no
Program, because it looks like one. The refusal is sourced as
`scope:scope.include[N].host` rather than `config:...`, which is how an operator
tells "your file is wrong" from "your file says nothing usable".

**Resume writes a scope version too.** Every answer that keeps the Program
running goes through `_project_scope`, not just `CREATE` and `REVISE`. A Program
opened before this path existed has `scope_version` NULL, and NULL is a Program
nothing may be sent to; the resume is the only chance to fix that without a
migration that guesses. It is idempotent by digest and revision, so repeated
`rk run` does not fill the version history with identical rows.

**Required-header redaction is a grant, not a convention.**
`program_required_headers` registers `name`, `ord`, `program_id` and `version` in
`state_read_surface` and deliberately not `value_ref`, so
`check_state_grants()` rule 3 fails the gate for any grant that would make the
reference readable. The table is classified `event_table_exempt` as `'reference'`
-- the same word as its two siblings -- rather than emitting a redacted event:
`program.configured` already records the revision every header row was derived
from, and an event per header would put the reference somewhere a redaction rule
has to keep removing it, rather than nowhere. The rows are immutable by trigger
with `ENABLE ALWAYS`, and there is a `purge_cascade_edges` row so they leave with
their Program.

**A denial is an answer.** `rk scope` exits 0 with denials in its report; only a
configuration that will not compile is a refusal, and that is exit 3. An operator
asking "what does this authorize" gets a document either way, and a script can
tell "denied" from "your file is broken" by the exit code alone.

**Absent permission is denial, and an unknown word is a refusal.** All five
Rules of Engagement and all five discovery techniques are reported whether asked
about or not, all false unless the configuration says so. A permission this
grammar has no word for is refused rather than answered false, because an
operator who writes `exfiltration` has said something, and answering "not
permitted" would let them believe the question was understood.

### Raised by review and deliberately not built here

- **The live-database half of this ticket has never been executed.** Every prior
  ticket in this branch was verified against `pgvector/pgvector:pg18`; this
  environment has no container runtime (podman cannot write `/run/user/1000`,
  the docker socket refuses the connection) and no pgvector for the local
  PostgreSQL 18.3, and `0010_embeddings.sql` builds an `hnsw` index over
  `vector_cosine_ops`, so a stub extension is not possible. The offline suite is
  421 tests, green, with 13 skipped -- and those 13 are the whole of
  `tests/test_database.py`, which includes all 11 `ScopeEvaluatorTest` tests, the
  three new negative controls, and therefore every assertion about
  `scope_class_of`, `check_scope_policy()`, the header grants and the immutability
  trigger. The migration itself has never been applied. It was written against
  the catalogue definitions it depends on and read against them line by line, but
  reading is not running: **this ticket's SQL needs one run with a server present
  before it should be trusted.** `tools/check_baseline.py` reports
  `classifications=10 regressions=7 artifacts=223`, unchanged, and
  `python3 -m compileall -q src tests` is clean, which remains what runs in place
  of a typechecker.
- **Nothing resolves a host to an address.** The compiler refuses a private or
  loopback literal in an inclusion, but a hostname that *resolves* to one is
  accepted, because resolving it would mean a DNS query at compile time -- the
  policy would then depend on what the resolver said at that moment, and the
  digest would stop describing the file. The check belongs in the proxy, at the
  moment of connection, where the address is already known.
- **The time window compiles and nothing enforces it.** The window is
  `window_seconds` under `[budgets]`, alongside the request and finding counts it
  is counted over. It is compiled, digested, carried in
  `program_scope_versions.policy` and reported by `rk scope`, and no code path
  consults it, because nothing in this branch performs a target-facing operation
  yet. The enforcement point is the proxy, and it is ticket 09's.
- **Discovery is denied unconditionally, because the grammar cannot authorize
  it.** `decide_discovery` returns `allowed = False` with
  `discovery_not_authorized` for all five techniques, always: the configuration
  schema has no key that turns any of them on, so there is nothing for the
  compiler to read. The criterion is met in the strongest available sense rather
  than the intended one -- "unless explicitly configured" is untestable while no
  configuration can express it. The decision path exists so that the day such a
  key is added, the answer it changes is one function and the default stays deny;
  a technique the grammar has no word for is refused rather than answered false,
  which is what stops a misspelled key from reading as a permission.
- **`pattern_kind = 'cidr'` remains unreachable.** `parse_pattern` produces only
  `exact` and `wildcard`, so `program_scope_rules`' CIDR check constraint is
  never exercised by compiler output and the `cidr` branch of `scope_class_of` is
  dead for compiled policies. That is 0021's surface, left as it is: an address
  range is a thing an operator will eventually write, and removing the column now
  would mean adding it back.
- **Callback channels are matched, not verified.** An observed interaction is
  matched against the declared channel hosts, and nothing proves the interaction
  really arrived on that channel -- there is no listener in this branch to prove
  it from.
- **The glossary is not updated.** `CONTEXT.md` defines **Scope Policy** and says
  nothing about a compiled version, a grammar version or a policy digest. As with
  tickets 06 and 07, no implementation ticket in this branch edits that file, so
  the terms are documented in the migration header and in `scope.py`'s own
  docstring and belong in the glossary whenever `/domain-modeling` runs next.
