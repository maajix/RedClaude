# 07 — Encrypt credential-bearing wire Artifacts

**What to build:** Retain authoritative wire evidence without turning the database, Artifact store, logs or Agent reads into a plaintext credential archive.

**Blocked by:** 06 — Store and read a redacted Artifact.

**Status:** ready-for-agent

- [ ] Wire Artifacts use authenticated encryption with runtime-owned key material outside the database and Agent-visible configuration.
- [ ] Ciphertext metadata records algorithm version, nonce and plaintext hash while never storing the plaintext capability or credential.
- [ ] A synthetic credential marker is absent from database dumps, logs, Events, diagnostics and ordinary Agent-visible reads.
- [ ] Agent-view and wire-view Artifacts remain separate immutable references whose hashes describe the exact bytes each party saw.
- [ ] Only an explicitly authorized runtime operation can decrypt a wire Artifact, and every such operation is audited.
- [ ] Tampered ciphertext, wrong key material and cross-Program references fail closed without returning partial plaintext.
