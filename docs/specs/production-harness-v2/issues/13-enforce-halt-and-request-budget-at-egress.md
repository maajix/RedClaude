# 13 — Enforce Halt and aggregate request budget at egress

**What to build:** Stop all target traffic at the final egress decision when the operator Halts a Program or its aggregate request budget is exhausted.

**Blocked by:** 09 — Send one HTTP request through the capability proxy.

**Status:** resolved

- [x] Program Halt is a durable operator transition and is checked on every exchange, including already-issued capabilities and subresources.
- [x] Only an operator verb can clear Halt; Agent, orchestrator and proxy roles cannot do so.
- [x] Per-target rate, burst, concurrency and total-request limits are enforced across concurrent Tool runs rather than per process.
- [x] Budget exhaustion and rate limiting create typed blocked Receipts and durable retry information without contacting the target.
- [x] Clearing Halt does not revive expired capabilities or closed Tool runs.
- [x] A concurrent fixture proves aggregate enforcement and exact target-contact counts under race.

## Comments

Implemented on branch `implementation/startup-assertion`.

### How it was built

**Halt** was already durable when this ticket opened: `program_halts` and the two
operator verbs are `20260811T130000Z__halt_at_egress.sql`, and
`resolve_egress_capability` refuses while a Program is halted — so every
exchange, including a subresource under an already-issued capability, resolves
the current state rather than the one that was true when the capability was
minted. `halt_program` and `clear_program_halt` are `SECURITY DEFINER` behind
`human_actor_session()` and revoked from `rk2_runtime`, `rk2_state` and
`rk2_proxy`; the standing check `program_halt` fails if any of that is undone.

**The budget** is `20260811T170000Z__egress_budget_at_the_door.sql`. Four limits
compile onto `program_scope_versions` beside the rules of engagement, because a
limit that lives anywhere else is a limit a scope version can be replaced
without. They are nullable and a null refuses: a policy that never said what it
authorised authorises nothing.

Enforcement is three tables and two functions, not a counter in the proxy:

- `program_egress_spend` — one row per Program, the total that does not refill.
  Locked first by every reserver, so two targets under one Program cannot
  deadlock against each other.
- `program_egress_budget` — one token bucket per (Program, target), where the
  target is the scope rule that authorised the request rather than the hostname
  that spelled it. `*.example.com` is one target however many names it has.
- `egress_reservations` — one row per in-flight request, with an expiry.
  A concurrency limit kept as a counter decays to zero when a proxy is killed
  mid-exchange; a row with a lifetime comes back on its own.

`reserve_egress_slot` re-resolves the capability, finds the rule, takes both
locks and decides in one order: total, then concurrency, then rate. It runs
after the request is authorized and **before the name is resolved**, so a
throttled request emits no DNS query — and a caller cannot measure the policy by
watching its own allowance drain on requests scope would have refused.
`release_egress_slot` gives the slot back and, when the door never opened a
socket, refunds the token and both counters. That is what makes the totals a
count of target contacts rather than of attempts.

**In the proxy**, `Fence.reserve` and `Fence.release` sit either side of the
exchange. The slot is released the moment the socket closes rather than after
the Receipt is written: concurrency is a fact about the target, not about how
fast this process writes rows. `Handler._release` is idempotent, so the exchange
and `_serve`'s `finally` can both call it. A refused reservation answers
`X-RedKraken-Decision: budget-refused` — its own token, because a caller's
response to a throttle is the opposite of its response to a capability refusal —
with `Retry-After` in seconds, and writes a blocked Receipt carrying
`retry_after` as an instant.

### Where the proof is

| Criterion | Test |
| --- | --- |
| 1, 2 | `ProxyEgressTest.test_a_program_halted_between_two_requests_stops_the_second_until_an_operator_clears_it` |
| 3 | `ProxyEgressTest.test_an_exhausted_program_budget_stops_a_tool_run_that_never_spent_any`, `...test_a_second_request_in_flight_is_refused_by_the_concurrency_limit` |
| 4 | `ProxyEgressTest.test_a_rate_limited_request_is_refused_with_the_time_it_may_be_retried`, `ExchangeTest.test_an_exhausted_budget_refuses_before_the_name_is_even_resolved` |
| 5 | `ProxyEgressTest.test_clearing_a_halt_revives_neither_an_expired_capability_nor_a_closed_run` |
| 6 | `ProxyEgressTest.test_a_concurrent_burst_across_two_doors_spends_one_budget` |

The sixth is the one the ticket rests on: eight Tool runs, eight capabilities,
two doors on two database sessions, one Program with three requests left, fired
at once off a barrier. Three sockets, three arrivals at the target, three allowed
Receipts and five blocked ones — whichever door was quicker.

The standing check `egress_budget` holds the arrangement in place: `rk2_proxy`
alone may reserve, no role below the owner may write the three tables directly,
no Program's allowed Receipts may exceed its compiled total, and no reservation
may be half-released.

### What this ticket changed elsewhere

`[budgets]` gained a fifth required key, `burst`. Rate is not derivable from a
request total and a window — a Program that may make 5000 requests an hour is not
a Program that may make 5000 at once — and the schema is closed, so the limit had
to be named rather than guessed. Existing configurations are refused until they
declare it, which is the intended direction: the alternative is a default nobody
chose being enforced at the one door that matters.
