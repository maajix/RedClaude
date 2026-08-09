# Vendored code — origin manifest (ticket 31)

A walking skeleton has to *execute* ticket 04's proxy and ticket 05's fixtures,
so this branch is the one place on the map where sibling-branch code is copied
rather than read with `git show`. Every copied file's origin is recorded here so
a divergence can be attributed to the ticket that owns it.

**Nothing under `vendor/` was edited.** Byte-for-byte copies. Where ticket 31
needed different configuration it authored a *new* file outside `vendor/`
(`proxy_config.py`), because ticket 04's `config.py` says in its own docstring
that it is "hand-written dicts, not the real config format" — the extension
point.

Schema comes from `docs/prototype/schema/migrations/` on this branch's own baseline
(`prototype/migrations-fold` `013ee26`), never from a copied file.

| vendored path | source branch | sha | source path |
| --- | --- | --- | --- |
| `vendor/eval-harness/*` | `prototype/eval-harness` | `4750a39` | `docs/prototype/eval-harness/*` |
| `vendor/scope-proxy/*` | `prototype/scope-proxy` | `5e5ca2e` | `docs/prototype/scope-proxy/*` |
| `vendor/sdk-auth-probe/*` | `prototype/sdk-auth-probe` | `9d5b97e` | `docs/prototype/sdk-auth-probe/*` |

`vendor/sdk-auth-probe/out/` was dropped: captured evidence from ticket 21's own
run, not runnable code.

## Which vendored file each proof leans on

| proof | vendored file | ticket |
| --- | --- | --- |
| fixture pair, vuln/secure | `vendor/eval-harness/fixture/app.py` | 05 |
| declared request contract 12/12 | `vendor/eval-harness/fixture/groundtruth.json` | 05 |
| grading predicates | `vendor/eval-harness/harness.py` | 05 |
| spec replay + `outcome_digest` | `vendor/eval-harness/spec.py` | 05 / 22 |
| proxy, three lanes, receipts | `vendor/scope-proxy/addon.py` | 04 |
| scope decision + IP pinning | `vendor/scope-proxy/policy.py` | 04 |
| identity injection, cookie jar | `vendor/scope-proxy/identity.py` | 04 |
| per-target rate limit | `vendor/scope-proxy/budget.py` | 04 |
| receipt store | `vendor/scope-proxy/receipts.py` | 04 |
| containment phase B | `vendor/scope-proxy/phase-b/*` | 04 / 14 |
| startup billing assertion | `vendor/sdk-auth-probe/subscription_guard.py` | 21 |

## Authored by ticket 31 (not vendored)

| file | why it is not a vendored copy |
| --- | --- |
| `proxy_config.py` | ticket 04's `config.py` points at ticket 04's own fixture; ticket 31's target is ticket 05's fixture pair, which authenticates differently (JSON `POST /login`, no CSRF). Written as a new file so `vendor/scope-proxy/config.py` stays unedited. |
| `rk.py` | the runtime: DB session helper, proxy/fixture lifecycle, SDK agent runner, token accounting |
| `skeleton.py` | the nine proofs |
| `phaseb/` | ticket 04's compose renamed to the `rk2-t31-` container prefix and re-pointed at ticket 05's fixture |
