# 17 — Refuse every startup vector fatally and durably

**What to build:** Exercise every credential and settings vector through the real launch interface and make any pre-spawn or init refusal a durable fatal supervisor outcome.

**Blocked by:** 04 — Create or resume a Program with the same command; 16 — Start one clean real Agent child.

**Status:** ready-for-agent

- [x] Every watched environment variable, settings helper, watched settings environment key, malformed setting and unexpected init source is parameterized through an actual child launch.
- [x] Pre-spawn violations construct the SDK transport zero times; init violations serve zero tools and close the transport.
- [x] Refusal closes the Agent run, returns its Task to pending without consuming an attempt, releases Task and Identity Leases and removes session bindings in one transaction.
- [x] Exactly one redacted `startup.refused` occurrence Event is emitted, and repeated cleanup is an idempotent no-op.
- [x] The supervisor latches after refusal, rejects another Agent run in the same process and exits non-zero; a clean process restart may proceed after remediation.
- [x] A refusal before Program creation leaves no invalid Event or state, and diagnostics expose names, phases and measured effects but no values.
