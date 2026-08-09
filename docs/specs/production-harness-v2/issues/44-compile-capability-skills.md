# 44 — Compile capability-based Skills

**What to build:** Load production Skills that describe executable capabilities, bind them to allowed roles and tools, and prove that instruction loading cannot widen runtime authority.

**Blocked by:** 18 — Compile and enforce the six-role roster; 31 — Run a browser entirely through the proxy; 32 — Run the JS analyst over a source Artifact.

**Status:** ready-for-agent

- [ ] Skill metadata declares stable name, description, compatible roles, required tool groups, evidence profile, version and optional references.
- [ ] Skill names describe capabilities such as surface enumeration, identity pairing, response comparison, browser evidence, source analysis or untrusted-content handling rather than vulnerability families or workflows.
- [ ] Deterministic behavior lives in checked scripts or runtime tools with a runnable synthetic check.
- [ ] A Skill cannot request a tool group its role does not hold, expose a forbidden builtin or add a new Agent type.
- [ ] The exact Skill text and dependency hashes are recordable on a Task and drift is detectable.
- [ ] Validation covers malformed metadata, missing scripts, unknown roles/tools, duplicate names, path escape and attempted tool widening.
