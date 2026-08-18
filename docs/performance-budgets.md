# Performance budgets

What the five operations an operator waits on are allowed to cost, on a corpus
the size of a real engagement. `SurfaceBenchmarkTest` in `tests/test_database.py`
reads this file, builds the corpus below and measures each operation against the
budget beside it, so the document and the measurement cannot drift: a budget
written here that nothing measures fails the case by name, and a measurement
with no budget here fails it the same way.

The numbers are deliberately loose. A budget tight enough to be a target is a
budget that fails on a busy laptop and teaches everyone to rerun the suite until
it passes; what these are for is the other failure, where an operation that took
a tenth of a second starts taking thirty because a join lost its index or a
bounded read stopped being bounded. Each is roughly an order of magnitude above
what the operation costs on the development machine, and every measurement is
printed when the case runs, so drift is visible long before a budget is reached.

The statistic is the median of five repetitions. Not the minimum, which reports
a machine that got lucky once, and not the mean, which one scheduler hiccup
moves further than a real regression would.

## The corpus these are measured on

One Program, at the size a mid-sized web target reaches after recon has run and
before anything has been closed out. The Findings, Hypotheses, Tests, Receipts
and Tool runs come from the fixture the case is built on rather than from this
table -- there are a few dozen of each, which is what a real engagement holds,
and they are what the report rendering measurement renders.

| Rows | Count |
| --- | --- |
| `applications` | 8 |
| `endpoints` | 400 |
| `parameters` | 800 |
| `tasks` | 1200 |

## The budgets

| Measurement | Budget | What is measured |
| --- | --- | --- |
| `slate` | 1500 ms | `offer_slate()`, which ranks every claimable Task of the Program and writes the offer. The one measurement here that writes, because superseding the previous slate is part of what an offer costs. |
| `playbook_selection` | 750 ms | `select_playbooks()` for one Surface against the whole shipped catalogue, at the ceiling and role a hunter runs under. |
| `bounded_read` | 4000 ms | `state.read()`, the whole command: it opens the runtime connection, resolves the Program, opens the agent connection, binds the session and reads the compact index. The budget is the largest here because two connections are two round trips before a row is read, and an operator waits for the command rather than for the query. |
| `graph_integrity` | 1500 ms | `check_kill_chains()`, which walks every chain in the corpus rather than one Program's. |
| `report_rendering` | 500 ms | `reporting.render()` over the long-form Finding bundle. Pure computation with no server in it, which is why it is the smallest budget and why exceeding it means the renderer itself grew a cost. |
