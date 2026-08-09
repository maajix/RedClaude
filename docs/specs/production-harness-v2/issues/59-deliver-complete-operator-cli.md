# 59 — Deliver the complete operator CLI

**What to build:** Give the operator one supported command surface for running, inspecting and controlling the full harness without raw database access or ad-hoc scripts.

**Blocked by:** 14 — Accept one explicitly configured callback Observation; 28 — Rotate the orchestrator and resume from a bounded capsule; 29 — Deliver pending decisions, Halt and resume verbs; 38 — Authorize and prove impact separately; 43 — Export a redacted evidence bundle; 57 — Close the 223-row v1 disposition ledger; 58 — Import v1 state without fabricating truth.

**Status:** ready-for-agent

- [ ] Supported verbs cover version, doctor, migrate, run/resume, Program lifecycle, compact/full reads, Halt/clear, pending decisions, integrity, import, validation, report and evidence export.
- [ ] Read verbs are non-mutating and return stable structured output with labels, revisions, digests and omission markers.
- [ ] Mutation verbs are narrow domain operations with explicit confirmation or standing-grant requirements where risk demands it.
- [ ] There is no generic SQL, arbitrary JSON patch, credential read/write, raw Receipt insert or Program-selector argument on model-facing operations.
- [ ] Human-only Finding reporting and review-gate clearing are distinct operator transitions with Events.
- [ ] Help, exit codes, machine-readable output and redacted diagnostics are consistent and tested from a clean installation.
