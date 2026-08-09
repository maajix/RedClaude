# 64 — Run and remediate the final code review

**What to build:** Review the complete production diff independently against repository Standards and the production Spec, fix every actionable release blocker and prove the review is clean enough to hunt.

**Blocked by:** 63 — Audit Spec, ticket and implementation coverage.

**Status:** ready-for-agent

- [ ] The fixed review point predates production implementation and the reviewed head contains every completed ticket and coverage artifact.
- [ ] Independent Standards and Spec reviews inspect the production runtime, schema, topology, tests, catalogue, UI, migration and operator surface rather than prototype code alone.
- [ ] Every finding records severity, exact source location, violated contract, evidence and remediation.
- [ ] All HIGH and MEDIUM findings are fixed with regression coverage or explicitly block release; LOW findings are fixed or dispositioned transparently.
- [ ] Targeted and full validation rerun after remediation, including secret, containment, migration and long-campaign gates.
- [ ] A final review pass reports no unresolved HIGH or MEDIUM finding and confirms that no production path imports or executes a prototype.
