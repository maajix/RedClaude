# 18 — Compile and enforce the six-role roster

**What to build:** Run the production orchestrator, recon, web hunter, JS analyst, validator and deterministic reporter through one closed roster whose declared authority is enforced at every tool call and delegation.

**Blocked by:** 03 — Run production migrations and the integrity gate; 15 — Replay auth-resolution evidence in production.

**Status:** ready-for-agent

- [ ] One roster compiles role kind, invocation authority, task kinds, model, effort, turns, builtin tools, MCP groups, Skills and concurrency.
- [ ] The pre-tool gate denies unattributed calls, unlisted tools, wrong role bindings, built-in agent types, session-role delegation and concurrency overflow.
- [ ] The orchestrator has scheduling and state reads but no target network or technique Skill; validator has only its closed judgement surface; reporter runs no model.
- [ ] No model-facing tool accepts Program selection, credentials, raw SQL, arbitrary canonical writes or unrestricted process creation.
- [ ] Tool visibility and permission mode cannot widen the enforced allowlist, proven through an executed deny canary.
- [ ] The roster validates against the observed SDK/CLI tool inventory and fails on unknown, misspelled or newly unclassified builtin tools.
