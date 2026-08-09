# 60 — Deliver the local operator UI

**What to build:** Provide a local dashboard over the same bounded application queries and operator verbs as the CLI, with no independent interpretation of campaign truth.

**Blocked by:** 59 — Deliver the complete operator CLI.

**Status:** ready-for-agent

- [ ] The UI shows Program lifecycle and integrity, Tasks and Slates, Agent and Tool runs, Leases, budgets, pending decisions, Surface, Hypotheses, Tests, Findings, chains and reports by stable label.
- [ ] Every view is backed by the same application query as the corresponding CLI read and never accesses Postgres tables directly.
- [ ] Halt, clear, pending-decision and human-report actions invoke the same typed operator operations and display their durable Event outcome.
- [ ] Proposed, attempted, observed, supported, validated, exploited and reported states remain visually distinct, including unsound and stale warnings.
- [ ] Summaries are non-authoritative hash-keyed projections and fall back to canonical text when unavailable or stale.
- [ ] Cross-Program isolation, redaction, keyboard access, empty/error/loading states and bounded large-campaign rendering have automated coverage.
