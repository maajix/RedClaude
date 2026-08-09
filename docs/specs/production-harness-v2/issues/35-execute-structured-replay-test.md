# 35 — Execute a structured Test through the replay Lane

**What to build:** Run one immutable Test specification with baseline, variant and control actions through production egress and derive a deterministic outcome from its assertions.

**Blocked by:** 25 — Reserve and reconcile campaign budgets; 33 — Promote an evidence-backed Hypothesis.

**Status:** ready-for-agent

- [ ] A Test contains typed preconditions, setup, request or tool actions, assertions and cleanup; changing any part creates a new Test identity.
- [ ] The runtime verifies scope, risk, Identity Leases and budget before moving the Hypothesis to testing.
- [ ] Every network action uses a replay-bound capability and produces a Receipt whose Lane is exactly `replay`.
- [ ] Baseline, variant and control roles remain explicit from action through Evidence and cannot be inferred from ordering.
- [ ] Deterministic assertion evaluation records holds, refutes or inconclusive plus failed assertion identifiers and cleanup state.
- [ ] A database constraint and negative test refuse attaching an agent-Lane Receipt, unrelated Tool run or foreign Artifact to the Test run.
