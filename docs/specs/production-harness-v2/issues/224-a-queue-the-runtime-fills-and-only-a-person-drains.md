# 224 — A queue the runtime fills and only a person drains

**What to build:** An automatic drain for `validation_queue`, so a Finding the
orchestrator asked about is reproduced and judged by the harness rather than by
an operator at a terminal.

**Blocked by:** nothing. 105 built the producer; 222 built the reproduction the
drain would call; 223 stopped that reproduction from failing the standing
family.

**Status:** ready-for-agent

## The wall, measured 2026-08-30

`validation_queue` has exactly one drain and it is a person.

- `grep -rn "validation_queue" src/redkraken/*.py` returns two hits, both in
  `src/redkraken/validation.py`: the `QUEUED` read at `:70` and nothing else.
- The write side is SQL: `request_validation` holds the only
  `INSERT INTO validation_queue` in the corpus
  (`20260815T180000Z__a_blind_validator_answers_from_the_packet.sql:656`).
- `open_validation` sets `running`, `abandon_validation` and `record_verdict`
  set `done`. All three are reached from `validation.run`, and `validation.run`
  is reached from `rk finding validate` and from nothing else.
- `grep -rn "finding validate\|validate" hunt.sh supervise.sh` in
  `/home/majix/engagements/here-technologies-2026-08-25` returns nothing. The
  hunt loop runs `rk run` and never `rk finding validate`.

So after 105 the orchestrator can ask, and the ask sits in the queue until a
human notices it.

## The price

The reproduction itself is built and costs nothing to reuse. `validation.run`
already opens its own `agent_runs` row when the operator names none (ticket
222), already resumes a validation left `queued` rather than refusing it, and
already reads its own door out of `proxy.PROXY_URL`. What is missing is a caller
inside the lap.

Three shapes, cheapest first.

1. **A step in the engagement's `hunt.sh`.** One `rk finding validate` per lap,
   for the oldest `queued` row. Costs a shell loop and a way to name the label
   from the queue -- there is no `rk finding queued` command today, so it would
   be a `psql` read or a new read-only subcommand. Buys the drain immediately
   and keeps the harness out of it. Does not survive a fresh engagement: every
   engagement copies its own `hunt.sh`.
2. **A `validate` Task kind the scheduler offers.** `role_task_kinds` already
   holds `validator/session` and `tasks.kind` already has `validate` in
   `task_kinds`; 0 rows of that kind have ever been written in any Program. A
   Task per queued Finding would put the drain on the Slate, which is where
   every other unit of work in this system lives, and the orchestrator would
   then be choosing between hunting and validating rather than doing both.
   Costs a writer that derives the Task from the queue, plus the lane and quota
   rows, plus `execution` learning to run a `validate` Task the way it runs a
   `perform` one.
3. **A drain in `rk run` itself**, before or after the lap. Costs the least
   code and puts a second scheduler inside the one there is, which is the shape
   this repo has refused before.

Shape 2 is the one that matches the system. Shape 1 is the one that works this
week. The ticket asks for a decision between them before any code.

## Why it matters

Nine Findings on `rk2here`, all `candidate`, all `info`, on 2026-08-30. Each one
needs a validation before it can carry a severity, and a campaign that has to
stop and wait for a person cannot reach a Medium finding on its own. 105's
producer removes the first half of that; this ticket is the second.

## Acceptance

- [x] The decision between shapes 1 and 2 is recorded in this file, with the
      price of the one not taken.
- [ ] A Finding the orchestrator asked about is reproduced and judged with no
      operator command, measured on a live Program: `validation_queue` goes
      `queued -> running -> done` and `validation_attempts` gains a row whose
      `agent_run_id` is not one a terminal opened.
- [ ] The drain is idempotent under a crash: a row left `running` by a killed
      process is picked up again rather than stranded. `abandon_validation`
      exists for this and the drain names when it calls it.
- [ ] The standing family stays quiet across the whole window. 223 narrowed
      `check_finding_candidates` rule 3 for exactly this state; a drain that
      opens more than one window at a time is a case that rule has not seen.

## The decision, taken 2026-08-30

**Shape 1 now, shape 2 still owed.** `drain-validations.sh` lives in the
engagement directory, is called by `hunt.sh` between laps, and drove `F9` from
`queued` to `validated` on the live `rk2here` Program. It is fourteen lines of
shell and it exists because the campaign was one step short of a validated
Finding and the step was a person typing a command.

Shape 2 is not withdrawn and this ticket stays open for it. What it costs, read
this session rather than estimated:

- A frontier and a derivation, the pair that
  `20261021T000000Z__a_supported_claim_becomes_the_finding_it_earned.sql:495-565`
  already spells for `conclude`: a `STABLE` function returning the queue rows
  nothing has claimed, and a `derive_*` function that turns them into Tasks
  under `max_conclusions_derived_per_pass`'s sibling ceiling.
- `validate` already exists as a Task kind (`roster.py:79`) and the `validator`
  Role already claims it (`roster.py:2301-2317`), so `task_kinds` and
  `role_task_kinds` need no row. That is the half of shape 2 that is built.
- `execution` learning to run a `validate` Task. This is the half that is not:
  the `validator` Role is `runs_as=SESSION` and every kind `execution` runs
  today is `SUBAGENT` or `RENDERER`. `rk finding validate` is the only caller
  that starts a validator session, and shape 2 means that call moving out of
  `cli.py` and into the lap.
- The four rows in `runtime_table_surface` and the `runtime_verb_surface` row
  the new verbs need, which is the bookkeeping every migration in this corpus
  pays.

## What shape 1 does not buy

Named here so the gap is not read as closed:

- **It is engagement-local.** The script is in
  `/home/majix/engagements/here-technologies-2026-08-25`, which is not this
  repository. A second engagement gets no drain until somebody copies a file.
- **It is not crash-idempotent.** Acceptance criterion 3 asks for a row left
  `running` by a killed process to be picked up again; this script reads only
  `queued` rows and would walk past a stranded one. `abandon_validation` exists
  and the script does not call it.
- **It drains one row per lap.** A queue that fills faster than one per lap
  grows, and nothing says so.
