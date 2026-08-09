# 20 — Run one Task to a canonical Observation

**What to build:** Make `rk run` execute one seeded Task through a real Agent run and network Tool run, then promote one grounded Observation and close every lifecycle row correctly.

**Blocked by:** 17 — Refuse every startup vector fatally and durably; 19 — Serve bounded MCP reads and Mission proposals.

**Status:** ready-for-agent

- [ ] `rk run` claims one ready Task, starts one allowed role with a bounded Mission packet and serves one capability-backed target request.
- [ ] The proxy Receipt, response Artifact, Tool run, Agent run, Task attempt and Mission proposal share the correct Program and causal identifiers.
- [ ] Runtime promotion verifies provenance and creates exactly one immutable canonical Observation in one transaction with its Event.
- [ ] Agent completion prose cannot close the Task until the runtime has accepted the structured result and reconciled execution.
- [ ] Success leaves no live capability, open Tool run, open Agent run or unreleased Lease; failure and restart reconcile idempotently.
- [ ] Running the slice twice from identical clean state yields the same decisions and relationships while generating only expected new run identifiers.
