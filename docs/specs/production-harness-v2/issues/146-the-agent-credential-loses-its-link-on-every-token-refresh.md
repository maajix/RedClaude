# 146 — The Agent credential loses its link on every token refresh

**What to build:** A supported way for an operator to give the contained user a
credential it can write, and a `rk doctor` check that says so before a run
spends an attempt finding out.

**Blocked by:** nothing.

**Status:** ready-for-agent

- [ ] **The measurement is in the ticket.** `rk2hunt7`, 2026-08-22, two
      refusals from one cause.

      First, exit 9. The child crashed with `Exception: Claude Code returned an
      error result: success`, three times, until `T1` reached
      `attempts_exhausted`. `agent-home/.claude/.credentials.json` showed
      `1 links` and an `expiresAt` thirty-one minutes in the past, while
      `~/.claude/.credentials.json` was fresh. The two had been one inode. The
      CLI refreshes by renaming a new file over the old, which breaks a hard
      link, so the engagement's copy stops tracking the operator's token the
      first time the operator's own session refreshes.

      Re-linking by hand moved the refusal to exit 3:

      ```
      invalid_configuration  the Agent boundary could not be provided: an Agent
      credential the child cannot write: .../agent-home/.claude/.credentials.json
      ```

      which is `isolation.writable_by_the_child(credential, wanted=0o200)` at
      `isolation.py:1219` doing exactly what ticket 86 built it to do. The file
      was `660 majix:majix`; the child is `65534:65534`; no arm of the check
      matches.

- [ ] **The operator step is named somewhere an operator reads.** Making the
      inode reachable by gid 65534 needs `chgrp nogroup`, which needs root once.
      Nothing in the harness says this, and the alternative an operator will
      reach for without root is `chmod 666` on a live Anthropic token.

- [ ] **`rk doctor` asks the question before a run does.** The launch refusal
      is correct and arrives too late: it costs a Task an attempt, and three of
      them abandon it. The same predicate belongs in the preflight, with the
      remedy in the message.

- [ ] **Checked by something that would go red.** A test that a credential
      owned by neither the contained uid nor gid, with no other-write bit, is
      refused by the doctor and not only by the launch.

## Why

Found by running the harness, not by reading it. Ticket 86 was right that a
credential living only in a copy is a token refreshed into a directory about to
be deleted, and right to refuse an unwritable one before launch. What it did not
carry is that the operator-side arrangement it depends on is not durable: the
link breaks on a schedule nobody controls, and the refusal that follows names a
path without naming what to do to it.

Blocking for a live hunt, cheap to fix, and independent of every other open
ticket.
