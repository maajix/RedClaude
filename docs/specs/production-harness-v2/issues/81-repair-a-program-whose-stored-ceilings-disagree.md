# 81 — Repair a Program whose stored ceilings disagree

**What to build:** Give an operator a way back from a Program row whose budget ceilings contradict each other, and stop one such Program from refusing every other Program in the database.

**Blocked by:** nothing.

**Status:** resolved

- [x] A Program whose stored ceilings disagree can be repaired by supplying a corrected configuration, rather than only by editing the database by hand.
- [x] A Program in that state does not refuse the runs of Programs that share the database.
- [x] A test opens a Program, puts its row into the disagreeing state, and fails if either repair or the neighbouring Program's run is still refused.

## Why

Found during authorised live validation on 2026-08-16, against a real target.

`check_program_configuration()` in
`20260813T230000Z__reserve_the_worst_case_and_reconcile_it.sql:1190-1203`
reports `configuration_ceilings_disagree` when a Program's per-run ceiling is
above its Lane's or its campaign's. That check is correct and the reasoning
above it is right: such a Program admits nothing and blames its budget for it.

Two things around it are not.

**The refusal has no exit.** `rk run` evaluates integrity before it adopts a
configuration -- the assertions come back in the order `configuration`,
`scope_policy`, `corpus`, `runtime_connection`, `integrity`, `scope_version`,
`program`. So the standing check reads the row as it stands, refuses, and the
corrected configuration is never applied. `--accept-change` is the flag for
exactly this situation and it cannot reach it either:

```
stop refused viol [{'code': 'integrity_failed',
  'source': 'standing:program_configuration',
  'detail': '1 problem(s): (configuration_ceilings_disagree,yekta-yconlab,
             "per run 400000 tokens/400 requests, per lane 300000/200,
              campaign 2000000/800")'}]
```

The only way out found during the run was to drop the database and re-migrate.

**The blast radius is every Program.** The check is a standing one over all
Programs, and `rk run` refuses on any failure rather than on a failure
concerning the Program it was asked to run. A second, well-formed Program in
the same database was refused with the identical violation, naming the first
Program's slug.

## What is already done

The door now refuses the configuration that produces such a row.
`config.py` carries `BUDGET_CEILINGS` and `_budgets` compares the per-run
ceiling upwards against the Lane's and the campaign's, so
`rk doctor --config` exits 3 and names both offending keys:

```
config:budgets.run_requests | must not exceed budgets.lane_requests, which is 200
config:budgets.run_tokens   | must not exceed budgets.lane_tokens, which is 300000
```

That closes the way in for a new Program. It does nothing for a database that
already holds one, which is what this ticket is for.

## Notes

Only the per-run ceiling is compared upwards, matching the SQL check: a Lane
ceiling above the campaign's is slack, because the campaign total binds first
and the Lane never does.

## What was built

`20260830T000000Z__a_program_whose_ceilings_disagree_can_be_repaired.sql`.

A standing check is now either about the corpus or about one Program, and
`standing_checks.program_scoped` records which -- with a constraint keeping the
column honest, since a scoped row's query has to carry the `$1` the runner binds
the Program list to. `check_program_configuration` takes that list, defaulting
to NULL: NULL is every Program, which is what `rk db verify`,
`assert_standing_checks` and every migration ask for, and the empty array is
none. The filter lives in the checker rather than in the runner because only the
checker knows which column holds a slug -- two of its five arms report
`slug || ' revision ' || n`, and a runner filtering on the `object` column by
equality would have stopped asking those two anything.

`program.open_program` then splits its one gate in two. The pre-adoption gate
asks for the global invariants only, so a neighbour's contradictory row is
nobody else's refusal. The Program-scoped checks run again at the end of
`_open_program`, inside the transaction that adopted the configuration, so a
corrected file repairs the row and a file that leaves it contradictory rolls the
adoption back instead of half-applying it. What that transaction writes is held
in locals until it has passed, so a refusal reports no program_id, no
configuration revision and no scope version -- the rollback took all three back,
and naming them would tell an operator about rows the database does not hold.

`capsule.compile` asks the same narrow question, for the same reason on the
other side of it: the capsule describes one Program's session, and a neighbour's
fault in its integrity section is somebody else's fault spending this model's
attention.

Two tests in `ProgramRunTest`: one opens a Program, poisons its row, proves a
neighbour still opens and that `--accept-change` with a corrected file repairs
it; the other proves an unchanged file records no revision, repairs nothing, is
refused with the check named, and answers with none of the rows it rolled back.
