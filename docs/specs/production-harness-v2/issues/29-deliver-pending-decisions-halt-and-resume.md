# 29 — Deliver pending decisions, Halt and resume verbs

**What to build:** Let autonomous work park a typed operator question, continue unrelated Tasks and later resume only through explicit operator decisions and Program controls.

**Blocked by:** 13 — Enforce Halt and aggregate request budget at egress; 27 — Let the orchestrator choose and dispatch a role.

**Status:** ready-for-agent

- [ ] Risk, scope ambiguity, third-party impact, credential need and policy uncertainty use stable question codes and Program-scoped rows.
- [ ] Parking closes the current Agent and Tool runs, releases resources and leaves the Task in a distinct non-terminal state.
- [ ] Other eligible Tasks may continue without waiting for the operator.
- [ ] Only operator verbs can answer, reject or supersede a pending decision and clear Program Halt.
- [ ] An answer is revalidated against current configuration before the Task becomes ready again.
- [ ] Free-text operator context is write-only to the decision record and cannot enter validator or unrelated Agent context automatically.
