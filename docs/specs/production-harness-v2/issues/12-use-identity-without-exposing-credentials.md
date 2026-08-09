# 12 — Use an Identity without exposing credentials

**What to build:** Let an Agent choose a named Identity and reach an authenticated target while all credential and session material remains in an encrypted proxy-side slot.

**Blocked by:** 07 — Encrypt credential-bearing wire Artifacts; 11 — Close direct-egress, DNS, redirect and subresource bypasses.

**Status:** ready-for-agent

- [ ] The Agent receives only stable Identity labels and non-secret metadata; no credential, cookie, token or provisioning input is model-visible.
- [ ] Credential acquisition or session provisioning is a control-side operation unavailable through hunter tools.
- [ ] A live, exclusive Identity Lease is required and rechecked for every authenticated exchange.
- [ ] The proxy injects the selected Identity, persists resulting session state encrypted and strips credential-bearing response material from the Agent view.
- [ ] Two concurrent Agent runs cannot share or swap one Identity slot, and cross-Program Identity labels cannot resolve.
- [ ] Agent-view and wire-view hashes prove exactly how identity injection and response stripping changed the exchange.
