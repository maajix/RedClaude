# 221 — Severity waits on a validation nothing in this runtime can ask for

**What to build:** Nothing here. This ticket is the measurement that shows what
ticket 105 costs, taken by building the wrong fix first and watching it be
refused. Close it when a Finding reaches `validated` with no operator command.

**Blocked by:** nothing. It was 105, then 224; both are recorded below and
neither turned out to be the wall. See "What was built, 2026-08-30".

**Status:** done

## The chain, measured end to end

`rk2here`, 2026-08-29, after the door restart of ticket 220 put test grading
back:

```
findings                     8   every one severity=info, status=candidate
severity_statements          0
validate tasks, ever         0
report tasks, ever           0
```

`state_severity` is the only writer of `findings.severity` --
`20260816T000000Z:2172-2179` raises if any other function carries the UPDATE,
and a query against the live `pg_proc` returns exactly that one name. It is
served (`agent.SERVED`), described in nine good lines (`_launch.py:1269-1277`),
and reachable by `web_hunter` through `state.conclude`.

It was never called, so the obvious reading was that no objective asks for it.
That reading was wrong, and the cheapest way to find out was to add the
sentence and dispatch one `conclude` Task with it. Run `AR989`, 22:44:12:

```
tools_called => ['get_evidence', 'get_hypotheses', 'get_receipts',
                 'http_request', 'propose_finding', 'state_severity',
                 'submit_mission_result']
denials     => []
```

The child called it. `severity_statements` stayed at 0 and `denials` stayed
empty, because `propose_severity` (`20261031T000000Z:194-215`) catches the
`RAISE` and answers `outcome: refused` rather than aborting -- deliberately,
and the file says so. Reproduced directly, in a rolled-back transaction:

```
SELECT propose_severity('F8','low','program_context', '...');

{"outcome": "refused",
 "refusal": "finding F8 is candidate and severity is stated about a validated Finding"}
```

So the order is fixed and it is the right order: a band is a claim about a
Finding somebody has reproduced, and a `conclude` child has just created one
that nobody has. The full chain to a severity is

```
test holds -> hypothesis supported -> Finding, candidate, info
           -> [ validation ] -> Finding validated -> state_severity
```

and the runtime cannot take the bracketed step. `mcp__rk2__request_validation`
is declared (`roster.py:1015`) and served by nothing (ticket 105), so no
`validate` Task has ever existed in this Program. The only way past it is an
operator running `rk finding validate`, which needs the Agent network the hunt
is holding (ticket 219).

## The wall, priced

```
WALL    state_severity's validated-only rule, reached through
        `propose_severity` (`20261031T000000Z:194-215`) and reproduced above.
        Read in source and exercised against the live database 2026-08-29;
        both ends read -- the verb that refuses, and the objective that now
        reaches it.
PRICE   Zero here and all of it in ticket 105. The severity verb needs no
        change, no new objective and no new sentence: a `conclude` child that
        calls it is refused for a true reason, and one that does not call it
        loses nothing. What is missing is upstream.
PURPOSE This Program exists to find something worth reporting. It has eight
        candidate Findings and no way to say what any of them is worth, and
        the two facts look like one working harness from outside.
RULE    Capability before catalogue. The severity capability is complete. The
        validation capability is declared and unserved, which is 105.
```

## What was tried and reverted

The `conclude` objective was extended to ask for a severity, with two tests, and
reverted the same hour once the refusal was read. It is recorded here rather
than dropped because the next session to notice `severity_statements = 0` will
reach for the same fix: the verb is served, the objective is silent, and the
sentence is one line. It does not work, and the reason is one query away.

## Acceptance criteria

- [x] **A Finding reaches `validated` without an operator.** Ticket 105's, not
      this one's. Closed 2026-08-30 by 224 shape 1: `drain-validations.sh` runs
      between laps from `hunt.sh` and drove `F9` to `validated` with nobody at a
      keyboard. It is engagement-local rather than in this repository, which is
      224's remaining half and is written down there.
- [x] **A validated Finding gets a band.** Closed 2026-08-30. The kind it
      moved to is `conclude`, which already held `state_severity` and already
      had a second job the roster described and nothing derived. `F9` on
      `rk2here` is `low` on basis `constrained_inference`, stated by a child
      through `mcp__rk2__state_severity` with `actor_kind = runtime`.
- [x] **`rk finding` says where severity comes from.** An operator reading
      eight `info` Findings cannot tell a judgement from a gap. Free, and true
      whether or not 105 lands. Done 2026-08-30: the `finding` parser gained a
      `description` saying that `info` means unjudged rather than harmless, and
      that the order is validate, then a band, then a report.

## What 105 closed and what it did not, 2026-08-30

105 landed. It built the producer this ticket said was missing:
`propose_validation` is served, `orchestrator` holds
`mcp__rk2__request_validation`, and `execution.PLANNING` now asks for one
Finding per generation by name -- which is this ticket's own lesson applied,
since a served verb no objective mentions is never called.

The bracketed step in the chain above is still not taken automatically. The ask
fills `validation_queue`; the queue's only drain is `rk finding validate`, run
by a person. So criteria 1 and 2 are not 105's after all -- they are ticket
224's, and this ticket is reblocked on it rather than closed.

Criterion 2's sentence still has no kind to move to. `state_severity` is held by
`web_hunter` alone, whose kinds are `hunt` and `conclude`, and a `conclude` child
creates a candidate Finding rather than meeting a validated one. Whichever shape
224 takes has to say which run meets a validated Finding before that sentence has
anywhere to go; a `validate` Task kind (224's shape 2) would be that run.

## What the first validated Finding showed, 2026-08-30

`F9` on `rk2here` is `validated` and still `info`, and this is the first time
the gap this ticket names has been standing in front of a real row rather than
a hypothetical one. Three facts, each read this session:

**Nothing puts a run in front of a validated Finding.** `rk2_finding_frontier`
(`20261021T000000Z__a_supported_claim_becomes_the_finding_it_earned.sql:495-518`)
is the only producer of `conclude` Tasks, and its last two clauses are
`NOT EXISTS (SELECT 1 FROM finding_hypotheses ...)` and `NOT EXISTS (SELECT 1
FROM tasks ... kind = 'conclude' ...)`. A hypothesis that already carries a
Finding is excluded, and so is one a `conclude` Task has already named in any
status. `F9`'s hypothesis `H165` is both. So the frontier can never offer it
again, and `state_severity` -- `roster.py:1678`, group `state.conclude`, held by
`web_hunter` alone -- has no caller that could reach `F9`.

**The roster already describes the shape that is missing.** `roster.py:2260`
says a `conclude` Task "runs from a validated Finding to the impact
specification, the severity band and the composed report". That is not what the
frontier produces: it produces a Task that runs from a *supported hypothesis
with no Finding*, and the child creates a candidate. The comment describes the
second half of a walk nothing takes.

**`info` was the right band here anyway.** `F9`'s test (`tests.spec` for the run
in `findings.validated_by_test_run_id`) sends five credential-free requests and
asserts only `status_differs`, `status_equals` and `body_differs` on a
404-versus-404 comparison at `/`. No `Origin` header is sent and no
`Access-Control-Allow-Origin` is read, so the CORS statement in `H165` is not
what the run measured. The Finding the `conclude` child wrote --
`error_disclosure`, a method-rejection body differential -- is the honest
reading of that evidence, and `info` is its honest band.

So criterion 2 is not blocked on a missing judgement. It is blocked on a missing
Task kind, and the shape is the same one ticket 224 shape 2 needs: a frontier
over rows that exist plus a derivation that turns them into Tasks. A
`severity` frontier would select validated Findings whose `severity_basis` is
still `undetermined`, which is the column that already distinguishes "nobody
judged" from "judged harmless".

## What was built, 2026-08-30

The sentence this ticket reverted was never the fix, and the kind it was looking
for already existed. `roster.py:2260` says a `conclude` Task "runs from a
validated Finding to the impact specification, the severity band and the
composed report" -- which is not what `rk2_finding_frontier` produces. That
frontier produces the Task that runs from a supported claim to a candidate
Finding. The second half of the walk had a description and no derivation.

So `conclude` has two shapes now, told apart by `tasks.finding_id` -- the column
`validate` already reads for the same question, and one of the seven
`tasks_live_dedup_idx` discriminates on, so two `conclude` Tasks stand on one
claim without a new index.

**`20261230T000000Z__a_validated_finding_gets_the_task_that_bands_it.sql`**

- `rk2_severity_frontier(uuid)` -- validated Findings with
  `severity_basis = 'undetermined'`, in scope, addressable, resting on a
  supported claim, named by no `conclude` Task. Shaped after
  `rk2_finding_frontier` clause for clause.
- `derive_finding_bands()` -- one `conclude` Task per frontier row, carrying
  `finding_id`. Shares `max_conclusions_derived_per_pass` with
  `derive_finding_claims`, because both open the same kind.
- `ready_for`, `novelty_for` and `rank_pass`, each replaced whole with one arm
  changed. Without all three the Task is abandoned before it is offered once:
  `ready_for` answers `conclude.already_found` because the Finding it was opened
  about is the edge that answer reads, and `novelty_for` scores the same edge 0,
  which `cancel_reason_for`'s general rule reads as nothing left to learn. That
  is ticket 152's `perform` measurement in a new place.
- Two `runtime_verb_surface` rows, which is ticket 66's rule.

**`execution.py`** -- `STARTED` gained the Finding label through a LEFT JOIN,
`Claimed` gained `finding_label`, and `objective` dispatches on it into a new
`_banding`. The band objective writes the three bases out with the refusal
waiting behind each, which is ticket 163's lesson applied to a second
vocabulary, and it says there is no band meaning `nothing` so that a run does
not reach for `low` to have said something.

**Not built, deliberately:** a new Task kind. It would have cost a `task_kinds`
row, a `role_task_kinds` row, cost and time priors, lane quota rows, a
`MISSIONS` sentence and a `web_hunter.task_kinds` change -- and would still have
needed the same three arms in `ready_for`, `novelty_for` and `rank_pass`. Also
not built: the impact specification and the composed report. They are the other
two verbs of `state.conclude` and they are their own tickets; a Task asked for
three things it can only do one of is a Task that ends having done none.

## What was verified

Live on `rk2here`, in this order:

1. `rk db migrate` applied clean, 237 migrations, 0 pending.
2. `rk2_severity_frontier` named `F9` and nothing else.
3. `derive_finding_bands()` answered
   `{"ceiling": 3, "derived": 1, "deferred": 0, "candidates": 1}`.
4. `T1152` read `ready_for = NULL`, `novelty_for = 1`,
   `cancel_reason_for = NULL`, while the eight `conclude` Tasks of the other
   shape still read `conclude.already_found` / `0` / `answered`.
5. `T1152` appeared on a real Slate at ordinal 2, priority `1.436716`,
   `entitled: true`.
6. A `web_hunter` child claimed it and stated the band. `severity_statements`
   holds one row: `F9`, `low`, `constrained_inference`, `actor_kind = runtime`,
   with a rationale naming the endpoint and what it returns. `findings.severity`
   and `findings.severity_basis` carry the same words.

`low` is the honest band and this ticket's earlier note says why: `F9`'s test
sends five credential-free requests and asserts only on 404-versus-404
status and body differences. The child read that and did not reach higher.

Offline: `tests.test_execution.BandingObjectiveTest` (7 cases, the dispatch and
both objectives), `tests.test_database.FindingBandTest` (7 cases, the frontier,
the derivation, both scheduler questions, the dedup index and the cache the
frontier reads). `tests.test_execution` 210 pass; `FindingClaimTest` and
`BlindValidationTest` 32 pass unchanged. `check_wiring`, `check_audit`,
`check_baseline` and `check_coverage` all exit 0.
