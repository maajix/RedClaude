# 174 -- Chromium runs with its own sandbox off and no profile to turn it on

**What to build:** The seccomp profile that lets Chromium's own sandbox start
inside the browser container, or the recorded decision that it stays off -- and
either way the reason kept where a reader of this lane finds it rather than in a
research file.

**Blocked by:** nothing. The lane runs today; this is the hardening step it has
not taken.

**Status:** ready-for-agent

- [ ] `--no-sandbox` (`browser_driver.py:114-119`) either goes away behind a
      profile or keeps a reason that names this ticket. It is set because the
      Agent boundary confines the process and the two together need a capability
      set the container drops, which is true and is not the same sentence as
      "the OS sandbox is not needed".
- [ ] The profile, if it is built, is a file in this tree and is passed by
      `isolation` the way every other flag is. No seccomp profile exists
      anywhere here today; Playwright's own Docker guidance names that file as
      what running Chromium with a sandbox takes.
- [ ] Nothing already hardened is traded for it. `--cap-drop ALL`,
      `no-new-privileges=true`, `--read-only`, `--user 65534:65534`,
      `--pull never`, `--entrypoint ""` and `--rm`
      (`isolation.py:166-208`) stay as they are, and a profile that needs one of
      them relaxed is a profile this ticket refuses.
- [ ] It does not land between a frozen runtime digest and the grading it was
      frozen for. The browser image is one of the digests a campaign freezes, so
      changing it mid-campaign invalidates the measurement rather than improving
      it.

## Why

Ticket 99 served `mcp__rk2__browse`, so a model can reach this lane from a
Playbook step. With Chromium's own sandbox off, a renderer compromise is code
running as uid 65534 and the container is the only boundary left. That was an
operator-only risk while the only entry point was the CLI; it is a model-reachable
one now.

Ticket 99's own criterion says this is either taken there or given a ticket. It
was given this one, because the browser work in Arbeitsblock 3 is bounded to
offering the existing lane through a closed Contract and adds no image, no
runtime flag and no authority.
