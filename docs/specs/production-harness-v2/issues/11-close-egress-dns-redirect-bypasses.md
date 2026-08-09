# 11 — Close direct-egress, DNS, redirect and subresource bypasses

**What to build:** Prove that every target exchange caused from the agent topology is independently reauthorized by the proxy, including redirects and browser-style subresources.

**Blocked by:** 10 — Send HTTPS through the same capability path.

**Status:** ready-for-agent

- [ ] Inside the real agent container, raw internet TCP, external DNS, target networks, provisioning ports and control ports are unreachable while the proxy remains reachable.
- [ ] The proxy resolves and pins the actual destination and rechecks scope after DNS resolution rather than trusting the requested hostname alone.
- [ ] Redirect targets are canonicalized and scope-checked independently before following them.
- [ ] Each subresource exchange resolves the live capability independently and receives its own Receipt under the parent Tool run.
- [ ] Capability expiry, Tool run closure, Lease loss and Program Halt between parent and child requests stop the next exchange before target contact.
- [ ] Negative fixtures count target contacts so every refused bypass proves that no request arrived.
