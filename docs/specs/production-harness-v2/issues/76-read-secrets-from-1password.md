# 76 — Read engagement secrets from 1Password

**What to build:** One way for the runtime to obtain an engagement credential, reading only the two vaults the operator has authorised, and never writing a secret anywhere the rest of the harness can read it.

**Blocked by:** 30 — Run an offline tool under isolation.

**Status:** resolved

- [x] Two vault IDs are the whole of what may be read, enforced by the code rather than by convention; any other vault is refused before a subprocess starts.
- [x] The service account token path works, verified against the operator's own vaults. Both token sources are covered: one already exported, and one on disk. The interactive path -- a local `op` session or a desktop app -- is *left open and is untested*; this host is headless, so it has never been exercised and nothing here claims it has. See "The authentication paths" below.
- [x] A secret reaches its one caller and nothing else -- not an event, not an artifact, not a log line, not an exception message, not a tool run's captured output.
- [x] The runtime declares no new package dependency; `pyproject.toml` stays `dependencies = []`.
- [x] A missing item, a locked vault and an unauthorised vault each produce a distinct refusal naming the item, never its contents.
- [x] The engagement encryption key is read the same way as every other secret, so nothing about it is a second mechanism.

## The authorisation boundary

The operator's statement, which is the criterion and not a preference:

- `4exeximtkfyxd2eywo3m7jpfwu` -- **BugBounty Dynamic**. Per-engagement accounts, one per program.
- `a4g3qhvisxxcyvfzjtfpariwfe` -- **BugBounty Static**. Accounts that outlive an engagement (a Play Store account for Android work) and the key that saved cookies and confidential findings are encrypted under.

Nothing else in the operator's 1Password may be read. The two IDs are a constant in `vault.AUTHORISED` and a vault argument that is not one of them is refused before `op` is invoked, so the refusal is this harness's and does not depend on how the account's own permissions happen to be set today.

A reference must spell its vault by **ID and not by name**. `op` resolves names perfectly well, which is exactly the problem: a name is a label the operator can move between vaults, so `op://BugBounty Static/...` is refused as unauthorised.

The 1Password grant is a second boundary underneath this one, and it moved during implementation: the service account began read-only on Dynamic alone and now holds read and write on both. That makes the read-only property this module's own -- `op read` is the only subcommand it ever invokes -- rather than something the grant enforces.

## What the module is

`src/redkraken/vault.py`, and it is the only place in the runtime that knows 1Password exists.

- `Reference` -- a parsed `op://vault/item[/section]/field`. Parsed rather than passed through, because the vault segment is the authorisation boundary and a string nobody has taken apart cannot be checked against it. Query parameters are refused, so one-time passwords are not reachable this way; that is later work if a program's login needs it.
- `Secret` -- what a read comes back in. `repr`, `str` and `format` all give the reference back, `__slots__` leaves no attribute dictionary to reflect over, `__reduce__` refuses copy and pickle, and `json.dumps` cannot serialise it. That is a barrier on the way *out* of this module and not a vessel the credential lives in: a credential has to become a `str` to be sealed, so both callers `reveal()` within a line or two and it is a plain string from there to the seal. What the type buys is that the crossing is deliberate and that nothing between here and the caller can render one by accident.
- `read` -- one `op read --no-newline <reference>`. The reference travels as the child's argument and the token in its environment, which is the split `rk db dump` makes for `PGPASSWORD` and for the same reason: an argument vector is world-readable in `/proc`.
- `resolve` -- a document walked for references, values substituted, repeats read once.

`op` and `pg_dump` are both trusted host programs rather than isolated ones, and both wanted the same three things: a curated environment, a timeout so an unattended campaign fails instead of hanging, and a bounded quote of the child's own words for a refusal. That had been written twice and the two copies had already drifted apart in the bound, so it is now `src/redkraken/child.py` and `backup.py` was moved onto it. `child.collapse` and `child.tail` are separate on purpose: `op`'s stderr is matched against `SIGNS` whole, and only the sentence a person reads is truncated, or a message recognised today stops being recognised the day `op` becomes chattier.

## The authentication paths

The credential is looked for in three places, in the order an unattended run should prefer them:

1. `OP_SERVICE_ACCOUNT_TOKEN` already exported. **Works**, exercised against the operator's vaults.
2. A token file -- `RK_OP_TOKEN_FILE`, default `~/.config/op/claude-sa-token`, refused unless `0600`. **Works**, and this is the one an unattended campaign uses: the token outlives one shell, so nothing has to carry it through the process tree that starts a run.
3. Otherwise, whatever local `op` session or desktop app the host has. **Untested.** This host is headless -- no desktop app, no TTY, so `op signin` is not possible here -- and no test asserts more than that `op` is still invoked when nothing else authenticated it.

The third is left open rather than refused, because refusing it would be this module deciding that a machine with a desktop app has no way to authenticate. What it is not is a path anybody has seen work. If an interactive host is ever wanted, expect `PASSED_THROUGH` to be short by at least `DBUS_SESSION_BUS_ADDRESS` and `DISPLAY`, and treat that as the first thing to check rather than as a bug. Until then a host with no token gets `op`'s own answer, which `_refusal` turns into `vault:locked` and a sentence naming the two things to go and do.

## Where a secret enters the harness

Two places, both of them a single line in a command that was already reading operator configuration:

- **`rk identity provision`.** The operator's material file holds references where the values would have been, and `vault.resolve` runs between parsing that file and validating it. Everything below that line treats what it holds as material the operator wrote, and every refusal `Session.from_material` can raise names a position -- `origins[0].headers[1].value` -- rather than a value, so a secret that fails validation is still a secret nobody wrote down. The count of references resolved is recorded in the command's facts and held in its ledger line, so an operator can see that a provision read the vault at all without seeing what it read.
- **`RK_ARTIFACT_KEY`,** through `seal.load_root`. Covered below; it is the same `vault.read` and not a second mechanism.

`vault` is imported by five modules and no others: `seal`, and the four command modules that resolve a root secret (`identity`, `header`, `artifact`, `proxy`). Three of those four import it only to name `vault.Refused` in an `except`; `identity` is the one that also calls `resolve`.

A string is a reference or it is not; nothing is substituted inside one. A header value is stored in the vault as `Bearer eyJ...` and a cookie as the whole `session=...; Path=/; Secure` line. The cost is one awkward field per credential; what it buys is that no parser here decides where a reference ends inside arbitrary header text, and no credential that happens to contain `op://` can make the harness read anything.

The root secret comes by the same route: `RK_ARTIFACT_KEY` now accepts a reference as well as a path, so an unattended campaign can hold no key file at all and a host that is lost loses no material. That is criterion 6 -- the encryption key is not a second mechanism, it is `vault.read` with the reference an operator configured. `seal.Location` is the one alias for "a path or a reference", and every signature that carries one now says so, so a reference cannot arrive at a parameter still typed `Path`.

`seal.load_root` lets `vault.Refused` **propagate** rather than flattening it into `Unusable`. A locked or rate-limited vault is not a bad `--key` argument: flattening it would exit `4` pointing at a reference that is correct, when what actually happened is outside this machine and exits `14` as `vault_unreadable`. The cost is one `except vault.Refused` at each of the four commands, which is what it takes for each to name its own subject (`identity_key`, `header_key`, `key`, `artifact_key`) the way every other refusal in the corpus does.

## Why the CLI and not the SDK

`onepassword-sdk` supports both authentication paths this ticket needs, and it is still the wrong choice here: it is not pure Python -- it ships a compiled core wanting libssl 3 and glibc 2.32 or later -- and `pyproject.toml` says `dependencies = []` with a startup assertion behind it. It is also a v0 package whose own documentation promises breaking changes between 0.x releases. The `op` CLI reaches the same account, honours the same `OP_SERVICE_ACCOUNT_TOKEN`, and costs no dependency.

The decision is confined to one module for exactly this reason: if the SDK later becomes the better answer, it is that module rewritten and no call site touched.

## Refusals

`op` exits `1` for most of what can go wrong and `6` for a forbidden vault, so the status alone separates nothing and the classification is on its own words. These were measured against `op` 2.39.0 on this host rather than taken from its documentation, which does not specify any of them.

| What happened | Source | Class |
| --- | --- | --- |
| Vault is not one of the two | `vault:unauthorised` | `invalid_configuration` |
| Reference is malformed | `vault:reference` | `invalid_configuration` |
| `"nope" isn't an item in the ... vault` | `vault:no_such_item` | `invalid_configuration` |
| `does not have a field 'nope'` | `vault:no_such_field` | `invalid_configuration` |
| The field exists and is empty | `vault:empty_field` | `invalid_configuration` |
| The field is over `MAX_SECRET_BYTES` | `vault:oversized_field` | `invalid_configuration` |
| `You are not currently signed in` | `vault:locked` | `vault_unreadable` |
| `(403) Forbidden: You aren't authorized` | `vault:forbidden` | `vault_unreadable` |
| Over the service account's rate limit | `vault:rate_limited` | `vault_unreadable` |
| Anything else `op` says | `vault:op` | `vault_unreadable` |

The last two rows on the `invalid_configuration` side are about what came back rather than about what `op` said, and they are here because the alternative is worse than a refusal. An empty field seals an empty credential and produces an Identity that authenticates as nobody, which surfaces later as a program that mysteriously returns 401 rather than as a configuration mistake. `MAX_SECRET_BYTES` is 64 KiB: a password is bytes and a private key is kilobytes, so anything at that size is a file somebody attached to the item, and reading it into a header value is a mistake worth stopping at the point it is made.

`vault_unreadable` is a new outcome class with its own exit code, and it earns one for the reason `target_unreachable` did: the configuration naming the secret is correct and what refused is outside this machine, so reporting it as an invalid configuration would send an operator to fix a reference that is right. A reference that really is wrong stays `invalid_configuration`, because that one is a file to go and fix.

## What this does not decide

- **How the encryption key is used beyond the root secret.** Encrypting saved cookies and confidential evidence outside the database is later work.
- **Which item a program's account lives in.** That is per-engagement configuration, not code.
- **One-time passwords.** `op`'s `?attribute=otp` query parameter is refused rather than supported.
- **Writing to a vault.** The grant now permits it and this module never does it.
