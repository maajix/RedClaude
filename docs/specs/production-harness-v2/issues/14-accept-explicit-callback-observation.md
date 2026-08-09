# 14 — Accept one explicitly configured callback Observation

**What to build:** Turn one correlated inbound callback on an operator-configured channel into a provenance-backed Observation without authorizing general callback infrastructure discovery.

**Blocked by:** 06 — Store and read a redacted Artifact; 08 — Compile and enforce one Scope Policy.

**Status:** ready-for-agent

- [ ] Only callback channels declared in the current Program policy can be provisioned or read.
- [ ] A runtime-generated correlation token binds the inbound record to one Program, Test or Tool run without becoming Agent-visible credential material.
- [ ] The exact inbound bytes are stored as an appropriate Artifact and promoted into an immutable Observation through runtime validation.
- [ ] Missing, expired, fabricated and cross-Program correlation tokens cannot confirm a Hypothesis.
- [ ] Unconfigured hosts, wildcard channels and adjacent infrastructure remain refused.
- [ ] The acceptance test is entirely synthetic and does not contact an external callback provider.
