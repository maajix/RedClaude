# 08 — Compile and enforce one Scope Policy

**What to build:** Turn Program scope and Rules of Engagement into one canonical decision used consistently before any target-facing operation.

**Blocked by:** 04 — Create or resume a Program with the same command.

**Status:** ready-for-agent

- [ ] The compiled policy represents target inclusions, exclusions, protocols, ports, path restrictions, callback channels, time windows and independent risk permissions.
- [ ] URL, host, IP, port, path and identifier inputs are canonicalized before matching, with ambiguous or malformed forms refused.
- [ ] Required-header names may be read while their values remain runtime-owned and redacted.
- [ ] Absent mutation, sensitive-data, credential, pivoting or availability permission is a denial rather than a permissive default.
- [ ] Adjacent-host, DNS, certificate-transparency, reverse-IP and virtual-host discovery is not authorized unless explicitly configured.
- [ ] The same fixture matrix produces identical decisions through CLI diagnostics and runtime policy calls.
