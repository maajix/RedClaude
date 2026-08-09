# 48 — Rework v1 Agents, Skills, references and sink packs

**What to build:** Preserve the useful operational knowledge from v1 while replacing unsafe Agent authority, routing Skills and global reference loading with the production roster and capability model.

**Blocked by:** 44 — Compile capability-based Skills; 47 — Validate v1 dispositions against real replacements.

**Status:** ready-for-agent

- [ ] The 11 v1 Agent definitions reconcile exactly as five web-hunter lenses, two recon lenses, two JS-analyst lenses, one deterministic reporter replacement and one explicit Android retirement.
- [ ] The four surviving v1 capability Skills are rewritten in the production format with role compatibility, evidence profile and runnable checks.
- [ ] Fourteen routing Skills resolve to Property-class vocabulary, five superseded Skills resolve to runtime/reporting controls, three workflow Skills resolve to scheduler behavior and two Android Skills resolve to retirement.
- [ ] Replacement capability Skills needed by Playbooks exist even where no one-to-one v1 Skill survived.
- [ ] All 112 operator references and 9 sink packs are assigned to bounded Skill or Playbook references rather than global Agent context.
- [ ] No v1 tool allowlist, workflow lifecycle, reporter prose authority, credential handling or engagement data is copied into production unchanged.
