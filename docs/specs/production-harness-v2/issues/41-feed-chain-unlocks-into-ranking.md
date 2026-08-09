# 41 — Feed sound chain unlocks into Task ranking

**What to build:** Turn missing requirements on sound kill-chain paths into auditable candidate Tasks and include their marginal unlock value in the existing deterministic ranking.

**Blocked by:** 26 — Rank Tasks by value, cost and unlock; 40 — Build and evaluate a sound kill chain.

**Status:** ready-for-agent

- [ ] The runtime derives candidate Tasks only from sound chain requirements and current Surface subjects, not from arbitrary model-written edges.
- [ ] Each derived Task records the chain members and capabilities it would unlock without claiming that it will succeed.
- [ ] Marginal unlock counts only newly reachable sound paths and avoids double-counting shared downstream Findings.
- [ ] Invalidating a member, pivot or scope condition removes its unlock contribution on the next Ranking pass.
- [ ] Direct value, probability, cost and safety still constrain ranking; unlock cannot bypass eligibility or Rules of Engagement.
- [ ] Fixtures prove that a useful low-cost pivot can outrank an isolated Task while an unsound proposed chain contributes zero.
