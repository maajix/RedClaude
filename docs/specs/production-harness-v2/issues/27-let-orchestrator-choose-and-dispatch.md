# 27 — Let the orchestrator choose and dispatch a role

**What to build:** Run one orchestrator decision over a bounded Slate, commit the runtime-validated choice and dispatch the correct production role without giving the model queue or egress authority.

**Blocked by:** 24 — Manage Task and Identity Leases through crashes; 25 — Reserve and reconcile campaign budgets; 26 — Rank Tasks by value, cost and unlock.

**Status:** ready-for-agent

- [ ] The orchestrator receives only compact Slate entries and relevant bounded Program context, not the full Task queue or transcripts.
- [ ] It may return one offered Task label or no choice and cannot invoke target, Skill or raw claim tools.
- [ ] Runtime fallback and claim revalidation determine the actual claimed Task.
- [ ] The claimed Task's kind selects an allowed role from the roster and rejects incompatible role or Skill combinations.
- [ ] Agent dispatch uses the Leases and reservations from the committed claim and cannot substitute another Task or Program.
- [ ] Malformed, off-Slate and empty model responses all leave a deterministic, safe and auditable outcome.
