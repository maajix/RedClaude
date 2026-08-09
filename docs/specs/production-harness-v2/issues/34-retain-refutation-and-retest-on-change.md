# 34 — Retain refutation and make it due on Surface change

**What to build:** Keep a refuted Hypothesis as Negative knowledge with its exact conditions and make it retestable only when a relevant Surface delta invalidates those conditions.

**Blocked by:** 22 — Fingerprint Surface and detect change; 33 — Promote an evidence-backed Hypothesis.

**Status:** ready-for-agent

- [ ] Refutation records the settling Test conditions, identities, Surface fingerprint, evidence and transition reason rather than deleting the Hypothesis.
- [ ] Matching unchanged Surface suppresses redundant equivalent Tasks and returns the Negative knowledge in bounded context.
- [ ] An unrelated Surface change leaves the refutation current.
- [ ] A typed relevant delta creates an explicit `retest_due` transition and makes a new Task eligible without rewriting history.
- [ ] Multiple recomputations and restarts are idempotent and emit no duplicate transitions.
- [ ] Legacy negative states without settling provenance import as unverified rather than active suppression.
