# 105 — Two request Contracts name a queue nothing serves

**What to build:** A decision, then a handler or a deletion, for
`mcp__rk2__request_validation` and `mcp__rk2__request_report`, and for
`report_queue`, which is a declared table with no producer, no consumer and a
Contract pointing at it.

**Blocked by:** 102 — Nothing in this tree has ever created a Finding.

**Status:** ready-for-agent

- [ ] `report_queue` is settled first, because it is the cleaner case.
      Declared at `0020_state_access.sql:134` with a state CHECK, an FK to
      `programs`, two RLS policies, a row in that migration's program-scoping
      registry at `:185` and a row in `0030_corpus_corrections.sql` classifying
      it `derived`. `grep -rn "INSERT INTO report_queue"` over
      `src/redkraken/migrations/*.sql` and `src/redkraken/*.py` returns nothing,
      and no function, view or Python module reads it. The only thing in the
      tree that names it as a write target is
      `src/redkraken/roster.py:722-725`, `writes=("report_queue",)`.
- [ ] Contrast the two siblings in the same tool group, which do have
      producers, and let the contrast decide the shape: `validation_queue` is
      filled by `rk finding validate` (`src/redkraken/cli.py:1278`) and
      `pending_decisions` by `park_authorized_tool_run` and
      `rk2_ask_about_impact`. `report_queue` has neither, so a handler for
      `request_report` would be the first writer of a table nothing drains.
- [ ] `request_validation` is the one of the three unserved Contracts with a
      written reason:
      `docs/specs/production-harness-v2/issues/37-validate-finding-blindly.md:94-97`
      says the verb exists, the CLI calls it, and "the tool it makes that step
      through belongs to the orchestrator dispatch ticket". That ticket is 102.
      This ticket does not re-argue 37; it records whether 102's answer serves
      this Contract or retires it.
- [ ] Whichever way each goes, the roster stops carrying an undecided one. A
      Contract that will not be served is deleted from `CONTRACTS` or moved into
      the explicit `name -> reason` register ticket 130 introduces, in the shape
      `roster.FORBIDDEN_BUILTINS` (`roster.py:902-931`) already proves works:
      every built-in a role does not hold states why, and the compile refuses an
      unclassified one.
- [ ] The two decisions are allowed to differ, and the ticket says so. A report
      is a projection of what holds and the last step of one is reserved for a
      human (`cli.py:1331-1332`, "`validated -> reported` is reserved for a
      human actor"), which is an argument for retiring `request_report`
      outright. A validation request is a hand-off between two runtime roles,
      which is an argument for serving `request_validation`.

## Why

`docs/research/wiring/23-database-wiring.md` section 3.1 calls `report_queue`
"the cleanest instance of the defect on this axis: a declared queue with no
producer, no consumer and a contract pointing at it", and its gate G9 names it
as "the one place where the Python layer and the schema layer each declare half
of a feature and neither implements it".

`docs/research/wiring/21-agent-surface-wiring.md` section 1.3 reaches the same
two Contracts from the tool side and grades the group "deliberate but
unfinished": `src/redkraken/agent.py:143-146` states a plan, not a decision not
to build, and a plan that has been a comment since the group was compiled is
what this ticket is for.

## The decision, taken 2026-08-22

**`request_validation` is served; `request_report` and `report_queue` are
retired.** The two go different ways because one is a hand-off between two
runtime roles and the other is a request to take a step no part of the runtime
may take.

**Serving `request_validation` is a handler, not a design.** The verb already
exists: `request_validation(p_program uuid, p_finding uuid)` at
`20260815T180000Z__a_blind_validator_answers_from_the_packet.sql:639`, granted to
`rk2_runtime` at `:679`, whose body is the only `INSERT INTO validation_queue` in
the corpus (`:656`) and whose refusals are already written ("no Finding ... in
this Program"). It already has a caller, on the operator path:
`src/redkraken/validation.py:65` holds
`REQUEST = "SELECT request_validation($1::uuid, $2::uuid)"`, reached by
`rk finding validate` (`src/redkraken/cli.py:1278`). The migration says in its own
words which half is missing: "`request_validation` is the orchestrator's step ...
and `open_validation` is the runtime's" (`:632-634`). What the Contract needs is
the same three pieces ticket 102 just built for `propose_finding` -- a `REQUEST`
in `roster.CONTRACTS` (`src/redkraken/roster.py:719` is the model), a handler in
`src/redkraken/_launch.py` (`:1081`), and one more arm on the supervisor dispatch
that is already keyed on verb (`src/redkraken/agent.py:1207-1212`).

**`request_report` is retired, and `report_queue` with it.** Three facts, and any
one of them would be enough. The table has no `INSERT` anywhere in the corpus and
no reader anywhere: the only thing in the tree that names it as a write target is
`src/redkraken/roster.py:773`, and the only other mentions are registry rows
(`0020_state_access.sql:185`, `:497`, `:507`;
`0030_corpus_corrections.sql:116`; `20260810T094500Z...:409`). Its sibling
`pending_decisions` has three SQL writers (`0026_human_control.sql:751`,
`20260814T020000Z...:249`, `20260816T000000Z...:1313`) and `validation_queue` has
one; `report_queue` has none, so a handler for `request_report` would be the
first writer of a table nothing drains. And the step it would queue is reserved:
`src/redkraken/cli.py:1327-1339` says "The last step, and the only one no part of
the runtime may take: `validated -> reported` is reserved for a human actor."
A model asking to be reported would be asking for a transition its own runtime
may not make on its behalf.

Rejected: serving both, which would mean building a drain for a queue whose one
consumer is a human at a keyboard, and deleting both, which would throw away a
verb that exists, is granted, is tested and is already called.

**Where the retired Contract goes.** Not silently deleted. It moves into the
explicit `name -> reason` register, in the shape `roster.FORBIDDEN_BUILTINS`
already proves works: "a tool that is neither granted nor refused here is a tool
this roster has not classified, and the compile refuses rather than defaulting it
either way" (`src/redkraken/roster.py:1006-1009`, the dict at `:1010`).

## What was measured

`grep -rn "INSERT INTO report_queue"` over `src/redkraken/migrations/*.sql` and
`src/redkraken/*.py` returns nothing, and no function, view or Python module
selects from it. `tools/check_wiring.py` reaches the same table from two
directions and charges both to this ticket: `"W6 report_queue": "owed:105"`
(`:276`) for the table nothing inserts into, and `"W8 report_queue": "owed:105"`
(`:286`) for the declared write target with no writer -- the gate whose own
docstring calls it "the place where the Python layer and the schema layer each
declare half of a feature and neither implements it" (`:1490-1497`).

## Corrections to this ticket's citations

Four line numbers moved when ticket 102 landed, and one claim is right by a route
the ticket does not name.

`writes=("report_queue",)` is at `src/redkraken/roster.py:773`, not `:722-725`;
the `request_validation` Contract is at `:759-765`; and
`roster.FORBIDDEN_BUILTINS` is at `:1010` with its rule at `:1006-1009`, not at
`:902-931`. The plan the ticket quotes from `agent.py:143-146` is now at
`src/redkraken/agent.py:142-151`, and `SERVED_GROUPS` above it (`:138-140`) now
names `state.propose`, because 102 served it -- so the group this ticket is about
is the last one still described by a comment rather than by a decision.

Criterion 2 says `validation_queue` is "filled by `rk finding validate`
(`src/redkraken/cli.py:1278`)". True, and indirectly: no Python statement inserts
into that table. It is filled by the SQL verb `request_validation`, which
`validation.py:65` calls. That is the fact that makes serving the Contract cheap,
so it is worth stating the right way round.
