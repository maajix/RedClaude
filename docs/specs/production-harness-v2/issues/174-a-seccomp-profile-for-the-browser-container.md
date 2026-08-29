# 174 -- Chromium runs with its own sandbox off and no profile to turn it on

**What to build:** The seccomp profile that lets Chromium's own sandbox start
inside the browser container, or the recorded decision that it stays off -- and
either way the reason kept where a reader of this lane finds it rather than in a
research file.

**Blocked by:** nothing. The lane runs today; this is the hardening step it has
not taken.

**Status:** resolved

- [x] `--no-sandbox` (`browser_driver.py:114-119`) either goes away behind a
      profile or keeps a reason that names this ticket. It is set because the
      Agent boundary confines the process and the two together need a capability
      set the container drops, which is true and is not the same sentence as
      "the OS sandbox is not needed".
- [x] The profile, if it is built, is a file in this tree and is passed by
      `isolation` the way every other flag is. No seccomp profile exists
      anywhere here today; Playwright's own Docker guidance names that file as
      what running Chromium with a sandbox takes.
- [x] Nothing already hardened is traded for it. `--cap-drop ALL`,
      `no-new-privileges=true`, `--read-only`, `--user 65534:65534`,
      `--pull never`, `--entrypoint ""` and `--rm`
      (`isolation.py:166-208`) stay as they are, and a profile that needs one of
      them relaxed is a profile this ticket refuses.
- [x] It does not land between a frozen runtime digest and the grading it was
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

## Answer

The profile was built. The reason `--no-sandbox` was set was measured and found
to be wrong: the capability set is not what stood in the way.

**The measurement.** `hardened` (`isolation.py:209-229`, not the `166-208` this
ticket wrote) gives every container `--cap-drop ALL`,
`--security-opt no-new-privileges=true`, `--read-only` and `--user 65534:65534`.
Under all four, with the engine's seccomp layer taken out of the way,
`unshare(CLONE_NEWUSER)` returns 0 and Chromium's own sandbox starts: the zygote
and every renderer sit in a user namespace this container did not make, chrooted
to `/proc/<zygote>/fdinfo`. So the blocker was one layer and one layer only --
Docker's default seccomp profile, which allows `clone` into a new namespace,
`unshare` and `chroot` only to a container holding `CAP_SYS_ADMIN` or
`CAP_SYS_CHROOT`. `--cap-drop ALL` compiles all three rules out of the filter,
and nothing about the capabilities themselves is the reason.

Playwright's published profile is not enough here and this is why: it clears
only `CLONE_NEWUSER` from the `clone` mask, and it runs against a container that
still holds `CAP_SYS_CHROOT`. Ours holds nothing, and Chromium's zygote asks for
`CLONE_NEWUSER|CLONE_NEWPID|CLONE_NEWNET` in one call. Measured: with only
`CLONE_NEWUSER` cleared, Chromium dies with `No usable sandbox!`; with the three
cleared but `chroot` still capability-gated, it dies one step later at
`zygote_host_impl_linux.cc:221`; with `chroot` allowed but `unshare` not, it dies
at the availability check again. All three are needed and nothing else is.

**What that cost, and what it did not.** `src/redkraken/browser_seccomp.json` is
the profile Docker Engine 29.7.2 itself ships
(`moby/moby@docker-v29.7.2:vendor/github.com/moby/profiles/seccomp/default.json`,
sha256 `536529b665dd0972c37bfb569f5d4ac8a53592e7b00752bc39ff063ca9864c74`) with
three edits, each carrying its reason in a `comment` the upstream schema already
uses: the two `clone` masks lose `CLONE_NEWUSER|CLONE_NEWPID|CLONE_NEWNET`
(`2114060288` becomes `235012096` -- the other four namespace bits stay masked),
and one appended group allows `chroot` and `unshare` unconditionally. Allowing a
call is not granting a capability, and the third criterion is checked by
measurement rather than by argument: under the profile the container's `CapEff`
is still `0000000000000000`, `NoNewPrivs` is still `1`, and `chroot` from the
container's own namespace still returns `EPERM`. Both calls succeed only inside
the namespace Chromium made for itself.

**The fourth criterion.** Nothing here changes an image, so no digest moves and
`--pull never` still decides which build ran. What does change is what a mission
does inside that image, so this is still a change to deploy between campaigns
rather than during one.

**The ceiling.** The file is a copy of a policy this repository does not author
and cannot regenerate. Between moby v24 and v28 the default profile gained seven
syscalls and dropped three (`io_uring_setup`, `io_uring_enter`,
`io_uring_register` -- a tightening); between v28 and 29.7.2 it gained twelve
more. A copy that is not refreshed with the engine is therefore both a lane that
breaks on a future Chromium and a browser container weaker than every other
container this harness starts. Refreshing it is a diff of three known edits
against a named upstream path, and `BrowserSandboxTest` is what says whether the
refresh still works -- but nothing in this tree measures the copy against the
engine actually installed, and nothing can: the engine exposes no way to read
its own default. That is the standing cost of this ticket's answer.

A host whose kernel refuses unprivileged user namespaces now loses the lane
rather than running it open, because Chromium refuses to start unsandboxed
unless told to. That failure arrives as `the browser opened no debugger` with
Chromium's own sentence attached (`browser_driver.py:main`), which is the answer
an operator needs, and it is deliberate: a lane that silently fell back to
`--no-sandbox` would be this ticket undone at runtime.

**Files:** `src/redkraken/browser_seccomp.json` (new),
`src/redkraken/isolation.py` (`run_tool` takes `seccomp`),
`src/redkraken/browser.py` (`SECCOMP`, passed at `_perform`),
`src/redkraken/browser_driver.py` (`--no-sandbox` gone), `pyproject.toml`
(package data), `tests/test_isolation.py` (`BrowserSandboxTest` plus one
refusal in `ToolPlanTest`).
