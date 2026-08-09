# 24 — Manage Task and Identity Leases through crashes

**What to build:** Hold a Task and all selected Identities exclusively for one Agent run, then release or recover them idempotently after success, refusal, timeout or process death.

**Blocked by:** 12 — Use an Identity without exposing credentials; 23 — Offer and claim a deterministic Slate.

**Status:** ready-for-agent

- [ ] One claim transaction creates the Task Lease, required Identity Leases and Agent-run binding against database time.
- [ ] Task and Identity Leases for one Agent run share one heartbeat and cannot disagree on liveness.
- [ ] A competing claim cannot acquire the Task or any already-leased Identity.
- [ ] Heartbeat, ordinary release and repeated release are idempotent and actor-attributed.
- [ ] Explicit crash reconciliation distinguishes a still-live owner from an expired one and never runs as a side effect of status reads.
- [ ] Recovery returns recoverable work to pending without fabricating attempts, while terminal work remains terminal.
