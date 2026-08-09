# 25 — Reserve and reconcile campaign budgets

**What to build:** Prevent concurrent Tasks from overspending token, request and Lane ceilings by reserving capacity before admission and reconciling actual use on every terminal path.

**Blocked by:** 13 — Enforce Halt and aggregate request budget at egress; 23 — Offer and claim a deterministic Slate.

**Status:** ready-for-agent

- [ ] Program configuration supplies total, per-Agent-run and per-Lane token/request ceilings plus concurrency limits.
- [ ] Claim admission reserves worst-case capacity transactionally before a Task becomes running.
- [ ] Concurrent claims cannot collectively reserve past any shared ceiling.
- [ ] Actual SDK usage, proxy exchanges and Tool usage reconcile reservations on success, abort, refusal, timeout and crash recovery.
- [ ] Exhausted capacity makes Tasks ineligible with a typed reason and never relies on a prompt instruction.
- [ ] Rate-limit and retry timing is durable, bounded and does not spin inside an Agent session.
