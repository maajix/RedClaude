# 23 — Offer and claim a deterministic Slate

**What to build:** Offer the orchestrator a bounded set of ready Tasks and let the runtime transactionally claim only a still-eligible member.

**Blocked by:** 18 — Compile and enforce the six-role roster; 20 — Run one Task to a canonical Observation.

**Status:** ready-for-agent

- [ ] A Ranking pass over fixed rows and a fixed weights version returns the same ordered eligible Tasks without reading the wall clock for rank values.
- [ ] The offered Slate contains at most five ready, role-compatible, Lane-legal, affordable and identity-available Tasks with an expiry and factor breakdown.
- [ ] Claim rechecks every eligibility condition inside one transaction rather than trusting the offered snapshot.
- [ ] Off-Slate, expired, stale, cross-Program and no-longer-ready choices are refused without partially claiming work.
- [ ] Choosing nothing falls back deterministically to the first still-valid entry.
- [ ] Concurrent claim attempts produce at most one winner and complete Events for the resulting row mutations.
