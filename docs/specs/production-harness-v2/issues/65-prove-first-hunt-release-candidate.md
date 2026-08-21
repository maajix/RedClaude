# 65 — Prove the first-hunt release candidate

**What to build:** Demonstrate from a fresh installation that RedKraken v2 can conduct a safe, complete synthetic bug-bounty hunt and leave the operator with a validated configuration and procedure for the first authorized live Program.

**Blocked by:** 64 — Run and remediate the final code review; 87 — Serve a Skill script as a recorded Tool run.

**Status:** ready-for-agent

- [ ] A fresh operator configures and starts a realistic synthetic web/API Program using only supported documentation, CLI/UI and secret handling.
- [ ] The campaign performs scoped recon, selects production Skills and Playbooks, records a meaningful negative result and discovers at least one fixture vulnerability.
- [ ] The vulnerability progresses through Observation, Evidence, Hypothesis, structured Test, replay, blind validation and deterministic Finding report without manual database intervention.
- [ ] A demonstrated pivot is evaluated in a sound kill chain, while an intentionally missing or invalid pivot remains visibly unreportable.
- [ ] Forced pause, process restart and resume preserve truth, budgets, Leases and bounded context and do not repeat settled work incorrectly.
- [ ] The final evidence bundle verifies independently and contains no synthetic credentials or unredacted wire secrets.
- [ ] The release includes an operator checklist and fillable Program configuration for the first authorized live hunt, with explicit scope, RoE, identity, budget, callback and stop prerequisites.
