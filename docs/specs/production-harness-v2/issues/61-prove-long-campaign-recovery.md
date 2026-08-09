# 61 — Prove long-campaign recovery and bounded context

**What to build:** Run a synthetic multi-role campaign long enough to force worker turnover, orchestrator rotation and repeated supervisor crashes, then prove the final truth matches an uninterrupted run.

**Blocked by:** 31 — Run a browser entirely through the proxy; 41 — Feed sound chain unlocks into Task ranking; 59 — Deliver the complete operator CLI.

**Status:** ready-for-agent

- [ ] The fixture campaign exercises recon, browser and offline analysis, hunting, replay, validation, negative knowledge, pivot/chain scheduling, reporting and pending decisions.
- [ ] Configured turn, token, decision and serialized-context ceilings force multiple fresh worker and orchestrator sessions.
- [ ] Fault injection stops processes immediately before and after claim, Agent start, Tool start, Receipt write, promotion, validation, Halt and Lease release commits.
- [ ] Every restart reconciles idempotently with no duplicate Events, fabricated attempts, stranded Leases, zombie runs or false terminal state.
- [ ] Final canonical rows, integrity verdicts and reportable Findings/chains match an uninterrupted deterministic control run apart from expected run identifiers.
- [ ] No correctness assertion depends on wall-clock sleeps, transcript replay or a model-authored summary.
