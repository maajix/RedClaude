# 83 — Open the first Task of a Program

**What to build:** A supported way for a freshly opened Program to acquire its first Task, so that `rk run` has something to rank, offer and claim.

**Blocked by:** nothing.

**Status:** ready-for-agent

- [ ] A Program with a compiled scope and no history reaches a claimed Task through the shipped surface, without a hand-written `INSERT`.
- [ ] Whatever opens it is narrow: a Task kind and a subject the scope already admits, not an arbitrary row. Ticket 59's fourth criterion -- no generic SQL and no raw insert on model-facing operations -- holds for this too.
- [ ] The Event record says who opened it and why, so a campaign's first Task is as attributable as every Task derived from one.
- [ ] A test opens a Program from a configuration, runs a pass, and fails if the slate is still empty.

## Why

Found during authorised live validation on 2026-08-16, immediately after the
Agent boundary was made to work (ticket 82).

With the boundary configured, `rk run` against a real Program gets all the way
to the scheduler and stops there:

```
{"name": "slate", "ok": true,
 "detail": "no Task is ready; nothing was claimed"}
```

`execution.Slice._pass` is right to stop: an empty slate ends the pass before
the orchestrator session is opened, so no child runs and nothing is spent.

The question is where the first Task comes from, and the answer today is
nowhere. Every production `INSERT INTO tasks` is downstream of state a fresh
Program does not have:

- `20260815T180000Z__a_blind_validator_answers_from_the_packet.sql:956` needs a
  Finding.
- `20260819T000000Z__a_chain_unlock_earns_its_place_in_the_queue.sql:374` needs
  a Hypothesis.
- `20260816T000000Z__impact_is_authorized_before_it_is_proved.sql:1266` needs
  both.

`promote_proposal` does not open Tasks either -- it promotes Observations,
Surface and Hypotheses -- so an Agent cannot propose its own next Task into
existence, and there is no Agent running to propose anything while the slate is
empty.

The suite has never noticed because it opens Tasks directly:
`tests/test_database.py:858` and `:1851` write the row themselves. That is
correct for a database test and it is exactly what an operator has no verb for.

## Notes

The narrow shape this expects is a `recon` Task against a subject the Program's
own scope admits, because that is the one kind whose input is the configuration
and nothing else. `MISSIONS["recon"]` in `execution.py` already has the sentence
such a child would be told: "Map what this target exposes."
