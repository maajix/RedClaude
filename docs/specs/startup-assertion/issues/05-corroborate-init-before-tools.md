# 05 — Corroborate init before any tool is served

**What to build:** Use the CLI's first init message as a version-bound second opinion, allowing a clean agent run to continue while stopping an unexpected or ungrounded auth source before any tool can run.

**Blocked by:** 03 — Make `rk.agent_run()` own the effective launch

**Status:** resolved

- [x] The first SDK message must be an init `SystemMessage` whose `apiKeySource` is exactly `none`.
- [x] A different first message, missing field or any other source returns a structured `auth_source_unexpected` startup refusal with source `init:apiKeySource`.
- [x] The init phase remains a supplement: focused tests prove that all six vectors it misses are still refused by pre-spawn assessment.
- [x] No MCP tool, tool run, network receipt or model-visible result can occur before init corroboration succeeds.
- [x] A clean init enables the existing tool surface without changing its allowlist or promotion rules.
- [x] Refusal closes the SDK transport, stops the supervisor from scheduling another run in that process and exposes phase `init` to the durable lifecycle added by ticket 07.
- [x] Tests use a fake SDK message stream and require no network, installed SDK or credentials.

## Comments

Implemented on branch `implementation/receipt-capability`, commit `d550fd3`, on
2026-08-09. Sixteen stdlib launch tests prove exact-first-init corroboration,
zero pre-init tool service and pre-transport refusal of every watched vector.
