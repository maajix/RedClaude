# 117 — The CIDR arm of scope evaluation has no writer

**What to build:** A decision, then the code that follows from it: either the
compiler learns to emit `cidr` rules and tiers, or the columns, the index, the
constraints and the matching arms that exist only for them come out.

**Blocked by:** nothing.

**Status:** resolved

- [x] The decision is recorded before anything is changed. Address-range scope
      and effort tiers are both in the schema and in neither compiler, and
      which of the two answers is right is a product question rather than a
      wiring one: a program that scopes by `10.0.0.0/8` is a real bug bounty
      scope, and no configuration file the loader accepts can express one.
- [x] The gap is stated as it stands. `program_scope_rules` declares `net cidr`
      (`0021_scope_policy.sql:91`), `tier text` (`:94`) and
      `allow_private_ips boolean NOT NULL DEFAULT false` (`:95`).
      `src/redkraken/program.py:910-921` writes the rules with a thirteen-column
      list -- `program_id, version, ord, effect, effect_rank, pattern_kind,
      pattern_text, match_key, protocol, port, path_prefix, spec_kind,
      spec_len` -- and none of those three is in it. The compiler that produces
      the rows produces exactly two pattern kinds, `Pattern(kind="wildcard"...)`
      at `src/redkraken/scope.py:579` and `Pattern(kind="exact"...)` at `:584`.
- [x] Each thing that is therefore unreachable is named, and the ticket says
      which of them is a defect and which is inert:
      the `'cidr'` arm of `pattern_kind text NOT NULL CHECK (pattern_kind IN
      ('exact','wildcard','cidr'))` (`0021:86`);
      the two paired CHECKs at `0021:109-110`, which assert both directions of
      "a CIDR rule has a `net` and no `match_key`";
      the partial GiST index `scope_rules_net_idx ... WHERE pattern_kind =
      'cidr'` (`0021:119-121`), which indexes a column that is always NULL over
      a predicate that is never true;
      the containment arm of the live classifier,
      `r.pattern_kind = 'cidr' AND r.net >>= (...)::inet`
      (`20260810T193000Z__scope_policy_compilation.sql:341-343`);
      and `allow_private_ips`, which has no writer and no reader anywhere in
      `src/` -- the only occurrence in the tree is its own declaration.
- [x] The tier half is treated as its own question, because it fails one step
      further along. `tier` is never set on a rule and `default_tier` is never
      set on a version, so the tier expression
      (`20260810T193000Z...:394-399`) always yields NULL, `entities.scope_tier`
      is always NULL, `CHECK (tier IS NULL OR effect = 'target')` (`0021:112`)
      can never fail, and `v_records` publishes `"scope_tier": null` for every
      Entity in the system. An effort policy that is declared, projected,
      published and always NULL is worse than one that is absent, because a
      reader cannot tell the two apart.
- [x] Whichever way the decision goes, the outcome is testable. If the columns
      stay, a configuration with a CIDR target compiles, projects, and an
      Entity inside the range comes out `target`. If they go, the migration
      that removes them says in its own prose why the design chose host-shaped
      scope only, so the next reader does not re-add them.

## Why

`docs/research/wiring/23-database-wiring.md` section 1.3(c). The report grades
the columns load-bearing rather than harmless, and the reason is that the
schema is the design document here: a `cidr` arm in a CHECK constraint is a
claim that the system evaluates address ranges, and nothing does.

Two corrections. The report cites the classifier arm as `0021:292` and the tier
expression as `0021:333`. Both are in the superseded definition:
`20260810T193000Z__scope_policy_compilation.sql:297` drops
`scope_class_of(uuid, integer, text, integer, text, text)` and `:299` recreates
it with two more arguments, so the live arms are at `:341-343` and `:394-399`.
The `0021` lines are what shipped first and are not what runs. The report also
names the constraints `program_scope_rules_check` and
`program_scope_rules_check1`; those are the names Postgres assigned, and the
CHECKs are written anonymously in the file at `0021:109-110`.

This is a decision, not a defect, which is why it is `needs-triage` rather than
`ready-for-agent`: nothing is broken today, and both answers are defensible.
What is not defensible is leaving it unanswered, because every future reader of
`0021` spends the same hour working out that the arm is dead.

## The decision, taken 2026-08-22

**Split the ticket in two and answer the halves differently. The address-range
half stays and the compiler learns to emit it. The effort-tier half comes out,
and so does `allow_private_ips`.**

### The range half stays

The sentence that settles it is in the function the ranges were built for.
`authorize_egress_address` re-decides the destination as the literal address the
proxy pinned, and it asks the coverage question with this reason
(`20260810T231500Z__pinned_destination_scope.sql:110-116`): "A withdrawal is
asked about the machine: **an operator who excluded a network excluded it**, and
an address that is only out of bounds for one path was already refused -- or
allowed -- by name, at the decision this one sits behind." That gate ships, it is
granted to `rk2_proxy` (`:127-129`), the proxy calls it on every request
(`src/redkraken/proxy.py:1024-1036`), and the only rule kind that can express
"a network" is the one no configuration can produce. The `cidr` arm is not
decoration on a schema; it is the second half of a two-gate design whose first
half is complete.

Ranges are also the ordinary shape of a real scope. The grammar already admits a
single address -- `_HOST_SHAPE` reads "must be a hostname, a wildcard such as
`*.example.com`, or an address" (`src/redkraken/config.py:136`) and
`parse_pattern` returns `Pattern(kind="exact", ...)` for one
(`src/redkraken/scope.py:584`) -- so a Program scoped to `203.0.113.0/24` is
expressible today as 256 configuration entries and a Program scoped to a /16 or
to any IPv6 range is not expressible at all. Deleting the arm would be choosing
that as the answer.

**Rejected: removing the columns, the index, the constraints and the classifier
arm.** It would delete a working evaluator -- the containment arm at
`20260810T193000Z__scope_policy_compilation.sql:341-343` is live and correct --
to avoid writing the compiler side, and it would leave `authorize_egress_address`
asserting a withdrawal nobody can state.

**Four things the implementation must carry, because the evidence names them.**

1. **The compile-time refusal is already specified.** `scope.address_refusal`
   (`scope.py:220-245`) says it is "shared by policy compilation and the egress
   door. An inclusion that the compiler accepts must not become an address the
   proxy refuses only after a capability has been spent." A range inclusion is
   subject to the same rule: a target range that is not globally routable must be
   refused where it is written, not at the door. An *exclusion* range is not, for
   the reason `config.py:132-135` already gives about broad hosts -- "Breadth here
   withdraws authority rather than claiming it."
2. **A range decides addresses, never names, and that is deliberate.** The
   containment arm only fires when the host being asked about is an address
   literal -- `r.net >>= (CASE WHEN nh.h ~ '^([0-9.]+|[0-9a-f:]+)$' THEN nh.h
   END)::inet` (`20260810T193000Z...:341-343`). A request naming
   `www.example.com` is therefore not admitted by the range its address falls in,
   and cannot be: the door decides before it resolves, which `proxy.resolve` and
   `proxy.destination` state as the order the design turns on -- "So the order is
   decide, then resolve, then dial" (`proxy.py:1803-1811`). The ticket's fifth
   criterion should be written as *an Entity reached by address inside the range
   comes out `target`*, because the name form of that test is a design the
   corpus has already refused.
3. **A range mints no configured subject, exactly as a wildcard does not.**
   `record_configured_subjects` filters `AND r.pattern_kind = 'exact'`
   (`20260831T000000Z...:203`) before building base URLs. So a Program scoped
   only by range opens with nothing to hunt, the same way a Program scoped only
   by `*.example.com` does today. That is the existing precedent and the range
   joins it; whether an operator should be warned at compile time belongs with
   ticket 83, not here.
4. **Four edits, not one.** The ticket's framing ("the compiler learns to emit
   `cidr`") reads as one file. It is: `config.py` (`_HOST_SHAPE` and the shape
   regexes at `:128-136`), `scope.parse_pattern` (`:553-584`) plus the three
   `Pattern` properties that assume a host -- `match_key` at `:535-536`,
   `spec_kind` at `:539-540`, `spec_len` at `:543-544` -- plus `Rule.matches`
   (`:609`) and `Rule.row()` (`:645-666`), which today emits twelve keys and none
   of them is `net`; and `program.py:911-922`, whose column list is thirteen names
   long. The CHECK pair at `0021:109-110` means `row()` must emit `net` and omit
   `match_key` on exactly the range rules, or every insert fails.

### The tier half comes out

`tier` and `default_tier` are an effort policy that is declared, projected,
published and always NULL, and nothing at all consumes the published value.
`grep -rn "scope_tier" src/redkraken/*.py tools/` returns nothing: the column is
projected by `0021:539`, indexed at `:489-493`, and emitted into every `v_records`
payload -- live definition `20260814T080000Z__a_refutation_is_kept_and_made_due.sql:1171`
-- and read by no ranker, no scheduler and no Python. And `grep -rn "tier"
src/redkraken/config.py src/redkraken/scope.py` returns nothing at all, so there
is no grammar to fill it from and no compiler to teach. Unlike the range half
there is no second gate waiting for it. If effort policy is wanted later it
belongs where effort is actually spent -- the budget and lane tables -- and not on
a scope rule, which is a statement about authority.

`allow_private_ips` is a prototype vestige whose job was taken by something
stricter. It is a per-rule opt-out in v1's policy engine
(`docs/prototype/walking-skeleton/vendor/scope-proxy/policy.py:160`, "if not
match.get('allow_private_ips')"), and v2 replaced it with an unconditional
deny-by-default at the door: `scope.address_refusal` (`scope.py:220-245`) and
`proxy.unroutable` (`proxy.py:1780-1801`), whose docstring says "Deny by default,
like the policy above it: an address is dialled because it is one the public
internet routes to, not because it failed to match a list of bad ones." The
evaluation case that genuinely needs a private address does not go through it
either -- it is a separate database question, `authorize_fixture_address`
(`proxy.py:1039-1051`). A boolean that would let a rule re-open what the door
closes should not survive as a column.

## What was measured

`grep -rn "allow_private_ips" src/ tools/ docs/` returns **one** occurrence under
`src/`: its own declaration at `0021_scope_policy.sql:95`. Every other hit is in
`docs/prototype/`, which is v1. `grep -rn "tier" src/redkraken/config.py
src/redkraken/scope.py` returns **zero** lines. `grep -rn "scope_tier"
src/redkraken/*.py tools/` returns **zero** lines. `program.py:911-922` writes
thirteen columns and `scope.Rule.row()` (`:645-666`) returns twelve keys, one of
which (`origin`) is not a column; neither mentions `net`, `tier` or
`allow_private_ips`. The compiler produces exactly two pattern kinds
(`scope.py:579`, `:584`).

## Correction: `proxy.py` is not the second evaluator, and the second evaluator is
still real

Any reading of this ticket that says "the door evaluates scope in Python" is
wrong, and it matters because it changes how many places learn about ranges.
The proxy holds no opinion: "The decision is the database's ... The proxy does not
get to have an opinion" (`proxy.py:15-22`), and the reason is a grant -- "This
role holds no `SELECT` on `program_scope_rules` and `scope_class_of` is not a
definer function, so the proxy cannot read the policy even to agree with it"
(`proxy.py:1028-1031`). What makes the Python evaluator a live second
implementation is the operator diagnostic: `scope.diagnose` (`scope.py:1315`)
"reaches no database", is what `rk scope` runs (`src/redkraken/cli.py:2117-2122`),
and its own docstring names the three-way obligation -- "the tests put the same
fixture matrix through here, through the evaluator directly and through
`scope_class_of`, and a disagreement is a bug in one of the three"
(`scope.py:1330-1332`). So ranges must land in the Python evaluator and in the
diagnostic's grammar as well as in the compiler, or the three-way matrix starts
disagreeing.

## Correction: the mirror the CHECK claims does not exist

`0021_scope_policy.sql:112` carries the comment "effort policy may only ride on a
target rule (mirrors the Python compiler)". There is nothing in the Python
compiler to mirror -- `scope.py` contains no `tier` at any line. Whoever removes
the column should not preserve the comment.

## What was built

The decision's split was implemented as written: the range half stays and the
compiler emits it, the tier half and `allow_private_ips` come out.

**The range half.** `parse_pattern` (`src/redkraken/scope.py:616-644`) now reads
a slash before anything else and returns a third kind, `Pattern(kind="cidr",
text=...)`, canonicalised through a new `parse_network` (`:226-242`); a pattern
carrying both a slash and a `*` is refused, because a suffix test over names and
containment over addresses would have to be read as one of them and neither
reading is what an operator wrote. `Pattern` (`:551-641`) answers the three
questions the schema asks of a rule differently for that kind: `match_key` is
None and `net` is the text, so the CHECK pair at `0021:109-110` is satisfied
from the same object rather than at the insert; `spec_kind` is `SPEC_CIDR`;
`spec_len` is the prefix length, so a /24 is cited over the /8 that also
matched. `covers` does address containment and `covers_subtree` returns False,
which is the second point of the decision expressed in code. `Rule.row()` gained
a thirteenth key, `net` (`:741`), and `program.py:910-925` gained the matching
column in both the insert list and the `jsonb_to_recordset` definition (`net
cidr`). The loader learned the shape it must accept for any of that to be
reachable: `_Reader.host` takes `ranges=True` from `_rule` (`config.py:384-429`,
`:544`) and hands a slashed value to a new `_range`, which parses it with
`ipaddress.ip_network(value, strict=True)` and, when only the non-strict parse
succeeds, names the range the operator meant -- `10.0.0.1/8` is refused with
"write 10.0.0.0/8" rather than silently widened. `GRAMMAR_VERSION` went to 2
(`scope.py:64-71`), because a policy digest computed under a grammar with two
pattern kinds is not a statement about a grammar with three.

`_unroutable` (`scope.py:1194-1240`) now takes the `Pattern` rather than the
host text and, for a range, applies `address_refusal` to both edges of the
block. This is the first point of the decision -- an inclusion the compiler
accepts must not become an address the proxy refuses after a capability was
spent -- and it is deliberately not complete: `172.0.0.0/8` has two globally
routable edges and contains `172.16.0.0/12`, so it is admitted here and its
private interior is refused at the door by `proxy.unroutable`. An exclusion is
exempt, exactly as a broad host is, because breadth there withdraws authority.

**The tier half.**
`20260929T030000Z__a_range_is_scope_and_a_tier_never_was.sql` drops
`program_scope_rules.tier`, `program_scope_rules.allow_private_ips`,
`program_scope_versions.default_tier` and `entities.scope_tier`. Four columns
cost five objects re-issued in full, because Postgres will not drop a column
anything depends on: `scope_class_of` and `scope_class_of_entity` are dropped
and recreated without the `tierpick` CTE and with a three-column `RETURNS
TABLE`; `entities_scope_is_projected` and `refresh_scope_projection` lose every
`scope_tier` clause; `v_records` is rewritten whole, minus `'scope_tier',
e.scope_tier`; `scope_rules_key_idx` and `entities_in_scope_idx` are recreated
without the dropped columns in their `INCLUDE` lists. A sixth thing goes with
them and it is a row, not an object: `state_read_surface` carried
`entities.scope_tier` as part of the agent read surface, and
`check_state_grants()` fails a registry row whose column no longer exists, so
the migration deletes it in the same file. The file's prose carries
the argument the fifth criterion asks for, so the next reader does not re-add
them, and it says what an operator who set `allow_private_ips` should be told:
nothing in `src/` ever read it, and the door it would have re-opened is now
`scope.address_refusal` at compile time and `proxy.unroutable` at dial time,
with `authorize_fixture_address` as the one lawful way to reach a private
address. The CHECK comment at `0021:112` that claimed to mirror a Python
compiler went with the column it constrained, as the last correction asks.

## What it is asserted with

Nine tests, and an apply-time proof where no test file was available.
`tests/test_config.py` gains three:

- `test_an_address_range_is_accepted_where_a_scope_rule_names_a_host`
- `test_a_range_whose_address_is_inside_it_is_refused_with_the_one_meant`
- `test_a_callback_endpoint_is_not_a_range`

`tests/test_scope.py` gains six:

- `test_a_range_compiles_to_a_rule_that_matches_by_containment`
- `test_a_range_decides_an_address_and_never_a_name`
- `test_a_range_is_cited_over_a_wider_range_and_under_an_exact_host`
- `test_an_inclusion_may_not_name_a_range_the_proxy_will_refuse`
- `test_an_exclusion_may_name_a_private_range`
- `test_a_range_is_neither_a_wildcard_nor_a_widened_address`

The migration's own section 3 is a rolled-back `DO` block that inserts a `cidr`
target rule, asserts `scope_class_of_entity` answers `target` for an address
inside the range, `denied` for one outside it and `denied` for a *name*, then
projects the version and asserts the two Entities' `scope_class` -- which is the
fifth criterion, written the way the decision's second point says it must be
written. Section 4 asserts the four columns are gone from
`information_schema.columns` and that `pg_get_viewdef('v_records')` no longer
mentions `scope_tier`.

## Five places the ticket or its decision was wrong

1. **The edit to `Rule.matches` (`:609`) was not needed.** The decision's fourth
   point lists it among the files. `Rule.matches` delegates the host question to
   `Pattern.covers`, so teaching the pattern taught the rule; `matches` is
   unchanged in this build.
2. **`_HOST_SHAPE` and the shape regexes at `config.py:128-136` were not
   changed either.** A range is detected by the slash before any host regex
   runs, so the regexes still describe exactly what they described. What was
   added is a second message, `_RANGE_SHAPE`, because an operator who wrote a
   malformed range should be told what a range looks like and not what a
   hostname looks like.
3. **The diagnostic needed no grammar of its own.** The correction section says
   ranges "must land in the Python evaluator and in the diagnostic's grammar as
   well as in the compiler". `scope.diagnose` compiles the document through
   `compile_policy` and evaluates through the same `Rule` objects, so it has no
   separate grammar to teach; the three-way matrix agrees because there is one
   parser, not three.
4. **`record_configured_subjects` is the fourth edit the ticket does not
   mention, and the decision is why it stays unedited.** Its `AND r.pattern_kind
   = 'exact'` filter (`20260831T000000Z...:203`) means a Program scoped only by
   range opens with no configured subject and therefore no first Task. That is
   the decision's third point rather than a defect, so nothing was changed
   there -- but it is a consequence an operator can hit, and the ticket's
   criteria do not name it.
5. **"What was measured" could not have found the fifth reader of
   `scope_tier`, and there is one.** The section proves the column is dead with
   greps over `src/` and `tools/`, and those greps are correct. The reader it
   cannot see is a row: `state_read_surface` names `entities.scope_tier`
   because `0030_corpus_corrections.sql:256-263` seeded that registry from
   `has_column_privilege('rk2_state', ...)` rather than by naming columns, so
   no grep for the word finds it. Dropping the column without deleting the row
   leaves `check_state_grants()` failing with
   `state_surface_names_missing_object,entities.scope_tier`, which is how this
   build found it -- `CleanCreationTest` went red before the delete was added.

## What was left alone, and why

The partial GiST index `scope_rules_net_idx` (`0021:119-121`) was not touched:
its predicate is now reachable and its column is now sometimes non-NULL, which
is the state it was written for. `README.md:246` says "A scope entry names a
hostname, an address, or a wildcard such as `*.example.com`" and is now
incomplete, but that file was outside this change's ownership and no gate reads
the sentence.
