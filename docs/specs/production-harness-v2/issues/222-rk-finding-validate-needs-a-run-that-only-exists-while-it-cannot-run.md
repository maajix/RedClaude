# 222 — `rk finding validate` needs a run that only exists while it cannot run

**What to build:** A reproduction that opens its own run, or an operator
command that can open one. And a failure path: today a validate that stops
after `reopen_for_reproduction` leaves the Program refusing every `rk run`, and
nothing in the tree can undo it.

**Blocked by:** nothing.

**Status:** ready-for-agent

## What was measured

`rk2here`, 2026-08-30. The command, run with the run the Finding was born from,
which is the run its own docstring names (`validation.py:5-7`):

```
rk finding validate --config program-here.toml --finding F8 --agent-run AR987

OK  request        | F8 is queued for validation
OK  reproduction   | H160 is testable, so TST83 can be performed again
ERR reproduction   | TST83 was not reproduced, so there is nothing to judge
```

The reason is not in that report -- `validation.py:222-225` says so in a
comment, "the replay reported why on its own ledger and that report is not this
one's to restate". Run directly, it says:

```
rk test replay --test TST83 --agent-run AR987
ERR plan | the registry refused this replay: agent run AR987 has already ended
```

`open_test_replay` (`20260815T000000Z:1139`, the check at `:1165-1168`):

```sql
    IF v_run.finished_at IS NOT NULL THEN
        RAISE EXCEPTION 'agent run % has already ended', v_run.label
            USING ERRCODE = '23514';
    END IF;
```

So the replay needs an open run. On this Program, `0` of `1015` agent runs are
open, and the only statement in the tree that opens one is `proxy.py:3868`,
inside `rk proxy request`, which closes it before returning. A run is open
exactly while a child is running -- and a running child is a peer on the Agent
network, which is what `one_peer` (`isolation.py:1738-1764`) refuses a second
of. The validator's own session is a second peer.

The two states, both refusing:

| state | replay | blind session |
|---|---|---|
| hunt running | open run exists | refused: a second peer |
| hunt stopped | refused: no open run | would work |

The one replay that ever succeeded proves it. `H160`'s transitions:

```
22:42:12  testable  -> testing    the replay of TST83 reached the target
22:42:15  testing   -> supported  the replay of TST83 holds
00:08:37  supported -> testable   reopened to reproduce F8 for validation
```

The first two are a `perform` Task inside a hunt lap, under that lap's own open
run. The third is this command, and nothing followed it.

## What the failure leaves behind

`reopen_for_reproduction` moved the claim before the replay was attempted, and
the failure path does not move it back. That leaves a `candidate` Finding on a
claim that is no longer `supported`, which `check_finding_candidates`
(`20260815T120000Z:976-981`) reports as `finding_claim_not_supported` -- and
the standing check turns into a refusal of every pass:

```
integrity_failed | standing:finding_candidates
  | 1 problem(s): (finding_claim_not_supported,F8,"H160 is testable")
lap 01 -> refused | ok False | exit 9
```

The Program has been refusing since. Four ways out were tried and every one is
refused by design, which is worth writing down because each refusal is right:

- `testable -> supported` directly: `illegal transition testable -> supported`
- `testable -> testing` to walk it back: `transition testable -> testing
  requires a tool receipt`
- `abandon_validation`: answers `nothing_open` and moves no claim
- deleting the Finding: `finding_proposals rows are immutable`

That is a well-built schema refusing to be lied to. It is also a Program that
one failed command can stop, with no command that starts it again.

## The wall, priced

```
WALL    open_test_replay (`20260815T000000Z:1165-1168`) requires an unfinished
        agent run, and `one_peer` (`isolation.py:1738-1764`) refuses the
        second peer that having one implies. Read in source and exercised
        against the live database 2026-08-30; both ends read -- the caller
        that passes `--agent-run` and the function that refuses it.
PRICE   Two separable pieces. (1) The reproduction opens its own run: it is
        already an operator-driven command holding the door, and `proxy.py`
        shows the four columns an opened run needs -- but `agent_runs` carries
        three FKs into `roles` (`role`, `runs_as`, `executes_tasks`), so the
        row is not a hand-written INSERT and belongs in a function beside
        `open_validation_session`, which already opens one. (2) The failure
        path returns the claim: `reopen_for_reproduction` has a counterpart to
        write, and it needs no receipt because it is undoing a move that
        measured nothing.
PURPOSE The Program exists to publish a Finding, and validation is the step
        that makes one publishable. Every Finding here is `info` because
        `state_severity` is refused about a candidate (ticket 221), and every
        Finding is a candidate because this command cannot run.
RULE    Capability before catalogue. The validator, the packet, the verdict
        and the queue are all built and all correct. What is missing is the
        run they are performed under.
```

## Acceptance criteria

- [ ] **`rk finding validate` completes on a stopped Program.** No hunt
      running, no open run beforehand, one candidate Finding: it reproduces,
      serves the packet, files the verdict.
- [ ] **A reproduction that fails returns the claim.** Whatever stops it, the
      hypothesis ends where it started and no standing check fires. A test
      that reopens and then fails the replay asserts the claim is `supported`
      again.
- [ ] **The replay's own reason reaches the operator.** `validation.py:222-225`
      deliberately does not restate it, and the consequence is a report that
      says "was not reproduced" and not "the run you named has ended".
- [ ] **A Program stopped by this is startable again.** Whether that is a
      command, a documented query, or the failure path above never leaving it
      there -- an operator holding `integrity_failed | finding_candidates` has
      no move today.

## What this does not change

Every refusal listed above. The illegal transition, the receipt requirement and
the immutable Finding are the reason this ticket has evidence rather than a
guess, and none of them should be loosened to let this command work.
