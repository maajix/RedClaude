# 13 — Enforce Halt and aggregate request budget at egress

**What to build:** Stop all target traffic at the final egress decision when the operator Halts a Program or its aggregate request budget is exhausted.

**Blocked by:** 09 — Send one HTTP request through the capability proxy.

**Status:** ready-for-agent

- [ ] Program Halt is a durable operator transition and is checked on every exchange, including already-issued capabilities and subresources.
- [ ] Only an operator verb can clear Halt; Agent, orchestrator and proxy roles cannot do so.
- [ ] Per-target rate, burst, concurrency and total-request limits are enforced across concurrent Tool runs rather than per process.
- [ ] Budget exhaustion and rate limiting create typed blocked Receipts and durable retry information without contacting the target.
- [ ] Clearing Halt does not revive expired capabilities or closed Tool runs.
- [ ] A concurrent fixture proves aggregate enforcement and exact target-contact counts under race.
