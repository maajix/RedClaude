# 06 — Store and read a redacted Artifact

**What to build:** Persist one non-secret runtime Artifact by content hash and let the owning Program retrieve bounded ranges without widening global deduplication into cross-Program access.

**Blocked by:** 05 — Prove Program isolation and bounded reads.

**Status:** ready-for-agent

- [ ] Storing identical plaintext twice produces one content-addressed Artifact and distinct Program-scoped references where appropriate.
- [ ] The recorded identifier is the SHA-256 of exact plaintext bytes and is verified again on read.
- [ ] Agent-visible reads require a reference reachable from the current Program and support bounded ranges with omission metadata.
- [ ] A bare hash from another Program cannot reveal existence or content.
- [ ] Artifact creation and reference creation are audited without embedding Artifact bytes in Events.
- [ ] Corruption, missing backing data and hash mismatch fail closed and make dependent integrity checks unsound.
