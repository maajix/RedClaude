# 165 — A token ceiling that sums the prefix is a turn ceiling

**What to build:** A budget a `conclude` run can finish inside. Every
`web_hunter` run this tree has produced ends on `budget`, and a `conclude` Task
has never once been closed: it returns to `pending`, is picked again, dies the
same way, and the campaign never mints a Finding out of a Hypothesis it already
supports.

**Blocked by:** nothing.

**Status:** resolved

## What was measured

`rk2hunt20`, six laps against the live target on 2026-08-23, after ticket 164's
regression was fixed (`dec1e52`, `afe8a58`):

| run  | role         | input   | output | stop        |
| ---- | ------------ | ------- | ------ | ----------- |
| AR10 | `recon`      |  42 052 |  3 983 | `completed` |
| AR12 | `web_hunter` | 255 742 |     28 | `budget`    |
| AR14 | `web_hunter` | 254 166 |     30 | `budget`    |
| AR18 | `web_hunter` | 253 925 |     38 | `budget`    |
| AR20 | `web_hunter` | 253 076 |     36 | `budget`    |

Every `web_hunter` run. Not one `recon` run.

The same pattern is in `rk2hunt17`, which predates ticket 164, so this is not
that commit's: laps 05, 06 and 07 report 260 247 / 250 020 / 250 466 input
against 43 / 46 / 45 output.

## The mechanism

`_launch.py:1965-1973` adds each turn's whole request to the running total and
breaks when the total passes the ceiling:

```python
spent_in += turn_in
if ceiling is not None and spent_in + spent_out > ceiling:
    stop_reason = "budget"
    break
```

`_usage`'s docstring (`_launch.py:2042-2047`) states that this is deliberate:
"A turn's numbers are that turn's own request, prefix and all, which is what the
Program is charged for making it -- so the session's cost is the sum of the
turns."

A turn's request is the whole prefix, so the ceiling is not a token budget. It
is a turn budget, and the number of turns it buys is `ceiling / context`:

- `recon` carries roughly 14 000 tokens of context, so 250 000 buys about
  eighteen turns. It finishes in three.
- `web_hunter` carries roughly 40 000 -- more tools, a fuller packet, and every
  artifact body it has read still sitting in the transcript -- so the same
  250 000 buys about six.

A `conclude` needs more than six. It has to read the evidence, read the
hypotheses, propose the Finding and submit a result, and two of its six turns
go to tools its own gate refuses:

```
h20-05  R-TOOL  mcp__rk2__get_validation_packet  web_hunter was not granted it
h20-06  R-TOOL  mcp__rk2__get_validation_packet  web_hunter was not granted it
h20-06  R-TOOL  mcp__rk2__get_slate              web_hunter was not granted it
```

A third of the budget is spent being told no. The run never reaches
`submit_mission_result` with a Finding in it, the Task is left `pending`, and
the next lap starts the whole thing over with the same ceiling.

## What this is not

- **Not the packet.** The compile ceiling is `min(65536 bytes, 8192 tokens x 4)`
  = 32 KB, about 8 000 tokens (`packet.py:85-90,180-181`). The packet is a fifth
  of the context, not the whole of it.
- **Not the wrong role.** `roster.py:1777` gives `web_hunter`
  `task_kinds=("hunt", "conclude")`. It is the role the schedule is meant to
  hand this to.
- **Not a measurement artifact.** The sum is the documented intent, and the
  `output_tokens` beside it are consistent with a handful of bare tool calls
  carrying no prose.

## Open

- [x] **The turn count is calculated, not measured.** The child counts its own
      turns as `answers` (`_launch.py:1993`) and the run report drops the number
      on the floor. Carry it into `execution.agent_run` so "six turns" stops
      being arithmetic. This is the cheapest thing here and it should come first,
      because every number below is read against it.
- [x] **Decide what the ceiling is meant to bound.** A cached prefix is billed at
      roughly a tenth, and `_usage` counts it at full price by choice -- the
      docstring says "a cached read is cheaper, not free". At four re-sends of a
      40 000-token prefix the difference between those two readings is most of
      the budget. Either credit the cache and say so, or keep the full count and
      state the ceiling in the turns it actually buys.
- [x] **Stop paying for refusals.** `web_hunter` reaches for
      `get_validation_packet` and `get_slate` on a `conclude` and holds neither.
      Either grant them or take them out of what the role is told it has; a turn
      spent on `R-TOOL` is a turn the Task does not get back.
- [x] **A Task that has burned its budget twice should not be picked a third
      time unchanged.** T6 in `rk2hunt20` is `pending` after two full-cap runs
      and the scheduler will keep offering it. Whatever the fix above, the
      retry needs to differ from the attempt -- a smaller packet, a narrower
      objective, or a refusal that says so out loud.

## Comments

Found while verifying ticket 164's fix. `rk2hunt20` holds the whole trail: 16
Observations, one `supported` Hypothesis (`transport.header_policy`), a `hunt`
Task that ran under `playbooks/deployment/playbook.md`, a `perform` Task that
settled two Tests -- and zero Findings, because T6 cannot finish.

## Resolution, 2026-08-23

Agent runs now persist uncached input, cache creation, cache reads, output,
`answer_count`, raw input and the charged `budget_tokens`. The fixed
`cache-credit-v1` policy charges
`uncached + creation + ceil(cache_read / 10) + output`; `max_turns` remains an
independent hard limit. A terminal `ResultMessage` replaces accumulated usage
only when it carries its own usage values.

The Role-specific MCP server omits foreign contracts from `web_hunter` while
the pre-tool gate still rejects an injected call. An attempt profile binds Task,
Mission packet, Role, Model, budget, policy and build/SDK/CLI. Its first
unchanged budget retry receives a completion-only objective; the database
abandons the second as `budget_exhausted_twice` and refuses a third unchanged
dispatch, while a changed profile starts a new first attempt.

The cached/uncached boundary, terminal outcomes and third-dispatch regressions
pass. Hunt 21's ten completed runs recorded 658066 raw input tokens, 29659
output tokens, 80 uncached input tokens, 133521 cache-creation tokens, 524465
cache-read tokens, 95 answers and 215710 charged budget tokens. Every raw and
budget formula matched, all charged reservations reconciled, and conclude
reached a candidate Finding.
