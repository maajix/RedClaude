# 12 — Use an Identity without exposing credentials

**What to build:** Let an Agent choose a named Identity and reach an authenticated target while all credential and session material remains in an encrypted proxy-side slot.

**Blocked by:** 07 — Encrypt credential-bearing wire Artifacts; 11 — Close direct-egress, DNS, redirect and subresource bypasses.

**Status:** resolved

- [x] The Agent receives only stable Identity labels and non-secret metadata; no credential, cookie, token or provisioning input is model-visible.
- [x] Credential acquisition or session provisioning is a control-side operation unavailable through hunter tools.
- [x] A live, exclusive Identity Lease is required and rechecked for every authenticated exchange.
- [x] The proxy injects the selected Identity, persists resulting session state encrypted and strips credential-bearing response material from the Agent view.
- [x] Two concurrent Agent runs cannot share or swap one Identity slot, and cross-Program Identity labels cannot resolve.
- [x] Agent-view and wire-view hashes prove exactly how identity injection and response stripping changed the exchange.

## Comments

Implemented on branch `implementation/startup-assertion` on 2026-08-11.
Identity material is a closed, origin-bound document sealed per Program and
Identity with revision-bound associated data. It supports headers, cookies and
upstream client certificates; certificate keys enter OpenSSL through an
anonymous in-memory file rather than a plaintext filesystem path.

The database resolves labels only from the capability's Tool run, rechecks the
exclusive live Lease at authorization, address selection, slot open, audit
confirmation and Receipt write, and rejects a slot whose configuration binding
or encrypted revision changed. Legacy Receipt writers are revoked. Root checks,
slot opens, session reseals and configuration invalidation remain auditable.

The proxy withholds all target-controlled response headers, reason text and body
bytes from an Identity call because transformed credential reflection cannot be
recognized safely. It seals the exact wire response, records the public client
certificate hash when mTLS is used, and turns oversized session capture into a
blocked Receipt. The Agent workflow is captured in
`skills/use-identity/SKILL.md`; the project README does not duplicate runtime
instructions or expose the control-side document shape.
