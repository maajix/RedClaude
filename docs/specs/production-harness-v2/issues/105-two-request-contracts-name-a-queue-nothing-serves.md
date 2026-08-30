# 105 — Two request Contracts name a queue nothing serves

**What to build:** A decision, then a handler or a deletion, for
`mcp__rk2__request_validation` and `mcp__rk2__request_report`, and for
`report_queue`, which is a declared table with no producer, no consumer and a
Contract pointing at it.

**Blocked by:** 102 — Nothing in this tree has ever created a Finding.

**Status:** done

- [x] `report_queue` is settled first, because it is the cleaner case.
      Declared at `0020_state_access.sql:134` with a state CHECK, an FK to
      `programs`, two RLS policies, a row in that migration's program-scoping
      registry at `:185` and a row in `0030_corpus_corrections.sql` classifying
      it `derived`. `grep -rn "INSERT INTO report_queue"` over
      `src/redkraken/migrations/*.sql` and `src/redkraken/*.py` returns nothing,
      and no function, view or Python module reads it. The only thing in the
      tree that names it as a write target is
      `src/redkraken/roster.py:722-725`, `writes=("report_queue",)`.
- [x] Contrast the two siblings in the same tool group, which do have
      producers, and let the contrast decide the shape: `validation_queue` is
      filled by `rk finding validate` (`src/redkraken/cli.py:1278`) and
      `pending_decisions` by `park_authorized_tool_run` and
      `rk2_ask_about_impact`. `report_queue` has neither, so a handler for
      `request_report` would be the first writer of a table nothing drains.
- [x] `request_validation` is the one of the three unserved Contracts with a
      written reason:
      `docs/specs/production-harness-v2/issues/37-validate-finding-blindly.md:94-97`
      says the verb exists, the CLI calls it, and "the tool it makes that step
      through belongs to the orchestrator dispatch ticket". That ticket is 102.
      This ticket does not re-argue 37; it records whether 102's answer serves
      this Contract or retires it.
- [x] Whichever way each goes, the roster stops carrying an undecided one. A
      Contract that will not be served is deleted from `CONTRACTS` or moved into
      the explicit `name -> reason` register ticket 130 introduces, in the shape
      `roster.FORBIDDEN_BUILTINS` (`roster.py:902-931`) already proves works:
      every built-in a role does not hold states why, and the compile refuses an
      unclassified one.
- [x] The two decisions are allowed to differ, and the ticket says so. A report
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

## What the unserved Contract costs, measured 2026-08-29

This ticket's blocker is gone. "102 — Nothing in this tree has ever created a
Finding" was true when it was written; the `rk2here` engagement now holds four.
All four are `candidate`, and the database says in its own words why each one
will stay that way:

```
 label | severity |                    was_fehlt
-------+----------+--------------------------------------------------
 F1    | info     | nothing asked for the Finding F1 to be validated
 F2    | info     | nothing asked for the Finding F2 to be validated
 F3    | info     | nothing asked for the Finding F3 to be validated
 F4    | info     | nothing asked for the Finding F4 to be validated
```

That sentence is `rk2_validation_refusal`, and what it is refusing over is the
empty `validation_queue` this Contract exists to fill. The consequence over the
whole Program:

- `validate` Tasks ever opened: **0**, in any status.
- `report` Tasks ever opened: **0**.
- `js_analyst` Agent runs in six hours of hunting: **0**, against 30
  orchestrator, 16 `web_hunter` and 11 `performer`.
- `conclude` Tasks: 2 done, 2 abandoned -- the contrast that makes the
  mechanism, because `state.conclude` is served whole and its Tasks exist.

So the campaign hunts, proposes Findings and settles claims, and every Finding
it opens stops at `candidate` forever. There is one way out and it is the
operator's: `rk finding validate` calls `request_validation` through
`validation.py:65` and then `open_validation_session`, which is exactly the
hand-off the migration describes at
`20260815T180000Z__a_blind_validator_answers_from_the_packet.sql:632-634` --
"`request_validation` is the orchestrator's step ... and `open_validation` is
the runtime's". Today the orchestrator's step has no tool, so a person takes it
or nobody does.

The comment this ticket was opened against still reads the same way and is now
the last unbuilt half of a shipped feature (`src/redkraken/agent.py:155-167`):

> the other two -- validation and a report -- are requests ticket 105 serves.
> Those two are the whole of what this tree declares and no launch serves.

Nothing in this measurement changes the decision taken 2026-08-22. It prices
the delay: a hunt that cannot ask for validation is a hunt whose output an
operator has to finish by hand, one Finding at a time.

## What was built, 2026-08-30

Both halves of the decision taken on 2026-08-22, in that order.

**`request_validation` is served.** Four pieces and no new design.

- `20261224T000000Z__the_orchestrator_asks_for_a_validation.sql` adds
  `propose_validation(text)`, the label-taking wrapper `propose_severity` and
  `propose_finding_report` already prove: it resolves the label through
  `rk2_finding_for_label`, answers `rk2_no_such_finding(p_label)` when there is
  none, and catches every refusal class so one refused ask does not abort the
  transaction the supervisor holds open across a run.
- `roster.py` moves `mcp__rk2__request_validation` into a three-member
  `sched.pick`, so the orchestrator holds it.
- `agent.py` dispatches it to `_validation`, one arm beside `_park`.
- `_launch.py` builds the handler with `_carry`, the same partial the other four
  carried verbs use, and gives it a description.

**`request_report` is retired and `report_queue` is dropped.** The same
migration deletes the table's `purge_cascade_edges` and `event_table_exempt`
rows and drops it; `20261225T000000Z__the_two_surfaces_the_previous_file_left_behind.sql`
finishes the pair of registers `check_runtime_privileges` reads, because the
first file left four `runtime_table_surface` rows naming nothing and one granted
verb with no `runtime_verb_surface` row. The Contract itself moves into
`roster.RETIRED_CONTRACTS`, a `name -> reason` dict the compile checks against
`CONTRACTS` and every tool group, so a retired name that came back would be
refused rather than silently re-served.

**The objective asks for it.** This is ticket 221's lesson applied before it
could repeat: `state_severity` was served and never called because no objective
mentioned it. `execution.PLANNING` now ends with a paragraph naming
`mcp__rk2__get_evidence` -- the only tool this role holds that carries a Finding
label at all (`packet.py:588`) -- and `mcp__rk2__request_validation`, and it asks
for one Finding per generation rather than one per Finding, because a second ask
about the same Finding is refused and a role that asked nine times would spend
eight calls learning that.

## What it cost, and what it did not buy

`validation_queue` now has a producer the runtime can reach. It still has only
one drain, and that drain is a person: `rk finding validate`
(`src/redkraken/validation.py`), reached from a terminal. Nothing in `hunt.sh`
or `supervise.sh` calls it, and `grep -rn "validation_queue" src/redkraken/*.py`
returns two hits, both in `validation.py`.

So the ask is a work list rather than a hand-off that completes itself. That is
still worth serving, and it is not the defect this ticket was opened against:
`report_queue` had no drain at all, which is why it was dropped rather than
served. The automatic drain is ticket 224.

## What was verified

- `tests/test_database.py::DownstreamVerbTest` gains three cases: a Finding this
  Program holds is queued by the label alone, a second ask says which state it
  is already in, and a label the Program does not hold is refused rather than
  raised. 20 tests, all pass.
- `tests/test_agent.py::test_no_contract_is_declared_that_a_launch_does_not_serve`
  is the old `..._are_the_two_the_runtime_answers_for` with an empty list: 23
  Contracts, 23 served, nothing declared that no launch answers.
- `tools/check_wiring.py` W1 has no `owed` rows left, and its register comment
  records both decisions rather than the open question it used to hold. All four
  gates exit 0.
