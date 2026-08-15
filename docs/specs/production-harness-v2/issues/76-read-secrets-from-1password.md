# 76 — Read engagement secrets from 1Password

**What to build:** One way for the runtime to obtain an engagement credential, reading only the two vaults the operator has authorised, and never writing a secret anywhere the rest of the harness can read it.

**Blocked by:** 30 — Run an offline tool under isolation.

**Status:** ready-for-agent

- [ ] Two vault IDs are the whole of what may be read, enforced by the code rather than by convention; any other vault is refused before a subprocess starts.
- [ ] Both authentication paths work: the operator's desktop app for interactive runs, and a service account token for an unattended campaign.
- [ ] A secret reaches its one caller and nothing else -- not an event, not an artifact, not a log line, not an exception message, not a tool run's captured output.
- [ ] The runtime declares no new package dependency; `pyproject.toml` stays `dependencies = []`.
- [ ] A missing item, a locked vault and an unauthorised vault each produce a distinct refusal naming the item, never its contents.
- [ ] The engagement encryption key is read the same way as every other secret, so nothing about it is a second mechanism.

## The authorisation boundary

The operator's statement, which is the criterion and not a preference:

- `4exeximtkfyxd2eywo3m7jpfwu` -- **BugBounty Dynamic**. Per-engagement accounts, one per program.
- `a4g3qhvisxxcyvfzjtfpariwfe` -- **BugBounty Static**. Accounts that outlive an engagement (a Play Store account for Android work) and the key that saved cookies and confidential findings are encrypted under.

Nothing else in the operator's 1Password may be read. The two IDs are a constant in the module and a vault argument that is not one of them is refused before `op` is invoked, so the refusal is this harness's and does not depend on how the account's own permissions happen to be set today.

## Why the CLI and not the SDK

`onepassword-sdk` supports both authentication paths this ticket needs, and it is still the wrong choice here: it is not pure Python -- it ships a compiled core wanting libssl 3 and glibc 2.32 or later -- and `pyproject.toml` says `dependencies = []` with a startup assertion behind it. It is also a v0 package whose own documentation promises breaking changes between 0.x releases. The `op` CLI reaches the same desktop app and honours the same `OP_SERVICE_ACCOUNT_TOKEN`, and costs no dependency.

The decision is confined to one module for exactly this reason: if the SDK later becomes the better answer, it is that module rewritten and no call site touched.

## What this does not decide

- **How the encryption key is used.** This ticket obtains it. Encrypting saved cookies and confidential evidence under it is later work, and the criterion above only requires that the key arrive by the same route as everything else.
- **Which item a program's account lives in.** That is per-engagement configuration, not code.
