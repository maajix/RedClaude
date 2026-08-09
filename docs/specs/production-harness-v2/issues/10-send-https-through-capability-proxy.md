# 10 — Send HTTPS through the same capability path

**What to build:** Make an HTTPS Tool run cross the exact same production capability, scope and Receipt path as HTTP, including certificate trust inside the real agent topology.

**Blocked by:** 09 — Send one HTTP request through the capability proxy.

**Status:** ready-for-agent

- [ ] The runtime configures both HTTP and HTTPS proxy schemes explicitly and installs only the run-specific trust root needed by the agent environment.
- [ ] A local TLS target is reached through the proxy and produces a capability-bound allowed Receipt.
- [ ] Direct HTTPS from the agent network namespace fails even when a client ignores conventional proxy environment variables.
- [ ] An out-of-scope HTTPS target is refused before target contact with an auditable blocked Receipt.
- [ ] The agent never receives proxy authorization, target credentials or wire-only response material.
- [ ] A regression test fails against the prototype behavior that configured only the HTTP proxy handler.
