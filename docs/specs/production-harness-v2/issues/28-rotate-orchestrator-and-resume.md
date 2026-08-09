# 28 — Rotate the orchestrator and resume from a bounded capsule

**What to build:** End an orchestrator session at configured ceilings and continue the logical campaign in a fresh session using only newly compiled durable state.

**Blocked by:** 27 — Let the orchestrator choose and dispatch a role.

**Status:** ready-for-agent

- [ ] Turn, token and decision ceilings are hard runtime settings rather than prompt guidance.
- [ ] Reaching a ceiling closes the current session cleanly and emits one occurrence Event with usage and reason.
- [ ] The replacement session receives a bounded capsule of Program lifecycle, budget, integrity, active work and the next Slate with revisions, digests and omission markers.
- [ ] No old transcript, model-authored summary or in-memory scheduler object is required to continue.
- [ ] Restarting the supervisor between rotations yields the same next eligible Slate as uninterrupted rotation.
- [ ] Serialized capsule size and estimated tokens are measured and refused or further compacted when above configured limits.
