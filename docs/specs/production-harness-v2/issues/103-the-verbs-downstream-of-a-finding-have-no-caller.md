# 103 — The impact, severity, pivot and chain verbs have no caller either

**What to build:** Callers for the six granted verbs that run from a validated
Finding to a sound kill chain, on whatever dispatch shape ticket 102 settles.

**Blocked by:** 102 — Nothing in this tree has ever created a Finding.

**Status:** ready-for-agent

- [ ] Each of these six is granted to `rk2_runtime` and has zero callers in
      `src/redkraken/*.py`, verified by grep against the current tree:
      `open_impact_task`
      (`20260816T000000Z__impact_is_authorized_before_it_is_proved.sql:1209`,
      granted `:2033`), `state_severity` (`20260816T000000Z...:1725`, granted
      `:2036`), `apply_computed_cvss` (`20260816T000000Z...:1851`, granted
      `:2037`), `issue_pivot_stamp`
      (`20260817T000000Z__a_pivot_is_stamped_from_the_run_that_showed_it.sql:931`,
      granted `:1121`), `build_kill_chain`
      (`20260818T000000Z__a_chain_is_composed_and_stays_sound.sql:538`, granted
      `:924`) and `read_kill_chain` (`20260818T000000Z...:797`, granted `:925`).
      `open_impact_replay` is the one verb of this group that does have a
      caller, at `src/redkraken/replay.py:96`.
- [ ] Ticket 38's factual claim is corrected rather than repeated. It says
      "`open_impact_task`, `open_impact_replay` and `state_severity` are called
      by the CLI and by the tests". Two thirds of that is false: only
      `open_impact_replay` has a Python caller. `open_impact_task` and
      `state_severity` appear in `tests/test_database.py` (three and six times
      respectively) and nowhere else. A dated correction note is appended to
      ticket 38 naming this ticket, and its `**Status:** resolved` is not
      changed.
- [ ] `read_kill_chain` is granted to `rk2_human` and has no caller in `src/`:
      one reference in `tests/test_database.py` and nothing else. `rk report
      chain` (`src/redkraken/cli.py:1517`) is a live verb that reaches
      `read_chain_report`, not this, so the operator's read of a composed chain
      is a verb granted to the operator's role and reachable from no command.
      It is not the only such verb -- fifty-six functions carry a `rk2_human`
      EXECUTE grant and about half have no Python caller -- but most of those
      are predicates a standing check or another function calls from inside SQL,
      and this one is a top-level read with nothing above it.
- [ ] `apply_computed_cvss` is the one member of this group already documented
      as knowingly dead, at
      `20260819T000000Z__a_chain_unlock_earns_its_place_in_the_queue.sql:440-443`:
      "038 dropped `apply_computed_severity` and left `apply_computed_cvss`
      behind it, and nothing in this corpus calls that function." The ticket
      decides between wiring it and dropping it, and does not leave it as the
      third state.
- [ ] `compose_finding_report`
      (`20260820T000000Z__a_report_is_a_projection_of_what_holds.sql:461`) is
      classified with the same reading and is not silently carried. It is
      owner-only, it has no grant to any role, and `src/redkraken/reporting.py`
      calls `read_finding_report` instead. Either it is superseded and says so
      in a `COMMENT ON`, or it is wired.
- [ ] Tickets 39 and 40 each carry a dated note naming this ticket as the owner
      of the deferral. Their own claims check out -- `issue_pivot_stamp` appears
      once in `tests/test_database.py`, `build_kill_chain` four times and
      `read_kill_chain` once, and neither ticket claimed a CLI caller -- so the
      note corrects the record about the ticket they deferred to and nothing
      else.

## Why

`docs/research/wiring/21-agent-surface-wiring.md` section 3.2, table B, and
`docs/research/wiring/23-database-wiring.md` section 4.2, which reach the same
twelve verbs from opposite directions: one from the grant, one from the
catalogue. Report 23 puts it as "a designed verb with a full test suite and no
production caller", and notes that every one of the 26 uncalled functions in the
corpus is granted to `rk2_runtime`, the role the harness connects as, and that
eleven of them are additionally published in `runtime_verb_surface`.

Ticket 65's fourth criterion is "A demonstrated pivot is evaluated in a sound
kill chain, while an intentionally missing or invalid pivot remains visibly
unreportable." Nothing in this tree can build the chain that criterion is about.

## The decision, taken 2026-08-22

**The six do not get one caller; they get three shapes, and the line that
splits them is whether the verb takes a parameter the runtime could not fill
out of a row it wrote itself.**

**Three served Contracts, on ticket 102's pattern.** `open_impact_task`
(`20260816T000000Z__impact_is_authorized_before_it_is_proved.sql:1209`), because
`p_spec` is a whole Test specification and the block that makes it an impact
Test is four authored fields `rk2_impact_problem` checks (`:88-141`): a class, an
`effect` sentence, a `cleanup` sentence and the ordinal of the action that reads
the state the Test leaves behind. Nothing in the database says which request
undoes a write. `state_severity` (`:1725`), because the band and the rationale
are a judgement: the basis is constrained by state and the band is not, and
`p_rationale` is prose between 20 and 2000 characters (`:1698`). And
`compose_finding_report`
(`20260820T000000Z__a_report_is_a_projection_of_what_holds.sql:461`), because the
file was written around exactly that: "which observation witnesses which effect
is a judgement, not a join" (`:436-437`).

**Three runtime steps.** `apply_computed_cvss` (`20260816T000000Z...:1851`) takes
one parameter and its answer is computed by `compute_finding_cvss`
(`0034_reports.sql:743-787`); the live `report_blockers`
(`20260906T000000Z__a_person_reports_a_finding_and_lifts_a_gate.sql:140`) already
emits `cvss_stale` with the computed vector written out in its own detail
(`:181-185`), so a model asked to call this verb would be handing the runtime
back a sentence the runtime wrote. The step goes where that blocker would
otherwise be raised. `issue_pivot_stamp`
(`20260817T000000Z__a_pivot_is_stamped_from_the_run_that_showed_it.sql:931`),
because both parameters name rows this machine created, every column of the
stamp comes out of `rk2_pivot_source` and the file says so at `:992-993`, and a
second call on the same Tool run answers `"issued": false` with the same digest.
It belongs immediately after `close_impact_replay` in the path `replay.py:96`
already runs. `build_kill_chain`
(`20260818T000000Z__a_chain_is_composed_and_stays_sound.sql:538`), because the
members are the stamps and the graph over them is derived by four functions that
take nothing but the Program id and the stamp set -- `rk2_chain_entry` (`:62`),
`rk2_chain_edges` (`:94`), `rk2_chain_depths` (`:116`) and `rk2_chain_reached`
(`:162`). The one thing a model could contribute is `p_flow`, and the column's
own comment is "Recorded and never read" (`:521-522`); nothing else in the corpus
names the column.

**One operator read.** `read_kill_chain` (`20260818T000000Z...:797`) is granted
`rk2_runtime, rk2_human` (`:925`) and is reachable from no command. Its home is a
sibling of `rk report chain` (`src/redkraken/cli.py:1517`, reaching
`read_chain_report` at `src/redkraken/reporting.py:69`), which renders the chain;
this answers whether it is still sound. It is not a Contract, because a model
that could ask whether its own chain is sound would be reading the verdict on its
own work.

Rejected: one shape for all six. It is what four earlier tickets each deferred to
a fifth, and the measurement is that three of these verbs have nothing a model
could contribute and one is already the operator's by grant.

## What was measured

Every verb was called on a real Program with a real validated Finding, and
called again with arguments a model could plausibly send
(`docs/research/decisions/32-chain-scope-and-eval.md`, "Ticket 103"). The
decisive outputs: `compose_finding_report` answered with
`{"code": "cvss_stale", "detail": "stored null, computed AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:N"}`
in its blocker list, and after `apply_computed_cvss` ran, `report_blockers` over
the same Program returned no `cvss_stale` row; `build_kill_chain` answered
`{"built": true, ...}` and then `{"built": false, ...}` with an identical
`source_sha256` for the same two members proposed in the other order;
`issue_pivot_stamp` called twice on one Tool run answered `"issued": false` the
second time. A catalogue search over every function body in the database for the
word `flow` returned `build_kill_chain`, `rk2_chain_problem`,
`record_callback_interaction` and `record_v1_import`, and none of them reads the
column.

Criterion 1 re-verified against this tree: all six have zero callers in
`src/redkraken/*.py`, and `open_impact_replay` is the one member of the group
that has one, at `src/redkraken/replay.py:96`.

## Correction: `compose_finding_report` is not owner-only

Criterion 5 says it "is owner-only, it has no grant to any role". That is wrong,
and the error is a wider surface rather than a narrower one. The absence of a
`GRANT` line in the migration is not the absence of a grant:
`20260820T000000Z__a_report_is_a_projection_of_what_holds.sql` contains no
`GRANT` and no `REVOKE` at all, and `0029_roles_and_grants.sql:103-104` sets
`ALTER DEFAULT PRIVILEGES FOR ROLE rk2_owner IN SCHEMA public GRANT EXECUTE ON
FUNCTIONS TO rk2_runtime`, which is a standing rule over every function created
after it. The default PUBLIC EXECUTE was never revoked either. Every sibling verb
in this group carries an explicit `REVOKE ALL ... FROM PUBLIC`
(`20260816T000000Z...:2015`, `:2018`, `:2019`;
`20260817T000000Z...:1109`; `20260818T000000Z...:911-912`); this one has none.
Measured off `pg_proc.proacl` the ACL reads
`{=X/rk2_owner,rk2_owner=X/rk2_owner,rk2_runtime=X/rk2_owner}`
(`docs/research/decisions/32-chain-scope-and-eval.md`, "One correction to the
ticket"), and `docs/research/wiring/23-database-wiring.md:679` had it right as
"PUBLIC, rk2_owner, rk2_runtime". Wiring it as a served Contract therefore
carries a second piece of work: the `REVOKE ALL ... FROM PUBLIC` its siblings
all have.

## Two smaller corrections

`state_severity` is granted to `rk2_runtime, rk2_human`
(`20260816T000000Z...:2036`), not to `rk2_runtime` alone, so criterion 3's
"`read_kill_chain` is granted to `rk2_human`" is true of two verbs in this group
rather than one. It does not change the shape: `state_severity`'s human grant is
for the operator overriding a band, and the Contract is for the hunter stating
one.

`report_blockers`'s live definition is at
`20260906T000000Z__a_person_reports_a_finding_and_lifts_a_gate.sql:140`, not the
`20260816T000000Z...:1874` one; the `cvss_stale` arm that makes
`apply_computed_cvss` a runtime step rather than a Contract is at
`20260906T000000Z...:181-185`.
