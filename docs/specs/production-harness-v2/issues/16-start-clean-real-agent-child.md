# 16 — Start one clean real Agent child

**What to build:** Launch an actual isolated Agent process through the runtime-owned interface using one effective configuration that has passed the production startup assertion.

**Blocked by:** 10 — Send HTTPS through the same capability path; 12 — Use an Identity without exposing credentials; 15 — Replay auth-resolution evidence in production.

**Status:** ready-for-agent

- [ ] `agent_run(request)` is the only external SDK launch interface and static checks reject direct SDK construction elsewhere.
- [ ] The supervisor builds a positive environment allowlist plus runtime-owned proxy and CA settings, and the child assesses the environment it actually inherited.
- [ ] One runtime-owned settings directory, bundled CLI path and SDK options value is used by both assessment and transport construction.
- [ ] A real isolated child starts against a synthetic local control upstream, emits the expected first init message and becomes tool-ready exactly once.
- [ ] The child has no API key, usable subscription credential, unrelated user/project settings or direct target network path.
- [ ] Missing bundled metadata, executable or supported runtime pair refuses before transport construction without falling back to `PATH`.
