# 47 — Validate v1 dispositions against real replacements

**What to build:** Extend the frozen v1 census into a machine-checkable migration ledger whose every disposition resolves to a production replacement, explicit absorption or deliberate retirement.

**Blocked by:** 44 — Compile capability-based Skills; 45 — Select one Playbook by Property class.

**Status:** ready-for-agent

- [ ] Every one of the 223 manifest rows has exactly one disposition, rationale, replacement identifier and verification reference.
- [ ] Replacement identifiers resolve to a current production role, Skill, Property-class vocabulary entry, Playbook, reference attachment, runtime control or explicit scope retirement.
- [ ] Missing replacements, stale source hashes, duplicate coverage and impossible disposition/kind combinations fail CI.
- [ ] The ledger distinguishes rewritten capability, absorbed vocabulary/reference, superseded runtime/workflow and out-of-scope retirement.
- [ ] Regeneration never edits the source v1 repository or reads engagement state as knowledge input.
- [ ] Summary counts reconcile exactly to the frozen census and are emitted in a reviewable deterministic report.
