# 62 — Pass fresh-install and release hardening gates

**What to build:** Prove the complete harness can be installed, upgraded, contained, restored and operated at realistic size from a clean checkout without secrets or prototype dependencies.

**Blocked by:** 60 — Deliver the local operator UI; 61 — Prove long-campaign recovery and bounded context; 66 — Narrow the runtime role's privilege surface.

**Status:** ready-for-agent

- [ ] A clean machine follows one documented install path, starts the supported topology and passes `rk doctor` without prototype or scratch content.
- [ ] Empty creation, supported upgrade, integrity, dump, restore and post-restore continuation all pass through production commands.
- [ ] Agent and browser container tests prove raw TCP, external DNS, control/provisioning ports and direct HTTP/HTTPS remain inaccessible.
- [ ] Secret scanning covers tracked/unignored publishable files, build contexts, generated fixtures, logs, reports and evidence bundles with no findings.
- [ ] Realistic corpus and Surface benchmarks meet documented budgets for Slate computation, Playbook selection, bounded reads, graph integrity and report rendering.
- [ ] The full offline suite and composed production suite pass twice from clean state with no provider network, operator credentials or real target contact.
- [ ] The declared `rk2_runtime` privilege surface from ticket 66 still holds on the installed and restored databases this gate builds, so hardening is verified on the artifacts an operator actually gets.
