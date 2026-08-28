# 211 — A Test action carries the header and the body it plans

**What to build:** `headers` and `body` on a Test specification action, the
validation that keeps them honest, the plan-to-Receipt binding that proves the
door sent what the plan stated, and the decision about what a `read_only`
Playbook may put in one.

**Blocked by:** nothing.

**Status:** resolved

## What was measured

Found while landing ticket 101, reading the source rather than the capability
card, because three adversarial critics of the ticket-101 source ledger returned
opposite verdicts on the same question.

The agent tool and the replay lane are asymmetric, and nothing in the tree says
so:

| Path | May send |
| --- | --- |
| `mcp__rk2__http_request` | method, url, headers, body (tickets 94, 96) |
| The replay lane, `replay.py:342-351` | method, url |

`_Door.send` calls `proxy.spend` with `url` and `method` and nothing else, even
though `proxy.spend` (`proxy.py:4216-4224`) accepts both a header mapping and a
body. Above it, `rk2_test_spec_problem`
(`20260815T000000Z__a_test_runs_through_the_replay_lane.sql:377`) refuses any
action key outside `('ordinal', 'role', 'kind', 'method', 'url')`, so there is
no place in a specification to put one.

## Why this is not cosmetic

A Finding is not reachable without the replay lane. The chain, read end to end:

1. `rk2_finding_refusal`
   (`20260815T120000Z__a_supported_claim_becomes_a_candidate.sql:644-649`) will
   not open a Finding unless a `hypothesis_transitions` row exists with
   `from_status = 'testing'`, `to_status = 'supported'`, `actor_kind =
   'runtime'`, joined through `test_run_receipts` to the Test run being cited.
2. `close_test_replay`
   (`20260816T000000Z__impact_is_authorized_before_it_is_proved.sql:1125`) is
   the only writer of that row. All 22 `INSERT INTO hypothesis_transitions`
   sites in the migration tree were checked; every other runtime writer moves a
   claim to `testable`.
3. That row's `to_status` comes from `rk2_test_outcome(v_outcome)`, and
   `v_outcome` comes from `rk2_settle_replay` — the evaluation of the Test's own
   assertions.
4. The Observation kind it writes is derived from those assertions and nothing
   else (`20260816T000000Z...:1064-1074`): `response_differential` when a
   `status_differs` or `body_differs` assertion names the action's ordinal,
   `response_invariant` otherwise.

So an Observation an agent files lands in `hypothesis_evidence` as a real edge —
`rk2_promote_hypotheses` puts no filter on the cited kind — but it can never
carry a Hypothesis to `supported`, and therefore can never reach a Finding.

**The Test itself must be the differential.** Today that means any technique
whose difference lives in a request header or a request body is a reading the
agent can perform and the runtime can never confirm. That is most of the
injection corpus, the whole desync and Host family, GraphQL, gRPC, and every
content-type parser differential.

Ticket 101 exists to give the fifty Playbooks executable technique. Writing
"this step stops at an Observation" into a third of them would be a catalogue
that describes attacks it cannot grade — the exact failure
`docs/research/playbook-state-of-the-art/00-todo-and-harness-gaps.md:31-33`
records the harness-first ordering to avoid.

## Acceptance criteria

- [x] **A specification action may state `headers` and `body`.**
      `rk2_test_spec_problem`'s action key set at
      `20260815T000000Z__a_test_runs_through_the_replay_lane.sql:377` widens
      from five keys to seven. Both are optional; an action that states neither
      digests exactly as it does today, so every Test written before this ticket
      is unchanged.
- [x] **A stated header may not be one the door owns.** The names in
      `proxy.HOP_BY_HOP` (`proxy.py:315-329`) are refused in a specification,
      with the refusal naming the header — the door strips them and a plan
      stating one would describe a request that is never sent. Header names and
      values are bounded the way `mcp__rk2__http_request`'s are, and the
      forbidden-name scan that guards that tool (`roster.py:229-244`) applies
      here too.
- [x] **A stated body is a string with the same ceiling as ticket 96's.**
      `bounds=(0, 65536)`, no pattern, for ticket 96's stated reason: the gate's
      forbidden-name scan returns immediately for anything that is not a
      `Mapping`, `list` or `tuple` (`roster.py:1334`), so an object body would
      deny the commonest POST in web testing.
- [x] **The Receipt comparison stays at the route, and the reason is written
      down.** This criterion originally demanded that `record_test_action`
      (live at `20260816T000000Z__impact_is_authorized_before_it_is_proved.sql:1564`)
      gain a header and body comparison. It was over-specified, and the repo
      already answers it: that function's own comment says "The query is not
      compared because only its digest is on the Receipt, over a normalisation
      the door owns." Headers and body are the same situation and more so — the
      door injects identity headers and re-measures the length, so a comparison
      here would be comparing a plan against a message the door rewrote.
      `receipts` carries `query_sha256` and `request_agent_sha` and no header or
      body column, so there is nothing to compare against without a new one.
      What the comparison is for is stopping a Receipt from one action being
      recorded under another ordinal, and method plus route already does that;
      `_Door.send` reads the spec directly, so no gap exists between plan and
      wire for a model to write into. No change to `record_test_action`.

      **Reversed by ticket 214.** This reasoning holds for the state this ticket
      shipped and stops holding the moment two actions can differ below the
      route -- which is what this ticket made possible. 214 adds the columns
      "there is nothing to compare against without" and answers the identity
      injection by digesting the view the caller stated, before it. The
      criterion is left as it was written rather than rewritten: it was the
      decision taken here, and 214 is where it was taken back.
- [x] **`_Door.send` passes them through.** `replay.py:342-351` forwards
      `headers=` and `body=` to `proxy.spend`.
- [x] **The replay lane declares its own body, and ticket 96's rule is left
      alone.** This criterion was written against `_body_allowed`
      (`execution.py:3646`) and named nine body-borne `read_only` Playbooks that
      would have to change `bb:effects`. Reading the source settles it
      differently and more cheaply: `_body_allowed` computes `body_allowed` for
      the **agent's** Tool run, and the replay lane never goes near it.
      `rk2_open_replay`
      (`20260816T000000Z__impact_is_authorized_before_it_is_proved.sql:827`)
      builds its own args — `identity_slot`, `methods`, `test`, `spec_sha256` —
      and has never stated `body_allowed` at all, which
      `authorize_egress_request`
      (`20260924T000000Z__a_request_may_carry_a_body.sql:255-260`) reads as no.
      So the replay lane declares it from the spec, exactly as it declares
      `methods`. Ticket 96's reason for binding the agent lane — "a Tool run
      opened to carry a body chooses its bytes after the row was written" — is
      not true of a Test: the bytes are in the spec, the spec is digested into
      `tests.spec_sha256`, and both the shape check and the risk gate read it
      before a capability exists. `execution.py` does not change, the agent
      lane does not widen, and no Playbook changes its `bb:effects`.
      `canonical_request` is not touched either: it short-circuits for every
      tool but `mcp__rk2__net_request`, and that arm already returns
      `reusable: false`.
- [x] **`roster.py` states the widened contract once.** The specification
      checker and the tool enum are two authorities that agree today rather than
      one read twice (`roster.py:417-423`); that property is kept.
- [x] **A negative control per rule.** Every refusal added here is broken once
      on purpose and asserted to be the rule that fires, for
      `tests/test_database.py`'s stated reason: a check nobody has seen fail is
      a check nobody knows is wired up.

## What this unblocks

Ticket 101's corpus rewrite. The ticket-101 source ledger's `capability_state`
field is judged against the rule "the differential must live in the request
line", and this ticket removes that rule. The ledger needs one re-pass over that
field; the fifty Playbooks are then written once, against the capability that
exists, instead of twice.
