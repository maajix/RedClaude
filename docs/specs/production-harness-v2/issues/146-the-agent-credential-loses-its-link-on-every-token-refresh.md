# 146 — The Agent credential loses its link on every token refresh

**What to build:** A supported, refresh-independent setup-token path from the
supervisor to one short-lived child, and a `rk doctor` check that refuses an
unsafe or unusable token file before a run spends an attempt finding out.

**Blocked by:** nothing.

**Status:** resolved

- [x] **The measurement is in the ticket.** `rk2hunt7`, 2026-08-22, two
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

- [x] **The operator step is named somewhere an operator reads.**
      `tools/setup-agent-oauth.sh` runs the exact `claude setup-token` command,
      reads the value once without echo, installs it atomically with safe modes,
      and verifies Doctor plus the pinned SDK/CLI canary. No `chgrp`, hardlink
      or world-writable credential is required.

- [x] **`rk doctor` asks the question before a run does.** Doctor and launch
      share the setup-token predicate and its remedy, so an invalid path, type,
      owner, mode, age warning or content shape is visible before dispatch.

- [x] **Checked by something that would go red.** The credential regressions
      reject relative overrides, symlinks, unsafe parent/file modes, wrong
      ownership, empty and multiline values, and prove the private-envelope and
      `apiKeySource=none` success paths.

## Why

Found by running the harness, not by reading it. Ticket 86 was right that a
credential living only in a copy is a token refreshed into a directory about to
be deleted, and right to refuse an unwritable one before launch. What it did not
carry is that the operator-side arrangement it depends on is not durable: the
link breaks on a schedule nobody controls, and the refusal that follows names a
path without naming what to do to it.

Blocking for a live hunt, cheap to fix, and independent of every other open
ticket.

## Resolution, 2026-08-23

The writable `.credentials.json` arrangement was replaced by one supervisor-
owned setup-token file. `rk doctor` and launch both require an absolute regular
file below a `0700` parent, mode `0600`, one non-empty line, no symlink, and the
supervisor owner. `tools/setup-agent-oauth.sh` installs it atomically, warns at
330 days, runs Doctor and the pinned SDK/CLI canary, and is the only documented
human step.

The token crosses only the private stdin job envelope and is inserted into the
short-lived child environment after the ambient/configuration checks;
`ClaudeAgentOptions.env` remains empty. Hunt 21 recorded ten completed Agent
runs across five supervisor processes with SDK `0.2.132`, CLI `2.1.224` and
`apiKeySource=none`. The new Agent home contains no `.credentials.json`, and
the sentinel scan found zero matches in process output, container inspection,
Program files, Mission packets, Artifacts and the database dump.
